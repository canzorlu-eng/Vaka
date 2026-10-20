"""Self-contained fixtures for tests/test_billing.py (no dependency on conftest.py).
DB tests need the dev Postgres and a migrated throwaway database (BILLING_TEST_DATABASE_URL)."""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

TEST_DB_URL = os.environ.get("BILLING_TEST_DATABASE_URL", "postgresql://vaka:vaka@localhost:55432/vaka_billing_test")


class FakeIyzico:
    """httpx.MockTransport handler: records calls, returns canned iyzico responses keyed by (method, path)."""

    def __init__(self):
        self.calls = []
        self.routes = {}

    def on(self, method, path, doc):
        self.routes[(method, path)] = doc

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path, request.content, dict(request.headers)))
        doc = self.routes.get((request.method, request.url.path))
        if doc is None:
            return httpx.Response(404, json={"status": "failure", "errorCode": "404", "errorMessage": "no route"})
        return httpx.Response(200, json=doc)

    def count(self, method, path):
        return sum(1 for c in self.calls if (c[0], c[1]) == (method, path))


@pytest_asyncio.fixture
async def pool():
    import db
    try:
        p = await asyncpg.create_pool(TEST_DB_URL, min_size=1, max_size=5)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"test database unavailable: {e!r}")
    await p.close()

    async def init(conn):
        await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

    p = await asyncpg.create_pool(TEST_DB_URL, init=init, min_size=1, max_size=8)
    await p.execute("TRUNCATE users, payment_events CASCADE")
    db._pool = p
    yield p
    db._pool = None
    await p.close()


@pytest_asyncio.fixture
async def user(pool):
    uid = uuid.uuid4()
    await pool.execute("INSERT INTO users (id, google_sub, email, role) VALUES ($1, $2, $3, 'user')",
                       uid, f"sub-{uid}", f"{uid.hex[:8]}@example.com")
    return {"id": uid, "email": f"{uid.hex[:8]}@example.com", "role": "user"}


@pytest.fixture
def iyzico_cfg(monkeypatch):
    """Configured sandbox credentials + plan refs, mocked transport. Returns the FakeIyzico."""
    import billing
    from config import settings
    overrides = dict(iyzico_api_key="api-key", iyzico_secret_key="secret-key", iyzico_webhook_secret="",
                     iyzico_plan_monthly_usd="PLAN-M-USD", iyzico_plan_yearly_usd="PLAN-Y-USD",
                     iyzico_plan_monthly_try="PLAN-M-TRY", iyzico_plan_yearly_try="PLAN-Y-TRY",
                     iyzico_base_url="https://sandbox-api.iyzipay.com", env="development")
    saved = {k: getattr(settings, k) for k in overrides}
    for k, v in overrides.items():
        object.__setattr__(settings, k, v)   # Settings is a frozen dataclass
    fake = FakeIyzico()
    monkeypatch.setattr(billing, "_TRANSPORT", httpx.MockTransport(fake))
    monkeypatch.setenv("IYZICO_MERCHANT_ID", "merchant-1")
    yield fake
    for k, v in saved.items():
        object.__setattr__(settings, k, v)


@pytest_asyncio.fixture
async def client(pool, user):
    import billing
    import cache
    from auth import current_user
    cache._mem.clear()   # rate-limit counters are per-IP in tests
    app = FastAPI()
    app.include_router(billing.router)
    app.dependency_overrides[current_user] = lambda: user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


def future(days=10):
    return datetime.now(timezone.utc) + timedelta(days=days)


async def insert_sub(pool, user, status="active", plan="pro_monthly", ref=None, end=None, cancel=False):
    ref = ref or f"SUB-{uuid.uuid4().hex[:8]}"
    await pool.execute(
        """INSERT INTO subscriptions (user_id, plan, status, provider_subscription_ref, current_period_end, cancel_at_period_end)
           VALUES ($1, $2, $3, $4, $5, $6)""", user["id"], plan, status, ref, end, cancel)
    return ref
