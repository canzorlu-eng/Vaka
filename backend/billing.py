"""Billing via iyzico Subscription (hosted checkout form). The backend never sees card data.

Flow: POST /checkout -> iyzico checkout form -> iyzico hits /callback with a token -> we fetch the result and
activate -> iyzico webhooks (subscription.order.success|failure) keep the period up to date; reconcile_all()
(hourly, from jobs.maintenance_loop) repairs drift (missed callbacks/webhooks).

Double charges: a user has at most one payable form (a live one is re-opened, not re-minted). A charge we still
cannot match (an older tab's form paid after a newer checkout, or a plan mismatch) is refunded and its iyzico
subscription canceled, at callback time or by the hourly orphan sweep; refunds are recorded once per paymentId. All state changes happen in a transaction holding a row lock on the
subscription, so callback, webhook, cancel and reconcile cannot interleave.

Nothing here logs request bodies, customer details or identity numbers; those are pass-through only.

Pending rows (no extra columns available): provider_subscription_ref = 'pending:<checkout token>' and
provider_customer_ref = our conversationId until the callback replaces them with the real iyzico refs.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Literal, Optional
from urllib.parse import parse_qs, quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator, model_validator

import alerts
import cache
import db
from auth import current_user
from config import settings
from ratelimit import limit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/billing", tags=["billing"])

PROVIDER = "iyzico"
PENDING_PREFIX = "pending:"
HTTP_TIMEOUT_S = 20.0
PLAN_INTERVAL_DAYS = {"pro_monthly": 31, "pro_yearly": 366}   # generous: webhooks refine on each renewal
PLAN_MONTHS = {"pro_monthly": 1, "pro_yearly": 12}
PLACEHOLDER_IDENTITY = "11111111111"   # iyzico requires identityNumber; placeholder for non-TR customers (confirm with iyzico)
RECONCILE_MIN_AGE = {"active": timedelta(hours=6), "past_due": timedelta(hours=6), "canceled": timedelta(hours=6),
                     "pending": timedelta(minutes=45)}
PENDING_MAX_AGE = timedelta(days=1)
FORM_TTL_S = 1800   # iyzico checkout tokens expire after 30 minutes
FORM_REUSE_MAX_AGE_S = FORM_TTL_S - 300   # re-open a live form instead of minting a second payable token
FORM_CACHE_PREFIX = "billing:form:"
ORPHAN_GRACE = timedelta(hours=3)   # leave time for the callback / pending reconcile to claim a fresh subscription
ORPHAN_SCAN_PAGE_SIZE = 100
ORPHAN_SCAN_MAX_PAGES = 20
CHARGING_STATUSES = ("ACTIVE", "UNPAID", "PENDING")
# The checkout form is iyzico's inline bootstrap script plus bundles/iframes from *.iyzipay.com. It only runs under
# a CSP that admits those, so it lives on its own page; the SPA keeps script-src 'self'. form-action is left open
# because 3-D Secure posts the card holder to the issuing bank's page.
PAY_PAGE_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://*.iyzipay.com",
    "style-src 'self' 'unsafe-inline' https://*.iyzipay.com https://fonts.googleapis.com",
    "font-src 'self' data: https://*.iyzipay.com https://fonts.gstatic.com",
    "img-src 'self' data: blob: https:",
    "connect-src 'self' https://*.iyzipay.com",
    "frame-src https://*.iyzipay.com",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "base-uri 'self'",
])

# Tests replace this to inject httpx.MockTransport.
_TRANSPORT: Optional[httpx.AsyncBaseTransport] = None


class IyzicoError(Exception):
    def __init__(self, message: str, code: str = "", http_status: int = 0):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


# ----------------------------- iyzico client -----------------------------
def sign_request(api_key: str, secret: str, path: str, body: bytes, rnd: Optional[str] = None) -> Dict[str, str]:
    """IYZWSv2: HMAC-SHA256(secret, randomKey + uri_path + body) -> base64('apiKey:..&randomKey:..&signature:..')."""
    rnd = rnd or secrets.token_hex(12)
    signature = hmac.new(secret.encode(), rnd.encode() + path.encode() + body, hashlib.sha256).hexdigest()
    auth = f"apiKey:{api_key}&randomKey:{rnd}&signature:{signature}"
    return {"Authorization": "IYZWSv2 " + base64.b64encode(auth.encode()).decode(),
            "x-iyzi-rnd": rnd, "Content-Type": "application/json", "Accept": "application/json"}


def credentials_configured() -> bool:
    return bool(settings.iyzico_api_key and settings.iyzico_secret_key)


async def iyzico(method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Signed call. Returns the unwrapped payload (`data` if present). Raises IyzicoError; never logs bodies."""
    if not credentials_configured():
        raise IyzicoError("iyzico credentials are not configured", "not_configured")
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode() if payload is not None else b""
    headers = sign_request(settings.iyzico_api_key, settings.iyzico_secret_key, path.split("?")[0], body)
    try:
        async with httpx.AsyncClient(base_url=settings.iyzico_base_url, timeout=HTTP_TIMEOUT_S,
                                     transport=_TRANSPORT) as client:
            resp = await client.request(method, path, content=body or None, headers=headers)
    except httpx.HTTPError as e:
        logger.error("iyzico request failed: %s %s (%s)", method, path.split("?")[0], type(e).__name__)
        raise IyzicoError("iyzico unreachable", "network") from e
    try:
        doc = resp.json()
    except ValueError:
        raise IyzicoError("iyzico returned a non-JSON response", "bad_response", resp.status_code)
    if not isinstance(doc, dict) or doc.get("status") != "success":
        code = str((doc or {}).get("errorCode", "")) if isinstance(doc, dict) else ""
        msg = str((doc or {}).get("errorMessage", "iyzico error")) if isinstance(doc, dict) else "iyzico error"
        logger.warning("iyzico error: %s %s http=%s code=%s", method, path.split("?")[0], resp.status_code, code)
        raise IyzicoError(msg[:200], code, resp.status_code)
    data = doc.get("data")
    return {**doc, **data} if isinstance(data, dict) else doc


