"""Billing tests: no network (iyzico is mocked via httpx.MockTransport). DB tests need the dev Postgres."""
import asyncio
import base64
import hashlib
import hmac
import json

import httpx
import pytest

import billing
import plans
from config import settings
from tests.billing_fixtures import (client, future, insert_sub, iyzico_cfg, pool, user)  # noqa: F401

pytestmark = pytest.mark.asyncio

CUSTOMER = {"name": "Ada", "surname": "Lovelace", "gsm_number": "+905551112233", "identity_number": "12345678901",
            "address": "Some Street 1 Istanbul", "city": "Istanbul", "country": "Turkey", "zip_code": "34000"}


def wh(event, order="ORD1", sub="SUB1", cust="CUST1"):
    return {"iyziEventType": event, "orderReferenceCode": order, "subscriptionReferenceCode": sub,
            "customerReferenceCode": cust}


def wh_headers(p, merchant="merchant-1", key="secret-key"):
    return {"X-IYZ-SIGNATURE-V3": billing.webhook_signature(
        merchant, key, p["iyziEventType"], p["subscriptionReferenceCode"], p["orderReferenceCode"],
        p["customerReferenceCode"])}


# ---------- pure ----------
async def test_sign_request_matches_spec():
    h = billing.sign_request("AK", "SK", "/v2/x", b'{"a":1}', rnd="rnd1")
    raw = base64.b64decode(h["Authorization"].split(" ", 1)[1]).decode()
    sig = hmac.new(b"SK", b'rnd1/v2/x{"a":1}', hashlib.sha256).hexdigest()
    assert h["Authorization"].startswith("IYZWSv2 ")
    assert raw == f"apiKey:AK&randomKey:rnd1&signature:{sig}"
    assert h["x-iyzi-rnd"] == "rnd1"


async def test_plans_math(client, iyzico_cfg):
    r = await client.get("/api/billing/plans")
    d = r.json()
    assert r.headers["cache-control"].startswith("public")
    assert d["plans"][0] == {"id": "pro_monthly", "interval": "month", "usd": 9.0, "try": 399.0}
    assert d["plans"][1]["usd"] == 90.0
    assert (d["list_price_yearly_usd"], d["savings_usd"], d["savings_percent"]) == (108.0, 18.0, 17)
    assert d["available"] is True


async def test_plans_unavailable_without_config(client, monkeypatch):
    monkeypatch.setattr(billing, "credentials_configured", lambda: False)
    assert (await client.get("/api/billing/plans")).json()["available"] is False


# ---------- webhook ----------
async def test_webhook_rejects_bad_or_missing_signature(client, iyzico_cfg):
    p = wh("subscription.order.success")
    assert (await client.post("/api/billing/webhook", json=p, headers={"X-IYZ-SIGNATURE-V3": "00"})).status_code == 401
    assert (await client.post("/api/billing/webhook", json=p)).status_code == 401


async def test_webhook_prod_without_config_is_rejected(client, iyzico_cfg, monkeypatch):
    object.__setattr__(settings, "env", "production")
    monkeypatch.delenv("IYZICO_MERCHANT_ID")
    try:
        assert (await client.post("/api/billing/webhook", json=wh("subscription.order.success"))).status_code == 401
    finally:
        object.__setattr__(settings, "env", "development")


async def test_webhook_success_is_idempotent(client, iyzico_cfg, pool, user):
    ref = await insert_sub(pool, user, status="past_due", ref="SUB1", end=future(-1))
    p = wh("subscription.order.success", sub=ref)
    r1 = await client.post("/api/billing/webhook", json=p, headers=wh_headers(p))
    assert r1.status_code == 200 and r1.json()["status"] == "processed"
    row = await pool.fetchrow("SELECT status, current_period_end FROM subscriptions")
    assert row["status"] == "active"
    first_end = row["current_period_end"]
    await pool.execute("UPDATE subscriptions SET current_period_end = $1", future(-1))   # detect a 2nd state change
    r2 = await client.post("/api/billing/webhook", json=p, headers=wh_headers(p))
    assert r2.json()["status"] == "duplicate"
    assert (await pool.fetchval("SELECT current_period_end FROM subscriptions")) < first_end
    assert await pool.fetchval("SELECT count(*) FROM payment_events") == 1


