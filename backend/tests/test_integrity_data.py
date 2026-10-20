"""Data integrity: concurrency, idempotent scoring, cascades, account deletion/export, unique constraints."""
import asyncio
import uuid

import asyncpg
import pytest

import db
import jobs
import repo
import usage
from conftest import CASE_ID


async def _chat(actor, sid, text):
    return await actor.post(f"/api/sessions/{sid}/message", {"text": text})


async def test_parallel_scoring_creates_one_report_and_one_llm_run(world, fake_llm, user_a):
    sid = await world.new_session(user_a)
    await _chat(user_a, sid, "Ağrınız ne zaman başladı?")
    fake_llm.calls.clear()
    results = await asyncio.gather(*[user_a.post(f"/api/sessions/{sid}/score") for _ in range(10)])
    assert [r.status_code for r in results] == [200] * 10
    assert await world.count("case_reports", "session_id = $1", uuid.UUID(sid)) == 1
    assert len({r.text for r in results}) == 1, "all callers must receive the identical stored report"
    assert fake_llm.count("narrative") == 1, "scoring must not pay for the LLM more than once"
    assert fake_llm.count("coverage") <= 1
    stored = await repo.get_report(sid, user_a.id)
    assert stored == results[0].json()
    assert (await repo.get_session(sid, user_a.id))["ended"] is True


async def test_repeated_scoring_is_idempotent(world, fake_llm, user_a):
    sid = await world.new_session(user_a)
    first = (await user_a.post(f"/api/sessions/{sid}/score")).json()
    calls = fake_llm.count()
    second = (await user_a.post(f"/api/sessions/{sid}/score")).json()
    assert first == second and fake_llm.count() == calls
    assert await world.count("case_reports") == 1


async def test_score_lock_is_released_after_failure(world, fake_llm, user_a):
    sid = await world.new_session(user_a)
    fake_llm.replies["narrative"] = RuntimeError("provider down")
    r = await user_a.post(f"/api/sessions/{sid}/score")
    assert r.status_code == 500
    fake_llm.replies["narrative"] = "recovered"
    ok = await user_a.post(f"/api/sessions/{sid}/score")
    assert ok.status_code == 200 and ok.json()["narrative"] == "recovered"


async def test_score_saves_report_only_for_own_user_and_case(world, fake_llm, user_a):
    sid = await world.new_session(user_a)
    await user_a.post(f"/api/sessions/{sid}/score")
    row = await db.pool().fetchrow("SELECT user_id, case_id, total, grade FROM case_reports")
    assert row["user_id"] == user_a.id and row["case_id"] == CASE_ID and 0 <= row["total"] <= 100


async def test_parallel_chat_messages_lose_no_transcript_entries(world, fake_llm, user_a):
    sid = await world.new_session(user_a)
    texts = [f"question-{i}" for i in range(10)]
    results = await asyncio.gather(*[_chat(user_a, sid, t) for t in texts])
    assert [r.status_code for r in results] == [200] * 10
    transcript = (await repo.get_session(sid, user_a.id))["transcript"]
    assert len(transcript) == 20
    assert sorted(m["text"] for m in transcript if m["role"] == "student") == sorted(texts)
    assert sum(1 for m in transcript if m["role"] == "patient") == 10


async def test_parallel_exam_and_commit_updates_do_not_clobber_each_other(world, user_a):
    sid = await world.new_session(user_a)
    from case_store import CASES
    exams = [a["id"] for a in CASES[0]["exam_actions"]][:3]
    await asyncio.gather(*[user_a.post(f"/api/sessions/{sid}/exam", {"action_id": e}) for e in exams],
                         user_a.post(f"/api/sessions/{sid}/commit", {"diagnosis_id": "d-x"}),
                         user_a.post(f"/api/sessions/{sid}/commit", {"treatment_id": "t-x"}))
    s = await repo.get_session(sid, user_a.id)
    assert sorted(s["exams_done"]) == sorted(exams)
    assert s["diagnosis_id"] == "d-x" and s["treatment_id"] == "t-x"


async def test_update_session_is_isolated_and_atomic(world, user_a):
    sid = await world.new_session(user_a)

    def bump(cur):
        return {**cur, "counter": cur.get("counter", 0) + 1}

    await asyncio.gather(*[repo.update_session(sid, user_a.id, bump) for _ in range(10)])
    assert (await repo.get_session(sid, user_a.id))["counter"] == 10
    assert await repo.update_session(str(uuid.uuid4()), user_a.id, bump) is None
    assert await repo.update_session("not-a-uuid", user_a.id, bump) is None