# ----------------------------- plan catalogue -----------------------------
def plan_refs(plan: str, currency: str) -> str:
    return {
        ("pro_monthly", "USD"): settings.iyzico_plan_monthly_usd,
        ("pro_yearly", "USD"): settings.iyzico_plan_yearly_usd,
        ("pro_monthly", "TRY"): settings.iyzico_plan_monthly_try,
        ("pro_yearly", "TRY"): settings.iyzico_plan_yearly_try,
    }.get((plan, currency), "")


def plan_for_ref(ref: str) -> Optional[str]:
    for plan in PLAN_MONTHS:
        for cur in ("USD", "TRY"):
            if ref and plan_refs(plan, cur) == ref:
                return plan
    return None


def plans_payload() -> Dict[str, Any]:
    monthly, yearly = settings.price_monthly_usd, settings.price_yearly_usd
    list_price = round(12 * monthly, 2)
    savings = round(list_price - yearly, 2)
    percent = round(savings / list_price * 100) if list_price > 0 else 0
    currencies = [c for c in ("USD", "TRY") if plan_refs("pro_monthly", c) or plan_refs("pro_yearly", c)]
    return {
        "plans": [
            {"id": "pro_monthly", "interval": "month", "usd": monthly, "try": settings.price_monthly_try},
            {"id": "pro_yearly", "interval": "year", "usd": yearly, "try": settings.price_yearly_try},
        ],
        "list_price_yearly_usd": list_price,
        "savings_usd": savings,
        "savings_percent": percent,
        "available": credentials_configured() and bool(currencies),
        "currencies": currencies,
    }


@router.get("/plans")
async def get_plans(response: Response):
    response.headers["Cache-Control"] = "public, max-age=300"
    return plans_payload()


