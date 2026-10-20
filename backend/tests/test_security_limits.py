"""Rate limits, plan quotas and the daily AI budget cap."""
import uuid

import pytest
from fastapi import HTTPException

import cache
import db
import llm
import repo
import usage
from conftest import CASE_ID


async def test_per_route_limit_returns_429_with_retry_after(world, user_a):
    # /api/tts allows 40 calls / minute per user; plan "free" answers cheaply without any provider call
    for i in range(40):
        r = await user_a.post("/api/tts", {"text": "merhaba"})
        assert r.status_code == 200, i
    r = await user_a.post("/api/tts", {"text": "merhaba"})
    assert r.status_code == 429
    assert 1 <= int(r.headers["retry-after"]) <= 60


async def test_limits_are_per_user_not_shared(world, user_a, user_b):
    for _ in range(41):
        await user_a.post("/api/tts", {"text": "x"})
    assert (await user_a.post("/api/tts", {"text": "x"})).status_code == 429
    assert (await user_b.post("/api/tts", {"text": "x"})).status_code == 200


async def test_limit_windows_are_isolated_by_route(world, user_a):
    for _ in range(41):
        await user_a.post("/api/tts", {"text": "x"})
    assert (await user_a.get("/api/sessions")).status_code == 200


async def test_session_creation_limit(world, user_a):
    await world.subscribe(user_a.id)  # pro: quota (60) is not the binding constraint
    codes = [(await user_a.post("/api/sessions", {"case_id": CASE_ID, "lang": "tr"})).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429


async def test_ip_scoped_limit_for_login_endpoint(world):
    for _ in range(20):
        assert (await world.anon.get("/api/auth/google/login")).status_code == 302
    r = await world.anon.get("/api/auth/google/login")
    assert r.status_code == 429 and "retry-after" in r.headers


async def test_global_per_ip_limit(world):
    await cache.set("rl:global:127.0.0.1", "300", 60)
    r = await world.anon.get("/api/topics")
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert r.headers["x-content-type-options"] == "nosniff"
    # health endpoint is exempt so the platform health check never trips the limiter
    assert (await world.anon.get("/api/health")).status_code == 200


async def test_global_limit_counts_every_api_request(world):
    for _ in range(3):
        await world.anon.get("/api/demo")
    assert await cache.get_int("rl:global:127.0.0.1") == 3


# ----------------------------- plan quotas -----------------------------
async def test_free_plan_session_quota_is_three_per_month(world, user_a):
    for _ in range(3):
        assert (await user_a.post("/api/sessions", {"case_id": CASE_ID, "lang": "tr"})).status_code == 200
    r = await user_a.post("/api/sessions", {"case_id": CASE_ID, "lang": "tr"})
    assert r.status_code == 402
    assert r.json()["detail"] == {"code": "quota_exceeded", "plan": "free", "limit": 3, "used": 3}
    me = (await user_a.get("/api/auth/me")).json()
    assert me["plan"] == "free" and me["used"]["sessions_this_month"] == 3


async def test_quota_is_per_user(world, user_a, user_b):
    for _ in range(3):
        await world.new_session(user_a)
    assert (await user_b.post("/api/sessions", {"case_id": CASE_ID, "lang": "tr"})).status_code == 200


async def test_old_sessions_do_not_count_toward_this_months_quota(world, user_a):
    for _ in range(3):
        await world.new_session(user_a)
    await db.pool().execute("UPDATE case_sessions SET created_at = now() - interval '40 days' WHERE user_id = $1", user_a.id)
    assert (await user_a.post("/api/sessions", {"case_id": CASE_ID, "lang": "tr"})).status_code == 200


@pytest.mark.parametrize("kind", ["pro", "admin"])
async def test_pro_and_admin_get_larger_quota(world, kind):
    actor = await world.make_user(plan="pro") if kind == "pro" else await world.make_user(role="admin")
    for _ in range(3):
        await world.new_session(actor)
    r = await actor.post("/api/sessions", {"case_id": CASE_ID, "lang": "tr"})
    assert r.status_code == 200
    me = (await actor.get("/api/auth/me")).json()
    assert me["plan"] == "pro" and me["limits"]["sessions_per_month"] == 60
    # fill to the pro cap directly, then the API refuses with the pro numbers
    existing = await world.count("case_sessions", "user_id = $1", actor.id)
    for i in range(60 - existing):
        await repo.insert_session(actor.id, {"id": str(uuid.uuid4()), "case_id": CASE_ID, "lang": "tr", "ended": False})
    r = await actor.post("/api/sessions", {"case_id": CASE_ID, "lang": "tr"})
    assert r.status_code == 402 and r.json()["detail"]["limit"] == 60 and r.json()["detail"]["plan"] == "pro"


async def test_canceled_subscription_keeps_pro_until_period_end_then_reverts(world, user_a):
    await world.subscribe(user_a.id, "canceled")  # period_end is 30 days ahead
    assert (await user_a.get("/api/auth/me")).json()["plan"] == "pro"
    await db.pool().execute("UPDATE subscriptions SET current_period_end = now() - interval '1 day' WHERE user_id = $1", user_a.id)
    assert (await user_a.get("/api/auth/me")).json()["plan"] == "free"
    for status in ("expired", "pending"):
        await world.subscribe(user_a.id, status)
        assert (await user_a.get("/api/auth/me")).json()["plan"] == "free"


async def test_ai_case_generation_on_free_plan_requires_upgrade(world, fake_llm, user_a):
    r = await user_a.post("/api/cases/generate", {"topic": "endodontics", "lang": "en"},
                          headers={"Idempotency-Key": "free-plan-key-1"})
    assert r.status_code == 402
    assert r.json()["detail"]["code"] == "upgrade_required" and r.json()["detail"]["plan"] == "free"
    assert await world.count("jobs") == 0 and fake_llm.count() == 0


async def test_generation_quota_for_pro_and_idempotent_retry_after_quota(world, fake_llm):
    pro = await world.make_user(plan="pro")
    first = await pro.post("/api/cases/generate", {"topic": "endodontics"}, headers={"Idempotency-Key": "pro-key-0001"})
    assert first.status_code == 202
    for i in range(9):
        await jobs_insert(pro.id, f"fill-{i:04d}-key")
    over = await pro.post("/api/cases/generate", {"topic": "endodontics"}, headers={"Idempotency-Key": "pro-key-over1"})
    assert over.status_code == 402 and over.json()["detail"]["code"] == "quota_exceeded"
    assert over.json()["detail"]["limit"] == 10
    again = await pro.post("/api/cases/generate", {"topic": "endodontics"}, headers={"Idempotency-Key": "pro-key-0001"})
    assert again.status_code == 202 and again.json()["job_id"] == first.json()["job_id"]


async def jobs_insert(user_id, key):
    import jobs
    await jobs.enqueue(user_id, "case_generation", {"topic": "endodontics"}, key)


async def test_generation_input_validation(world, fake_llm):
    pro = await world.make_user(plan="pro")
    h = {"Idempotency-Key": "valid-key-1234"}
    assert (await pro.post("/api/cases/generate", {"topic": "nope"}, headers=h)).status_code == 400
    assert (await pro.post("/api/cases/generate", {"topic": "endodontics"}, headers={"Idempotency-Key": "bad key!"})).status_code == 400
    assert (await pro.post("/api/cases/generate", {"topic": "endodontics"}, headers={"Idempotency-Key": "short"})).status_code == 400
    assert (await pro.post("/api/cases/generate", {"topic": "endodontics"})).status_code == 422
    assert (await pro.post("/api/cases/generate", {"topic": "endodontics", "lang": "de"}, headers=h)).status_code == 422
    assert await world.count("jobs") == 0


async def test_generation_unavailable_without_provider(world, monkeypatch):
    monkeypatch.setattr(llm, "llm_available", lambda: False)
    pro = await world.make_user(plan="pro")
    r = await pro.post("/api/cases/generate", {"topic": "endodontics"}, headers={"Idempotency-Key": "valid-key-1234"})
    assert r.status_code == 503


async def test_tts_is_pro_only(world, fake_llm, user_a):
    assert (await user_a.post("/api/tts", {"text": "hello"})).json() == {"audio": None, "reason": "plan"}


# ----------------------------- daily AI budget -----------------------------
async def _spend(user_id, usd):
    await usage.record(user_id, "chat", "gemini", "gemini-test", input_tokens=1, output_tokens=1, cost_usd=usd)


async def test_budget_cap_blocks_free_user_over_cap(world, user_a):
    await llm.enforce_budget(user_a.user)  # no spend yet
    await _spend(user_a.id, 0.04)
    await llm.enforce_budget(user_a.user)  # just under the cap
    await _spend(user_a.id, 0.01)
    with pytest.raises(HTTPException) as exc:
        await llm.enforce_budget(user_a.user)
    assert exc.value.status_code == 429 and exc.value.detail == "daily_ai_budget_reached"
    assert exc.value.headers["Retry-After"] == "3600"


async def test_budget_cap_is_per_user_and_plan_specific(world, user_a, user_b):
    pro = await world.make_user(plan="pro")
    await _spend(user_a.id, 0.5)
    await _spend(pro.id, 0.5)  # over the free daily cap (0.05) but under the pro cap (1.50)
    await llm.enforce_budget(user_b.user)
    await llm.enforce_budget(pro.user)
    with pytest.raises(HTTPException):
        await llm.enforce_budget(user_a.user)
    await _spend(pro.id, 1.0)
    with pytest.raises(HTTPException):
        await llm.enforce_budget(pro.user)


async def test_old_spend_does_not_count(world, user_a):
    await _spend(user_a.id, 5)
    await db.pool().execute("UPDATE llm_usage SET created_at = now() - interval '40 days'")
    await llm.enforce_budget(user_a.user)


async def test_chat_endpoint_returns_429_when_budget_exhausted(world, monkeypatch, user_a):
    monkeypatch.setattr(llm, "llm_available", lambda: True)  # real llm_call: must stop at the budget check, pre-provider
    sid = await world.new_session(user_a)
    await _spend(user_a.id, 1.0)
    r = await user_a.post(f"/api/sessions/{sid}/message", {"text": "agri var mi"})
    assert r.status_code == 429 and r.json()["detail"] == "daily_ai_budget_reached"
    assert (await user_a.get(f"/api/sessions/{sid}")).json()["transcript"] == []


async def test_concurrent_ai_slot_cap_per_user(world, user_a):
    held = []
    async with llm.slot(user_a.id):
        async with llm.slot(user_a.id):
            with pytest.raises(HTTPException) as exc:
                async with llm.slot(user_a.id):
                    held.append(1)
            assert exc.value.status_code == 429
    async with llm.slot(user_a.id):  # slots are released
        pass
    assert not held