async def test_update_session_does_not_mutate_stored_copy_on_error(world, user_a):
    sid = await world.new_session(user_a)

    def explode(cur):
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await repo.update_session(sid, user_a.id, explode)
    assert (await repo.get_session(sid, user_a.id))["phase"] == "anamnez"


async def test_ended_session_rejects_further_chat_and_commit(world, fake_llm, user_a):
    sid = await world.new_session(user_a)
    await user_a.post(f"/api/sessions/{sid}/score")
    assert (await _chat(user_a, sid, "late question")).status_code == 409
    assert (await user_a.post(f"/api/sessions/{sid}/commit", {"diagnosis_id": "x"})).status_code == 409


# ----------------------------- cascades -----------------------------
async def _populate(world, fake_llm, actor):
    sid = await world.new_session(actor)
    await actor.post(f"/api/sessions/{sid}/score")
    await jobs.enqueue(actor.id, "case_generation", {"topic": "endodontics"}, "cascade-key-1")
    await world.add_ai_case(actor.id)
    await usage.record(actor.id, "chat", "gemini", "m", cost_usd=0.01)
    await world.subscribe(actor.id, "canceled")


async def test_deleting_user_cascades_but_keeps_anonymised_usage(world, fake_llm, user_a, user_b):
    await _populate(world, fake_llm, user_a)
    await _populate(world, fake_llm, user_b)
    usage_before = await world.count("llm_usage")
    assert usage_before >= 2
    await repo.delete_user(user_a.id)
    for table, col in (("auth_sessions", "user_id"), ("case_sessions", "user_id"), ("case_reports", "user_id"),
                       ("jobs", "user_id"), ("ai_cases", "created_by"), ("subscriptions", "user_id")):
        assert await world.count(table, f"{col} = $1", user_a.id) == 0, table
        assert await world.count(table, f"{col} = $1", user_b.id) >= 1, f"{table} of the other user must survive"
    assert await world.count("llm_usage") == usage_before, "cost ledger rows are kept"
    assert await world.count("llm_usage", "user_id IS NULL") >= 1
    assert await world.count("llm_usage", "user_id = $1", user_a.id) == 0


async def test_deleting_session_cascades_report(world, fake_llm, user_a):
    sid = await world.new_session(user_a)
    await user_a.post(f"/api/sessions/{sid}/score")
    await db.pool().execute("DELETE FROM case_sessions WHERE id = $1", uuid.UUID(sid))
    assert await world.count("case_reports") == 0


async def test_report_requires_existing_session(world, user_a):
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await repo.save_report(str(uuid.uuid4()), user_a.id, CASE_ID, {"total": 1, "grade": "F"})


# ----------------------------- account deletion & export -----------------------------
async def test_delete_account_requires_confirmation_text(world, user_a):
    # the route allows 3 attempts per hour, so exercise three distinct failure modes
    assert (await user_a.delete("/api/me", {"confirm": "delete"})).status_code == 400
    assert (await user_a.delete("/api/me", {})).status_code == 422
    assert (await user_a.delete("/api/me")).status_code == 422
    assert await world.count("users") == 1