# ----------------------------- helpers -----------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _add_months(dt: datetime, months: int) -> datetime:
    y, m = divmod(dt.month - 1 + months, 12)
    year, month = dt.year + y, m + 1
    for day in (dt.day, 30, 29, 28):
        try:
            return dt.replace(year=year, month=month, day=day)
        except ValueError:
            continue
    return dt + timedelta(days=30 * months)


def period_end_from(plan: str, start: Optional[datetime] = None) -> datetime:
    return _add_months(start or _now(), PLAN_MONTHS[plan])


async def _lock_by(conn, where: str, *args):
    return await conn.fetchrow(f"SELECT * FROM subscriptions WHERE {where} FOR UPDATE", *args)


# ----------------------------- checkout -----------------------------
class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    surname: str = Field(min_length=1, max_length=60)
    gsm_number: str = Field(min_length=7, max_length=20)
    identity_number: Optional[str] = Field(default=None, max_length=11)
    address: str = Field(min_length=5, max_length=250)
    city: str = Field(min_length=2, max_length=60)
    country: str = Field(min_length=2, max_length=60)
    zip_code: Optional[str] = Field(default=None, max_length=12)

    @field_validator("gsm_number")
    @classmethod
    def _gsm(cls, v: str) -> str:
        v = re.sub(r"[\s()\-]", "", v)
        if not re.fullmatch(r"\+?\d{7,15}", v):
            raise ValueError("invalid phone number")
        return v if v.startswith("+") else "+" + v

    @field_validator("identity_number")
    @classmethod
    def _identity(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return None
        if not re.fullmatch(r"\d{11}", v):
            raise ValueError("identity_number must be 11 digits")
        return v


class CheckoutIn(BaseModel):
    plan: Literal["pro_monthly", "pro_yearly"]
    currency: Literal["USD", "TRY"]
    customer: CustomerIn

    @model_validator(mode="after")
    def _try_needs_identity(self):
        if self.currency == "TRY" and not self.customer.identity_number:
            raise ValueError("identity_number (11 digits) is required for TRY payments")
        return self


@router.post("/checkout", dependencies=[Depends(limit("billing-checkout", 5, 600))])
async def checkout(body: CheckoutIn, user: Dict[str, Any] = Depends(current_user)):
    ref = plan_refs(body.plan, body.currency)
    if not credentials_configured() or not ref:
        raise HTTPException(status_code=503, detail="Payments are not available for this plan/currency yet")
    conversation_id = uuid.uuid4().hex
    c = body.customer
    full_name = f"{c.name} {c.surname}"
    payload = {
        "callbackUrl": f"{settings.public_base_url}/api/billing/callback",
        "pricingPlanReferenceCode": ref,
        "subscriptionInitialStatus": "ACTIVE",
        "conversationId": conversation_id,
        "locale": "tr" if body.currency == "TRY" else "en",
        "customer": {
            "name": c.name, "surname": c.surname, "email": user["email"], "gsmNumber": c.gsm_number,
            "identityNumber": c.identity_number or PLACEHOLDER_IDENTITY,
            "billingAddress": {"contactName": full_name, "address": c.address, "city": c.city,
                               "country": c.country, **({"zipCode": c.zip_code} if c.zip_code else {})},
            "shippingAddress": {"contactName": full_name, "address": c.address, "city": c.city,
                                "country": c.country, **({"zipCode": c.zip_code} if c.zip_code else {})},
        },
    }
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """INSERT INTO subscriptions (user_id, provider, plan, status, provider_customer_ref)
                   VALUES ($1, $2, $3, 'pending', $4) ON CONFLICT (user_id) DO NOTHING""",
                user["id"], PROVIDER, body.plan, conversation_id)
            row = await _lock_by(conn, "user_id = $1", user["id"])
            if row["status"] in ("active", "past_due"):
                raise HTTPException(status_code=409, detail={"code": "already_subscribed",
                                                              "message": "You already have a subscription"})
            reusable = await _reusable_form(row, body.plan, body.currency)
            if reusable:
                return {"checkout_url": _pay_url(reusable)}
            try:
                res = await iyzico("POST", "/v2/subscription/checkoutform/initialize", payload)
            except IyzicoError:
                raise HTTPException(status_code=502, detail="Payment provider error, please try again")
            token = res.get("token")
            if not token:
                raise HTTPException(status_code=502, detail="Payment provider returned no checkout token")
            await conn.execute(
                """UPDATE subscriptions SET plan = $2, status = 'pending', provider = $3,
                       provider_customer_ref = $4, provider_subscription_ref = $5, updated_at = now()
                   WHERE id = $1""",
                row["id"], body.plan, PROVIDER, conversation_id, PENDING_PREFIX + str(token))
    # iyzico's hosted page (paymentPageUrl / cpp) ignores subscription tokens, so the embeddable form is required.
    await cache.set(FORM_CACHE_PREFIX + str(token), json.dumps(
        {"html": res.get("checkoutFormContent", ""), "locale": payload["locale"], "plan": body.plan,
         "currency": body.currency, "created": _now().timestamp()}), FORM_TTL_S)
    return {"checkout_url": _pay_url(str(token))}


