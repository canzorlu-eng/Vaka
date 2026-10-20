"""One-time, idempotent iyzico catalogue setup: product "Vaka Pro" + four recurring pricing plans
(monthly/yearly x USD/TRY). Existing products/plans are looked up by name, so re-running never duplicates.
Usage (from backend/):  .venv/bin/python scripts/iyzico_setup.py [--dry-run]
Reads IYZICO_API_KEY / IYZICO_SECRET_KEY / IYZICO_BASE_URL and PRICE_* from the environment/.env (never printed)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import billing  # noqa: E402
from config import settings  # noqa: E402

PRODUCT_NAME = "Vaka Pro"
PAGE_SIZE = 100


def plan_specs():
    s = settings
    return [  # (env var, plan name, interval, currency, price)
        ("IYZICO_PLAN_MONTHLY_USD", "Vaka Pro Monthly USD", "MONTHLY", "USD", s.price_monthly_usd),
        ("IYZICO_PLAN_YEARLY_USD", "Vaka Pro Yearly USD", "YEARLY", "USD", s.price_yearly_usd),
        ("IYZICO_PLAN_MONTHLY_TRY", "Vaka Pro Monthly TRY", "MONTHLY", "TRY", s.price_monthly_try),
        ("IYZICO_PLAN_YEARLY_TRY", "Vaka Pro Yearly TRY", "YEARLY", "TRY", s.price_yearly_try),
    ]


def _items(res):
    for key in ("items", "content", "data"):
        if isinstance(res.get(key), list):
            return res[key]
    return []


async def find_product():
    for item in _items(await billing.iyzico("GET", f"/v2/subscription/products?page=1&count={PAGE_SIZE}")):
        if item.get("name") == PRODUCT_NAME:
            return item.get("referenceCode")
    return None


async def existing_plans(product_ref):
    res = await billing.iyzico("GET", f"/v2/subscription/products/{product_ref}/pricing-plans?page=1&count={PAGE_SIZE}")
    return {i.get("name"): i for i in _items(res)}


async def main(dry_run: bool) -> int:
    if not billing.credentials_configured():
        print("IYZICO_API_KEY / IYZICO_SECRET_KEY are not set.", file=sys.stderr)
        return 1
    print(f"iyzico endpoint: {settings.iyzico_base_url}", file=sys.stderr)
    product = await find_product()
    if product:
        print(f"product '{PRODUCT_NAME}' exists", file=sys.stderr)
    elif dry_run:
        print(f"[dry-run] would create product '{PRODUCT_NAME}'", file=sys.stderr)
    else:
        product = (await billing.iyzico("POST", "/v2/subscription/products", {
            "name": PRODUCT_NAME, "description": "Vaka Pro subscription", "locale": "en"})).get("referenceCode")
        print(f"created product '{PRODUCT_NAME}'", file=sys.stderr)
    have = await existing_plans(product) if product else {}
    lines = []
    for env, name, interval, currency, price in plan_specs():
        plan = have.get(name)
        if plan:
            if str(plan.get("currencyCode")) != currency or float(plan.get("price", price)) != float(price):
                print(f"WARNING: existing plan '{name}' differs from configured price/currency; iyzico plans are immutable, "
                      f"create a new plan with a new name if the price changed", file=sys.stderr)
            ref = plan.get("referenceCode")
        elif dry_run or not product:
            print(f"[dry-run] would create plan '{name}' ({price} {currency}/{interval})", file=sys.stderr)
            ref = "<to-be-created>"
        else:
            created = await billing.iyzico("POST", f"/v2/subscription/products/{product}/pricing-plans", {
                "name": name, "price": price, "currencyCode": currency, "paymentInterval": interval,
                "paymentIntervalCount": 1, "planPaymentType": "RECURRING", "locale": "en"})
            ref = created.get("referenceCode")
            print(f"created plan '{name}'", file=sys.stderr)
        lines.append(f"{env}={ref}")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main("--dry-run" in sys.argv)))
    except billing.IyzicoError as e:
        print(f"iyzico error: {e} (code {e.code})", file=sys.stderr)
        raise SystemExit(2)