async def test_webhook_concurrent_duplicates_apply_once(client, iyzico_cfg, pool, user):
    await insert_sub(pool, user, status="active", ref="SUB1", end=future(1))
    p = wh("subscription.order.success")
    rs = await asyncio.gather(*[client.post("/api/billing/webhook", json=p, headers=wh_headers(p)) for _ in range(4)])
    assert sorted(r.json()["status"] for r in rs) == ["duplicate"] * 3 + ["processed"]


async def test_webhook_failure_marks_past_due_and_unknown_sub_retries(client, iyzico_cfg, pool, user):
    await insert_sub(pool, user, status="active", ref="SUB1", end=future(5))
    p = wh("subscription.order.failure")
    assert (await client.post("/api/billing/webhook", json=p, headers=wh_headers(p))).status_code == 200
    assert await pool.fetchval("SELECT status FROM subscriptions") == "past_due"
    u = wh("subscription.order.success", order="ORD9", sub="NOPE")
    assert (await client.post("/api/billing/webhook", json=u, headers=wh_headers(u))).status_code == 409
    assert await pool.fetchval("SELECT count(*) FROM payment_events WHERE event_id LIKE 'ORD9%'") == 0   # retry stays possible


# ---------- checkout / callback ----------
def checkout_body(**kw):
    return {"plan": "pro_monthly", "currency": "USD", "customer": {**CUSTOMER, "identity_number": None}, **kw}


async def test_checkout_validation(client, iyzico_cfg):
    bad = checkout_body(currency="TRY")   # TRY needs identity_number
    assert (await client.post("/api/billing/checkout", json=bad)).status_code == 422
    bad2 = checkout_body(customer={**CUSTOMER, "identity_number": "123"})
    assert (await client.post("/api/billing/checkout", json=bad2)).status_code == 422


async def test_checkout_creates_pending_and_returns_hosted_page(client, iyzico_cfg, pool, user):
    # The embeddable form needs inline scripts our CSP forbids, so we always send users to iyzico's hosted page.
    iyzico_cfg.on("POST", "/v2/subscription/checkoutform/initialize",
                  {"status": "success", "token": "tok-1234567", "checkoutFormContent": "<script>x</script>"})
    r = await client.post("/api/billing/checkout", json=checkout_body())
    assert r.status_code == 200
    assert r.json() == {"checkout_url": "https://sandbox-cpp.iyzipay.com/?token=tok-1234567&lang=en"}
    row = await pool.fetchrow("SELECT status, plan, provider_subscription_ref FROM subscriptions")
    assert (row["status"], row["plan"], row["provider_subscription_ref"]) == ("pending", "pro_monthly", "pending:tok-1234567")
    sent = json.loads(iyzico_cfg.calls[0][2])
    assert sent["pricingPlanReferenceCode"] == "PLAN-M-USD" and sent["customer"]["email"] == user["email"]
    assert sent["callbackUrl"].endswith("/api/billing/callback")
    # re-initiating replaces the stale pending row
    iyzico_cfg.on("POST", "/v2/subscription/checkoutform/initialize",
                  {"status": "success", "data": {"token": "tok-7654321", "paymentPageUrl": "https://pay.example/x"}})
    r = await client.post("/api/billing/checkout", json=checkout_body(plan="pro_yearly"))
    assert r.json() == {"checkout_url": "https://pay.example/x"}
    assert await pool.fetchval("SELECT count(*) FROM subscriptions") == 1


async def test_checkout_refuses_double_subscription(client, iyzico_cfg, pool, user):
    await insert_sub(pool, user, status="active", end=future(20))
    r = await client.post("/api/billing/checkout", json=checkout_body())
    assert r.status_code == 409 and iyzico_cfg.calls == []


async def _pending(client, iyzico_cfg, token="tok-1234567"):
    iyzico_cfg.on("POST", "/v2/subscription/checkoutform/initialize", {"status": "success", "token": token, "checkoutFormContent": "x"})
    await client.post("/api/billing/checkout", json=checkout_body())
    iyzico_cfg.on("GET", f"/v2/subscription/checkoutform/{token}", {"status": "success", "data": {
        "referenceCode": "SUB-REAL", "customerReferenceCode": "CUST-REAL", "subscriptionStatus": "ACTIVE",
        "pricingPlanReferenceCode": "PLAN-M-USD"}})