def _pay_url(token: str) -> str:
    return f"/api/billing/pay/{quote(token, safe='')}"


async def _reusable_form(row, plan: str, currency: str) -> Optional[str]:
    """Token of the user's still-payable form for the same plan/currency. Re-opening it (rather than minting a new
    token) keeps one payable checkout per user, so a double click or second tab cannot produce two charges."""
    ref = row["provider_subscription_ref"] or ""
    if row["status"] != "pending" or not ref.startswith(PENDING_PREFIX):
        return None
    token = ref[len(PENDING_PREFIX):]
    cached = await cache.get(FORM_CACHE_PREFIX + token)
    if not cached:
        return None
    form = json.loads(cached)
    fresh = _now().timestamp() - float(form.get("created", 0)) < FORM_REUSE_MAX_AGE_S
    return token if fresh and form.get("plan") == plan and form.get("currency") == currency else None


PAY_PAGE = """<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vaka · {title}</title>
<style>body{{margin:0;background:#f5f2ec;font-family:system-ui,sans-serif;color:#1f2a2a}}
main{{max-width:560px;margin:0 auto;padding:24px 16px}}a{{color:#15695f;font-weight:600}}</style></head>
<body><main><p><a href="/account">&larr; {back}</a></p>
<div id="iyzipay-checkout-form" class="responsive"></div>
{form}</main></body></html>"""


@router.get("/pay/{token}", response_class=HTMLResponse)
async def pay_page(token: str, user: Dict[str, Any] = Depends(current_user)):
    if not re.fullmatch(r"[\w\-.]{8,200}", token):
        raise HTTPException(status_code=404, detail="Checkout not found")
    owner = await db.pool().fetchval(
        "SELECT user_id FROM subscriptions WHERE provider_subscription_ref = $1 AND status = 'pending'",
        PENDING_PREFIX + token)
    cached = await cache.get(FORM_CACHE_PREFIX + token)
    if owner != user["id"] or not cached:
        raise HTTPException(status_code=404, detail="Checkout not found or expired")
    form = json.loads(cached)
    tr = form.get("locale") == "tr"
    html = PAY_PAGE.format(lang="tr" if tr else "en", title="Ödeme" if tr else "Checkout",
                           back="Vazgeç" if tr else "Cancel", form=form.get("html", ""))
    return HTMLResponse(html, headers={"Content-Security-Policy": PAY_PAGE_CSP, "Cache-Control": "no-store"})


# ----------------------------- callback -----------------------------
async def _token_from(request: Request) -> Optional[str]:
    token = request.query_params.get("token")
    if not token and request.method == "POST":
        raw = (await request.body())[:4096].decode("utf-8", "ignore")
        token = (parse_qs(raw).get("token") or [None])[0]
    return token if token and re.fullmatch(r"[\w\-.]{8,200}", token) else None