async def test_delete_account_success_removes_everything_and_signs_out(world, fake_llm, user_a, user_b):
    await _populate(world, fake_llm, user_a)
    await db.pool().execute("UPDATE subscriptions SET status = 'expired' WHERE user_id = $1", user_a.id)
    r = await user_a.delete("/api/me", {"confirm": "DELETE"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert await world.count("users", "id = $1", user_a.id) == 0
    assert (await user_a.get("/api/sessions")).status_code == 401
    assert (await user_b.get("/api/sessions")).status_code == 200


@pytest.mark.parametrize("status", ["active", "past_due", "pending"])
async def test_delete_account_blocked_by_live_subscription(world, user_a, status):
    await world.subscribe(user_a.id, status)
    r = await user_a.delete("/api/me", {"confirm": "DELETE"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "active_subscription"
    assert await world.count("users", "id = $1", user_a.id) == 1


async def test_export_contains_only_callers_data(world, fake_llm, user_a, user_b):
    sid_a = await world.new_session(user_a)
    await _chat(user_a, sid_a, "ALICE-SECRET-MARKER")
    await user_a.post(f"/api/sessions/{sid_a}/score")
    sid_b = await world.new_session(user_b)
    await _chat(user_b, sid_b, "BOB-SECRET-MARKER")
    await user_b.post(f"/api/sessions/{sid_b}/score")

    out = (await user_a.get("/api/me/export")).json()
    assert out["user"]["email"] == "alice@example.com" and "google_sub" not in out["user"]
    assert [s["id"] for s in out["sessions"]] == [sid_a]
    assert [r["session_id"] for r in out["reports"]] == [sid_a]
    blob = str(out)
    assert "BOB-SECRET-MARKER" not in blob and "bob@example.com" not in blob and sid_b not in blob
    assert "ALICE-SECRET-MARKER" in blob


async def test_export_requires_auth_and_is_rate_limited(world, user_a):
    assert (await world.anon.get("/api/me/export")).status_code == 401
    codes = [(await user_a.get("/api/me/export")).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]


# ----------------------------- constraints -----------------------------
async def test_user_email_is_unique_case_insensitively(world):
    await repo.upsert_google_user("sub-1", "Dup@Example.com", True, None, None, [])
    with pytest.raises(asyncpg.UniqueViolationError):
        await repo.upsert_google_user("sub-2", "dup@example.COM", True, None, None, [])
    assert await world.count("users") == 1


async def test_upsert_same_google_sub_updates_instead_of_duplicating(world):
    a = await repo.upsert_google_user("sub-9", "n@example.com", True, "Old", None, [])
    b = await repo.upsert_google_user("sub-9", "n@example.com", True, "New", None, [])
    assert a["id"] == b["id"] and b["name"] == "New" and await world.count("users") == 1


async def test_admin_role_is_assigned_case_insensitively_and_never_silently_revoked(world):
    admin = await repo.upsert_google_user("sub-a", "Boss@Example.com", True, None, None, ["boss@example.com"])
    assert admin["role"] == "admin"
    again = await repo.upsert_google_user("sub-a", "Boss@Example.com", True, None, None, [])
    assert again["role"] == "admin"


async def test_job_idempotency_is_scoped_per_user_and_kind(world, user_a, user_b):
    j1, c1 = await jobs.enqueue(user_a.id, "case_generation", {}, "same-key-123")
    j2, c2 = await jobs.enqueue(user_a.id, "case_generation", {"different": 1}, "same-key-123")
    j3, c3 = await jobs.enqueue(user_b.id, "case_generation", {}, "same-key-123")
    j4, c4 = await jobs.enqueue(user_a.id, "other_kind", {}, "same-key-123")
    assert (c1, c2, c3, c4) == (True, False, True, True)
    assert j1["id"] == j2["id"] and len({j1["id"], j3["id"], j4["id"]}) == 3
    assert await world.count("jobs") == 3


async def test_parallel_enqueue_with_same_key_creates_one_job(world, user_a):
    results = await asyncio.gather(*[jobs.enqueue(user_a.id, "case_generation", {}, "race-key-0001") for _ in range(10)])
    assert len({j["id"] for j, _ in results}) == 1 and sum(created for _, created in results) == 1
    assert await world.count("jobs") == 1


async def test_check_constraints(world, user_a):
    with pytest.raises(asyncpg.CheckViolationError):
        await db.pool().execute(
            "INSERT INTO case_sessions (id, user_id, case_id, lang, data) VALUES ($1, $2, 'c', 'xx', '{}')",
            uuid.uuid4(), user_a.id)
    job, _ = await jobs.enqueue(user_a.id, "case_generation", {}, "check-key-0001")
    with pytest.raises(asyncpg.CheckViolationError):
        await db.pool().execute("UPDATE jobs SET progress = 150 WHERE id = $1", job["id"])
    with pytest.raises(asyncpg.CheckViolationError):
        await db.pool().execute("UPDATE jobs SET status = 'weird' WHERE id = $1", job["id"])


async def test_late_scorer_that_missed_the_report_does_not_pay_for_the_llm_again(world, fake_llm, user_a, monkeypatch):
    """Deterministic interleaving: request Y checked for an existing report (none yet), then stalls until request X has
    scored, stored the report and released the lock. Y then acquires a fresh lock and must re-check before scoring."""
    import cache
    sid = await world.new_session(user_a)
    first_done = asyncio.Event()
    seen = {"n": 0}
    real_incr, real_delete = cache.incr, cache.delete

    async def gated_incr(key, ttl):
        if key.startswith("score-lock:"):
            seen["n"] += 1
            if seen["n"] == 2:
                await first_done.wait()
        return await real_incr(key, ttl)

    async def delete(key):
        await real_delete(key)
        if key.startswith("score-lock:"):
            first_done.set()

    monkeypatch.setattr(cache, "incr", gated_incr)
    monkeypatch.setattr(cache, "delete", delete)
    x = asyncio.create_task(user_a.post(f"/api/sessions/{sid}/score"))
    y = asyncio.create_task(user_a.post(f"/api/sessions/{sid}/score"))
    rx, ry = await asyncio.gather(x, y)
    assert rx.status_code == ry.status_code == 200 and rx.json() == ry.json()
    assert fake_llm.count("narrative") == 1