async def test_callback_activates_and_is_idempotent(client, iyzico_cfg, pool, user):
    await _pending(client, iyzico_cfg)
    r = await client.get("/api/billing/callback?token=tok-1234567")
    assert r.status_code == 303 and r.headers["location"] == "/account?checkout=success"
    row = await pool.fetchrow("SELECT status, provider_subscription_ref, current_period_end FROM subscriptions")
    assert row["status"] == "active" and row["provider_subscription_ref"] == "SUB-REAL" and row["current_period_end"] > future(27)
    end = row["current_period_end"]
    for method in ("get", "post"):   # refresh / iyzico POST
        r = await (client.get("/api/billing/callback?token=tok-1234567") if method == "get" else
                   client.post("/api/billing/callback", content="token=tok-1234567",
                               headers={"content-type": "application/x-www-form-urlencoded"}))
        assert r.headers["location"] == "/account?checkout=success"
    assert await pool.fetchval("SELECT current_period_end FROM subscriptions") == end


async def test_callback_rejects_unknown_token_and_mismatch(client, iyzico_cfg, pool, user):
    assert (await client.get("/api/billing/callback")).headers["location"].endswith("failed")
    await _pending(client, iyzico_cfg)
    iyzico_cfg.on("GET", "/v2/subscription/checkoutform/tok-1234567", {"status": "success", "data": {
        "referenceCode": "SUB-REAL", "subscriptionStatus": "ACTIVE", "pricingPlanReferenceCode": "PLAN-Y-USD"}})
    assert (await client.get("/api/billing/callback?token=tok-1234567")).headers["location"].endswith("failed")
    assert await pool.fetchval("SELECT status FROM subscriptions") == "pending"
    iyzico_cfg.on("GET", "/v2/subscription/checkoutform/tok-unknown1", {"status": "success", "data": {
        "referenceCode": "SUB-X", "subscriptionStatus": "ACTIVE", "pricingPlanReferenceCode": "PLAN-M-USD"}})
    assert (await client.get("/api/billing/callback?token=tok-unknown1")).headers["location"].endswith("failed")


# ---------- cancel ----------
async def test_cancel_keeps_access_until_period_end(client, iyzico_cfg, pool, user):
    ref = await insert_sub(pool, user, status="active", end=future(12))
    iyzico_cfg.on("POST", f"/v2/subscription/subscriptions/{ref}/cancel", {"status": "success"})
    assert await plans.plan_name_for(user) == "pro"
    r = await client.post("/api/billing/cancel")
    assert r.status_code == 200 and r.json()["cancel_at_period_end"] is True
    assert (await client.post("/api/billing/cancel")).status_code == 200   # idempotent
    assert iyzico_cfg.count("POST", f"/v2/subscription/subscriptions/{ref}/cancel") == 1
    assert await plans.plan_name_for(user) == "pro"
    sub = (await client.get("/api/billing/subscription")).json()
    assert sub["status"] == "canceled" and sub["cancel_at_period_end"] is True
    await pool.execute("UPDATE subscriptions SET current_period_end = $1", future(-1))
    assert await plans.plan_name_for(user) == "free"


async def test_cancel_provider_failure_changes_nothing(client, iyzico_cfg, pool, user):
    await insert_sub(pool, user, status="active", end=future(12))
    assert (await client.post("/api/billing/cancel")).status_code == 502
    assert await pool.fetchval("SELECT status FROM subscriptions") == "active"


async def test_subscription_none(client, iyzico_cfg):
    assert (await client.get("/api/billing/subscription")).json()["status"] == "none"


# ---------- reconcile ----------
async def test_reconcile_repairs_missed_renewal_and_expires(client, iyzico_cfg, pool, user):
    ref = await insert_sub(pool, user, status="past_due", ref="SUB-R", end=future(-2))
    await pool.execute("UPDATE subscriptions SET updated_at = now() - interval '2 days'")
    iyzico_cfg.on("GET", f"/v2/subscription/subscriptions/{ref}", {"status": "success", "data": {"subscriptionStatus": "ACTIVE"}})
    assert await billing.reconcile_all() == 1
    row = await pool.fetchrow("SELECT status, current_period_end FROM subscriptions")
    assert row["status"] == "active" and row["current_period_end"] > future(0)
    assert await billing.reconcile_all() == 0   # nothing left to fix (fresh updated_at)