async def activate_from_token(token: str) -> str:
    """Fetch the checkout result and activate our pending row. Idempotent. Returns 'active' when the user ends up
    subscribed, 'refunded' when iyzico charged a checkout we cannot match (a superseded form from another tab, or a
    plan mismatch) and the money went back, else 'failed'."""
    try:
        res = await iyzico("GET", f"/v2/subscription/checkoutform/{quote(token, safe='')}")
    except IyzicoError:
        return "failed"
    sub_ref = res.get("referenceCode")
    if not sub_ref or str(res.get("subscriptionStatus", "")).upper() != "ACTIVE":
        return "failed"
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            row = await _lock_by(conn, "provider_subscription_ref = $1", PENDING_PREFIX + token)
            if row is None:   # refresh / retry of a processed token, or a paid checkout we no longer track
                done = await conn.fetchrow(
                    "SELECT status FROM subscriptions WHERE provider_subscription_ref = $1", sub_ref)
                if done:
                    return "active" if done["status"] in ("active", "past_due") else "failed"
                orphan = True
            else:
                plan = plan_for_ref(str(res.get("pricingPlanReferenceCode", "")))
                conv = res.get("conversationId")
                orphan = plan is None or plan != row["plan"] or bool(conv and conv != row["provider_customer_ref"])
                if orphan:
                    logger.error("checkout result does not match pending subscription (user=%s)", row["user_id"])
                else:
                    end = period_end_from(plan)
                    await conn.execute(
                        """UPDATE subscriptions SET status = 'active', provider_subscription_ref = $2,
                               provider_customer_ref = $3, cancel_at_period_end = false,
                               current_period_end = GREATEST(COALESCE(current_period_end, $4), $4), updated_at = now()
                           WHERE id = $1""",
                        row["id"], sub_ref, res.get("customerReferenceCode"), end)
                    return "active"
    return "refunded" if orphan and await refund_and_cancel_orphan(str(sub_ref)) else "failed"


@router.api_route("/callback", methods=["GET", "POST"])
async def callback(request: Request):
    token = await _token_from(request)
    outcome = await activate_from_token(token) if token else "failed"
    return RedirectResponse(f"/account?checkout={'success' if outcome == 'active' else outcome}", status_code=303)


# ----------------------------- webhook -----------------------------
def webhook_signature(merchant_id: str, key: str, event_type: str, sub_ref: str, order_ref: str, customer_ref: str) -> str:
    msg = merchant_id + key + event_type + sub_ref + order_ref + customer_ref
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()


def _webhook_key() -> str:
    return settings.iyzico_webhook_secret or settings.iyzico_secret_key


def _merchant_id() -> str:
    return os.environ.get("IYZICO_MERCHANT_ID", "").strip()


def verify_webhook(p: Dict[str, Any], header: Optional[str]) -> bool:
    key, merchant = _webhook_key(), _merchant_id()
    if not key or not merchant:
        return not settings.is_prod and not header   # dev convenience only; production always requires config
    if not header:
        return False
    expected = webhook_signature(merchant, key, str(p.get("iyziEventType", "")), str(p.get("subscriptionReferenceCode", "")),
                                 str(p.get("orderReferenceCode", "")), str(p.get("customerReferenceCode", "")))
    return hmac.compare_digest(expected.encode(), header.strip().lower().encode())


@router.post("/webhook")
async def webhook(request: Request):
    raw = (await request.body())[:65536]
    try:
        p = json.loads(raw)
        if not isinstance(p, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    if not verify_webhook(p, request.headers.get("x-iyz-signature-v3")):
        raise HTTPException(status_code=401, detail="Invalid signature")
    event_type = str(p.get("iyziEventType", ""))
    order_ref = str(p.get("orderReferenceCode", ""))
    sub_ref = str(p.get("subscriptionReferenceCode", ""))
    if not event_type or not order_ref:
        raise HTTPException(status_code=400, detail="Invalid payload")
    status = await apply_order_event(event_type, order_ref, sub_ref, p)
    return {"status": status}


async def apply_order_event(event_type: str, order_ref: str, sub_ref: str, payload: Dict[str, Any]) -> str:
    event_id = order_ref + event_type
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            inserted = await conn.fetchval(
                """INSERT INTO payment_events (provider, event_id, event_type, payload)
                   VALUES ($1, $2, $3, $4) ON CONFLICT (provider, event_id) DO NOTHING RETURNING id""",
                PROVIDER, event_id, event_type, payload)
            if inserted is None:
                return "duplicate"
            if event_type not in ("subscription.order.success", "subscription.order.failure"):
                await conn.execute("UPDATE payment_events SET processed_at = now() WHERE id = $1", inserted)
                return "ignored"
            row = await _lock_by(conn, "provider_subscription_ref = $1", sub_ref) if sub_ref else None
            if row is None:
                # Callback may not have run yet. Roll back the event row so iyzico's retry is processed.
                raise HTTPException(status_code=409, detail="Unknown subscription, retry later")
            if event_type == "subscription.order.success":
                if row["status"] in ("canceled", "expired"):
                    pass   # cancellation is final; a late/in-flight charge never re-grants access
                else:
                    end = period_end_from(row["plan"])
                    await conn.execute(
                        """UPDATE subscriptions SET status = 'active',
                               current_period_end = GREATEST(COALESCE(current_period_end, $2), $2), updated_at = now()
                           WHERE id = $1""", row["id"], end)
            elif row["status"] == "active":
                await conn.execute("UPDATE subscriptions SET status = 'past_due', updated_at = now() WHERE id = $1", row["id"])
            await conn.execute("UPDATE payment_events SET processed_at = now() WHERE id = $1", inserted)
            return "processed"


# ----------------------------- subscription / cancel -----------------------------
@router.get("/subscription")
async def get_subscription(user: Dict[str, Any] = Depends(current_user)):
    row = await db.pool().fetchrow(
        "SELECT status, plan, current_period_end, cancel_at_period_end FROM subscriptions WHERE user_id = $1", user["id"])
    if not row:
        return {"status": "none", "plan": None, "current_period_end": None, "cancel_at_period_end": False}
    return {"status": row["status"], "plan": row["plan"],
            "current_period_end": row["current_period_end"].isoformat() if row["current_period_end"] else None,
            "cancel_at_period_end": row["cancel_at_period_end"]}


@router.post("/cancel", dependencies=[Depends(limit("billing-cancel", 5, 600))])
async def cancel(user: Dict[str, Any] = Depends(current_user)):
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            row = await _lock_by(conn, "user_id = $1", user["id"])
            if row is None or row["status"] in ("pending", "expired"):
                raise HTTPException(status_code=404, detail="No active subscription")
            if row["status"] != "canceled":
                ref = row["provider_subscription_ref"] or ""
                if not ref or ref.startswith(PENDING_PREFIX):
                    raise HTTPException(status_code=409, detail="Subscription is not confirmed yet")
                try:
                    await iyzico("POST", f"/v2/subscription/subscriptions/{quote(ref, safe='')}/cancel")
                except IyzicoError:
                    raise HTTPException(status_code=502, detail="Could not cancel with the payment provider, please retry")
                await conn.execute(
                    "UPDATE subscriptions SET status = 'canceled', cancel_at_period_end = true, updated_at = now() WHERE id = $1",
                    row["id"])
            end = row["current_period_end"]
    return {"status": "canceled", "cancel_at_period_end": True,
            "current_period_end": end.isoformat() if end else None}


# ----------------------------- orphan recovery -----------------------------
def _subscription_record(res: Dict[str, Any]) -> Dict[str, Any]:
    """The detail endpoint answers with a one-item page ({items: [...]}); tolerate a bare record too."""
    items = res.get("items")
    return items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else res


def _charged_payments(record: Dict[str, Any]):
    """(paymentId, price, currency) for every successful charge of an iyzico subscription."""
    for order in record.get("orders") or []:
        for attempt in order.get("paymentAttempts") or []:
            if str(attempt.get("paymentStatus", "")).upper() == "SUCCESS" and attempt.get("paymentId"):
                yield str(attempt["paymentId"]), order.get("price"), order.get("currencyCode")


async def _refund_once(payment_id: str, price: Any, currency: Any, sub_ref: str) -> None:
    """Refund one charge at most once: the payment_events marker commits only if iyzico accepted the refund, and
    its unique key makes a concurrent attempt wait and then skip."""
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            marker = await conn.fetchval(
                """INSERT INTO payment_events (provider, event_id, event_type, payload, processed_at)
                   VALUES ($1, $2, 'refund.orphan', $3, now()) ON CONFLICT (provider, event_id) DO NOTHING RETURNING id""",
                PROVIDER, f"refund:{payment_id}", {"subscriptionReferenceCode": sub_ref, "paymentId": payment_id})
            if marker is None:
                return
            await iyzico("POST", "/v2/payment/refund", {"paymentId": payment_id, "price": price, "currency": currency,
                                                         "conversationId": f"orphan-{sub_ref}", "locale": "en"})


async def refund_and_cancel_orphan(sub_ref: str) -> bool:
    """A charged iyzico subscription with no matching row of ours: give every charge back, then stop renewals.
    Refunds go first so a failure leaves it renewing-and-visible to the sweep, which retries. True when done."""
    try:
        record = _subscription_record(await iyzico("GET", f"/v2/subscription/subscriptions/{quote(sub_ref, safe='')}"))
        for payment_id, price, currency in _charged_payments(record):
            await _refund_once(payment_id, price, currency, sub_ref)
        if str(record.get("subscriptionStatus", "")).upper() in CHARGING_STATUSES:
            await iyzico("POST", f"/v2/subscription/subscriptions/{quote(sub_ref, safe='')}/cancel")
    except IyzicoError as e:
        logger.error("orphan subscription %s not refunded yet (code %s); the sweep retries", sub_ref, e.code)
        return False
    logger.warning("orphan subscription %s refunded and canceled", sub_ref)
    await alerts.send(f"billing-orphan-{sub_ref}", f"Refunded and canceled unmatched iyzico subscription {sub_ref}")
    return True


def _created_at(record: Dict[str, Any]) -> Optional[datetime]:
    raw = record.get("createdDate")
    try:
        return datetime.fromtimestamp(float(raw) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


async def sweep_orphans() -> int:
    """Refund and cancel iyzico subscriptions of our plans that still charge but that no row of ours tracks
    (a paid form whose callback never reached us after a newer checkout replaced it). Returns how many."""
    known = {r["provider_subscription_ref"] for r in await db.pool().fetch(
        "SELECT provider_subscription_ref FROM subscriptions WHERE provider_subscription_ref IS NOT NULL")}
    cutoff = _now() - ORPHAN_GRACE
    fixed = 0
    for page in range(1, ORPHAN_SCAN_MAX_PAGES + 1):
        res = await iyzico("GET", f"/v2/subscription/subscriptions?subscriptionStatus=ACTIVE&page={page}"
                                  f"&count={ORPHAN_SCAN_PAGE_SIZE}")
        items = res.get("items") or []
        for item in items:
            ref, created = str(item.get("referenceCode", "")), _created_at(item)
            if (ref and ref not in known and plan_for_ref(str(item.get("pricingPlanReferenceCode", "")))
                    and str(item.get("subscriptionStatus", "")).upper() in CHARGING_STATUSES
                    and created is not None and created < cutoff):
                fixed += 1 if await refund_and_cancel_orphan(ref) else 0
        if len(items) < ORPHAN_SCAN_PAGE_SIZE:
            break
    return fixed


# ----------------------------- reconciliation -----------------------------
_STATUS_MAP = {"ACTIVE": "active", "UNPAID": "past_due", "CANCELED": "canceled", "EXPIRED": "expired"}


async def _reconcile_one(row) -> bool:
    ref = row["provider_subscription_ref"] or ""
    if ref.startswith(PENDING_PREFIX):
        if _now() - row["updated_at"] > PENDING_MAX_AGE:
            async with db.pool().acquire() as conn:
                async with conn.transaction():
                    await conn.execute("DELETE FROM subscriptions WHERE id = $1 AND status = 'pending' "
                                       "AND provider_subscription_ref = $2", row["id"], ref)
            return True
        return await activate_from_token(ref[len(PENDING_PREFIX):]) == "active"
    if not ref:
        return False
    try:
        res = _subscription_record(await iyzico("GET", f"/v2/subscription/subscriptions/{quote(ref, safe='')}"))
    except IyzicoError:
        return False
    new_status = _STATUS_MAP.get(str(res.get("subscriptionStatus", "")).upper())
    if not new_status:
        return False
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            cur = await _lock_by(conn, "id = $1", row["id"])
            if cur is None or cur["provider_subscription_ref"] != ref:
                return False
            status, end, cancel_flag = cur["status"], cur["current_period_end"], cur["cancel_at_period_end"]
            new_end, new_cancel = end, cancel_flag
            if new_status == "active":
                if status == "canceled":
                    return False   # we cancelled; iyzico may lag, the next run decides
                if end is None or end <= _now():   # renewal webhook missed: roll the period forward
                    base = end or _now()
                    while base <= _now():
                        base = _add_months(base, PLAN_MONTHS[cur["plan"]])
                    new_end = base
            elif new_status == "canceled":
                new_cancel = True
            if (new_status, new_end, new_cancel) == (status, end, cancel_flag):
                return False
            await conn.execute(
                "UPDATE subscriptions SET status = $2, current_period_end = $3, cancel_at_period_end = $4, updated_at = now() WHERE id = $1",
                cur["id"], new_status, new_end, new_cancel)
            return True


async def reconcile_all() -> int:
    """Repair drift between iyzico and our rows (missed callback/webhook). Returns the number of rows changed."""
    if not credentials_configured():
        logger.warning("reconcile skipped: iyzico credentials not configured")
        return 0
    now = _now()
    rows = await db.pool().fetch(
        "SELECT * FROM subscriptions WHERE status IN ('active', 'past_due', 'pending', 'canceled') ORDER BY updated_at LIMIT 500")
    fixed = 0
    for row in rows:
        if now - row["updated_at"] < RECONCILE_MIN_AGE[row["status"]]:
            continue
        if row["status"] == "canceled" and (row["current_period_end"] is None or row["current_period_end"] > now):
            continue
        try:
            fixed += 1 if await _reconcile_one(row) else 0
        except Exception:  # noqa: BLE001 - one bad row must not stop the sweep
            logger.exception("reconcile failed for subscription %s", row["id"])
    # canceled subscriptions whose paid period is over are 'expired' (plan_name_for already ignores them)
    expired = await db.pool().execute(
        "UPDATE subscriptions SET status = 'expired', updated_at = now() "
        "WHERE status = 'canceled' AND current_period_end <= now()")
    fixed += int(expired.split()[-1])
    try:   # after the pending rows above had their chance to claim fresh subscriptions
        fixed += await sweep_orphans()
    except IyzicoError as e:
        logger.error("orphan sweep failed (code %s)", e.code)
    logger.info("billing reconcile finished", extra={"extra_fields": {"fixed": fixed, "scanned": len(rows)}})
    return fixed


async def _cli() -> int:
    from logging_setup import setup
    setup()
    await db.connect()
    try:
        n = await reconcile_all()
        print(f"reconciled {n} subscription(s)")
    finally:
        await db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_cli()))
