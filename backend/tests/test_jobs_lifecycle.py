"""Background jobs: idempotency, lifecycle, retry/backoff, timeouts, lease reclaim, case generation handler."""
import asyncio
import dataclasses
import uuid

import pytest

import db
import jobs
import repo
from jobs import JobError

KIND = "test_kind"


@pytest.fixture
def handler(monkeypatch):
    """Register a controllable handler under KIND."""
    state = {"calls": 0, "behaviour": None, "stages": []}

    async def fn(job, progress):
        state["calls"] += 1
        state["stages"].append(job["attempts"])
        await progress(30, "working")
        b = state["behaviour"]
        if isinstance(b, BaseException):
            raise b
        if callable(b):
            return await b(job, progress)
        return b if b is not None else {"ok": True}

    monkeypatch.setitem(jobs.HANDLERS, KIND, fn)
    return state


async def _job(job_id):
    return dict(await db.pool().fetchrow("SELECT * FROM jobs WHERE id = $1", job_id))


async def _make_due(job_id):
    await db.pool().execute("UPDATE jobs SET run_after = now() WHERE id = $1", job_id)


async def test_lifecycle_pending_processing_completed_with_progress(world, user_a, handler):
    job, created = await jobs.enqueue(user_a.id, KIND, {"x": 1}, "life-key-0001")
    assert created and job["status"] == "pending" and job["progress"] == 0 and job["attempts"] == 0
    observed = {}

    async def behaviour(j, progress):
        row = await _job(j["id"])
        observed["status_during"], observed["progress_during"] = row["status"], row["progress"]
        observed["via_api"] = (await user_a.get(f"/api/jobs/{j['id']}")).json()
        await progress(70, "almost")
        return {"answer": 42}

    handler["behaviour"] = behaviour
    claimed = await jobs._claim()
    assert claimed["id"] == job["id"] and claimed["status"] == "processing" and claimed["attempts"] == 1
    await jobs._run(claimed)
    assert observed["status_during"] == "processing" and observed["progress_during"] == 30
    assert observed["via_api"]["status"] == "processing" and observed["via_api"]["stage"] == "working"
    final = (await user_a.get(f"/api/jobs/{job['id']}")).json()
    assert final["status"] == "completed" and final["progress"] == 100 and final["stage"] == "done"
    assert final["result"] == {"answer": 42} and final["error"] is None
    assert await jobs._claim() is None, "a completed job is never claimed again"


async def test_progress_is_clamped_below_100_until_finished(world, user_a, handler):
    await jobs.enqueue(user_a.id, KIND, {}, "clamp-key-001")
    seen = []

    async def behaviour(j, progress):
        await progress(500, "x")
        seen.append((await _job(j["id"]))["progress"])
        await progress(-5, "y")
        seen.append((await _job(j["id"]))["progress"])
        return {}

    handler["behaviour"] = behaviour
    await jobs._run(await jobs._claim())
    assert seen == [99, 0]


async def test_claim_respects_run_after_and_order(world, user_a, handler):
    later, _ = await jobs.enqueue(user_a.id, KIND, {}, "later-key-001")
    await db.pool().execute("UPDATE jobs SET run_after = now() + interval '1 hour' WHERE id = $1", later["id"])
    assert await jobs._claim() is None
    first, _ = await jobs.enqueue(user_a.id, KIND, {}, "first-key-001")
    assert (await jobs._claim())["id"] == first["id"]


async def test_parallel_claims_never_hand_out_the_same_job(world, user_a, handler):
    for i in range(5):
        await jobs.enqueue(user_a.id, KIND, {}, f"claim-key-{i:03d}")
    claimed = await asyncio.gather(*[jobs._claim() for _ in range(8)])
    ids = [c["id"] for c in claimed if c]
    assert len(ids) == 5 and len(set(ids)) == 5


async def test_handler_failure_retries_with_backoff_then_fails_permanently(world, user_a, handler):
    job, _ = await jobs.enqueue(user_a.id, KIND, {}, "retry-key-001", max_attempts=3)
    handler["behaviour"] = RuntimeError("provider exploded: key=AIzaSyFAKEFAKEFAKEFAKEFAKEFAKE0123456 host=10.0.0.5")
    for attempt in (1, 2):
        claimed = await jobs._claim()
        assert claimed["attempts"] == attempt
        await jobs._run(claimed)
        row = await _job(job["id"])
        assert row["status"] == "pending" and row["error"] == "internal_error" and row["locked_until"] is None
        delay = await db.pool().fetchval("SELECT extract(epoch FROM run_after - now()) FROM jobs WHERE id = $1", job["id"])
        assert delay > (3 if attempt == 1 else 8), "backoff grows between attempts"
        assert await jobs._claim() is None, "not claimable before backoff elapses"
        await _make_due(job["id"])
    await jobs._run(await jobs._claim())
    row = await _job(job["id"])
    assert row["status"] == "failed" and row["error"] == "internal_error" and row["finished_at"] is not None
    assert handler["calls"] == 3
    await _make_due(job["id"])
    assert await jobs._claim() is None
    public = (await user_a.get(f"/api/jobs/{job['id']}")).json()
    assert public["status"] == "failed" and public["error"] == "internal_error"
    assert "AIza" not in str(public) and "provider" not in str(public) and "10.0.0.5" not in str(public)


async def test_permanent_job_error_fails_immediately_with_code(world, user_a, handler):
    job, _ = await jobs.enqueue(user_a.id, KIND, {}, "perm-key-0001", max_attempts=5)
    handler["behaviour"] = JobError("user_gone", permanent=True)
    await jobs._run(await jobs._claim())
    row = await _job(job["id"])
    assert row["status"] == "failed" and row["error"] == "user_gone" and row["attempts"] == 1


async def test_transient_job_error_retries_with_its_code(world, user_a, handler):
    job, _ = await jobs.enqueue(user_a.id, KIND, {}, "trans-key-001", max_attempts=2)
    handler["behaviour"] = JobError("invalid_model_output")
    await jobs._run(await jobs._claim())
    row = await _job(job["id"])
    assert row["status"] == "pending" and row["error"] == "invalid_model_output"


async def test_unknown_job_kind_fails_permanently(world, user_a):
    job, _ = await jobs.enqueue(user_a.id, "no_such_kind", {}, "unk-key-00001")
    await jobs._run(await jobs._claim())
    row = await _job(job["id"])
    assert row["status"] == "failed" and row["error"] == "unknown_job_kind"


async def test_timeout_path_retries_then_fails_with_timeout_code(world, user_a, handler, monkeypatch):
    monkeypatch.setattr(jobs, "settings", dataclasses.replace(jobs.settings, job_timeout_s=0.2))
    job, _ = await jobs.enqueue(user_a.id, KIND, {}, "tmo-key-00001", max_attempts=2)

    async def slow(j, progress):
        await asyncio.sleep(5)

    handler["behaviour"] = slow
    await jobs._run(await jobs._claim())
    row = await _job(job["id"])
    assert row["status"] == "pending" and row["error"] == "timeout"
    # the client retries with the same key while the job is retrying: same job, no duplicate
    again, created = await jobs.enqueue(user_a.id, KIND, {}, "tmo-key-00001")
    assert not created and again["id"] == job["id"]
    await _make_due(job["id"])
    await jobs._run(await jobs._claim())
    row = await _job(job["id"])
    assert row["status"] == "failed" and row["error"] == "timeout" and row["attempts"] == 2


async def test_job_succeeds_on_retry_after_transient_failure(world, user_a, handler):
    job, _ = await jobs.enqueue(user_a.id, KIND, {}, "flaky-key-001")

    async def flaky(j, progress):
        if j["attempts"] == 1:
            raise RuntimeError("transient")
        return {"attempt": j["attempts"]}

    handler["behaviour"] = flaky
    await jobs._run(await jobs._claim())
    await _make_due(job["id"])
    await jobs._run(await jobs._claim())
    row = await _job(job["id"])
    assert row["status"] == "completed" and row["result"] == {"attempt": 2} and row["error"] is None


async def test_crashed_worker_lease_is_reclaimed(world, user_a, handler):
    job, _ = await jobs.enqueue(user_a.id, KIND, {}, "lease-key-001")
    claimed = await jobs._claim()  # worker 1 claims and "dies" without finishing
    assert claimed["attempts"] == 1
    assert await jobs._claim() is None, "a live lease must not be stolen"
    await db.pool().execute("UPDATE jobs SET locked_until = now() - interval '1 minute' WHERE id = $1", job["id"])
    reclaimed = await jobs._claim()
    assert reclaimed["id"] == job["id"] and reclaimed["attempts"] == 2 and reclaimed["status"] == "processing"
    await jobs._run(reclaimed)
    assert (await _job(job["id"]))["status"] == "completed"


async def test_claim_does_not_reclaim_a_job_that_exhausted_its_attempts(world, user_a, handler):
    """A poison job that keeps killing workers must stop after max_attempts instead of being claimed forever."""
    job, _ = await jobs.enqueue(user_a.id, KIND, {}, "poison-key-01", max_attempts=2)
    await db.pool().execute(
        "UPDATE jobs SET status='processing', attempts=2, locked_until = now() - interval '1 minute' WHERE id = $1", job["id"])
    claimed = await jobs._claim()
    assert claimed is None, f"exhausted job was handed out again (attempts now {claimed and claimed['attempts']})"
    assert handler["calls"] == 0


async def test_maintenance_marks_abandoned_jobs(world, user_a, handler):
    job, _ = await jobs.enqueue(user_a.id, KIND, {}, "aband-key-001", max_attempts=1)
    await db.pool().execute(
        "UPDATE jobs SET status='processing', attempts=1, locked_until = now() - interval '1 minute' WHERE id = $1", job["id"])
    stop = asyncio.Event()
    task = asyncio.create_task(jobs.maintenance_loop(stop))
    for _ in range(50):
        await asyncio.sleep(0.05)
        if (await _job(job["id"]))["status"] == "failed":
            break
    stop.set()
    await asyncio.wait_for(task, 5)
    row = await _job(job["id"])
    assert row["status"] == "failed" and row["error"] == "abandoned"


async def test_worker_loop_processes_jobs_and_stops_gracefully(world, user_a, handler):
    job, _ = await jobs.enqueue(user_a.id, KIND, {}, "loop-key-0001")
    stop = asyncio.Event()
    task = asyncio.create_task(jobs.worker_loop(stop, "t"))
    for _ in range(100):
        await asyncio.sleep(0.05)
        if (await _job(job["id"]))["status"] == "completed":
            break
    stop.set()
    await asyncio.wait_for(task, 5)
    assert (await _job(job["id"]))["status"] == "completed"


async def test_cancelled_handler_leaves_lease_for_another_worker(world, user_a, handler):
    job, _ = await jobs.enqueue(user_a.id, KIND, {}, "cancel-key-01")

    async def hang(j, progress):
        await asyncio.sleep(30)

    handler["behaviour"] = hang
    task = asyncio.create_task(jobs._run(await jobs._claim()))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    row = await _job(job["id"])
    assert row["status"] == "processing" and row["locked_until"] is not None


# ----------------------------- HTTP surface -----------------------------
async def test_generate_endpoint_is_idempotent_and_runs_llm_once(world, fake_llm, run_jobs):
    pro = await world.make_user(plan="pro")
    h = {"Idempotency-Key": "http-key-0001"}
    r1 = await pro.post("/api/cases/generate", {"topic": "endodontics", "lang": "en"}, headers=h)
    r2 = await pro.post("/api/cases/generate", {"topic": "endodontics", "lang": "en"}, headers=h)
    assert r1.status_code == r2.status_code == 202 and r1.json()["job_id"] == r2.json()["job_id"]
    assert await world.count("jobs") == 1
    await run_jobs()
    assert await run_jobs() is None
    assert fake_llm.count("generate") == 1
    r3 = await pro.post("/api/cases/generate", {"topic": "endodontics", "lang": "en"}, headers=h)
    done = (await pro.get(f"/api/jobs/{r1.json()['job_id']}")).json()
    assert r3.json()["job_id"] == done["job_id"] and done["status"] == "completed"
    assert done["result"]["case_id"].startswith("gen-") and done["result"]["title"] == "Test case"
    assert fake_llm.count("generate") == 1 and await world.count("jobs") == 1


async def test_same_key_for_two_users_yields_two_jobs(world, fake_llm):
    a, b = await world.make_user(plan="pro"), await world.make_user(plan="pro")
    h = {"Idempotency-Key": "shared-key-001"}
    ja = (await a.post("/api/cases/generate", {"topic": "endodontics"}, headers=h)).json()["job_id"]
    jb = (await b.post("/api/cases/generate", {"topic": "endodontics"}, headers=h)).json()["job_id"]
    assert ja != jb and await world.count("jobs") == 2


async def test_generated_case_is_deterministic_private_and_not_duplicated_on_retry(world, fake_llm, run_jobs):
    owner = await world.make_user(plan="pro")
    other = await world.make_user()
    jid = (await owner.post("/api/cases/generate", {"topic": "endodontics", "lang": "en"},
                            headers={"Idempotency-Key": "gen-key-00001"})).json()["job_id"]
    job = await run_jobs()
    expected_case_id = f"gen-{uuid.UUID(jid).hex[:12]}"
    assert await world.count("ai_cases") == 1
    assert (await db.pool().fetchval("SELECT case_id FROM ai_cases")) == expected_case_id
    # simulate a crash after the insert: the same job runs again (lease reclaim / retry)
    await db.pool().execute("UPDATE jobs SET status='processing', locked_until=now() - interval '1 minute' WHERE id=$1",
                            uuid.UUID(jid))
    await jobs._run(await jobs._claim())
    assert await world.count("ai_cases") == 1
    assert (await _job(uuid.UUID(jid)))["status"] == "completed"
    # visibility
    assert (await owner.get(f"/api/cases/{expected_case_id}")).status_code == 200
    assert expected_case_id in [c["case_id"] for c in (await owner.get("/api/cases?topic=endodontics&limit=100")).json()]
    assert (await other.get(f"/api/cases/{expected_case_id}")).status_code == 404
    assert expected_case_id not in [c["case_id"] for c in (await other.get("/api/cases?topic=endodontics&limit=100")).json()]
    assert job["id"] == uuid.UUID(jid)


async def test_generation_invalid_model_output_retries_then_fails_cleanly(world, fake_llm, run_jobs):
    pro = await world.make_user(plan="pro")
    fake_llm.replies["generate"] = "I cannot comply { not json"
    jid = (await pro.post("/api/cases/generate", {"topic": "endodontics"}, headers={"Idempotency-Key": "bad-out-0001"})).json()["job_id"]
    await run_jobs()
    assert fake_llm.count("generate") == 2, "one repair attempt per run"
    await _make_due(uuid.UUID(jid))
    await run_jobs()
    final = (await pro.get(f"/api/jobs/{jid}")).json()
    assert final["status"] == "failed" and final["error"] == "invalid_model_output" and final["attempts"] == 2
    assert "cannot comply" not in str(final) and await world.count("ai_cases") == 0


async def test_generation_handler_errors_never_leak_provider_details(world, fake_llm, run_jobs):
    pro = await world.make_user(plan="pro")
    fake_llm.replies["generate"] = RuntimeError("403 from generativelanguage.googleapis.com key=AIzaSyFAKEFAKEFAKEFAKEFAKEFAKE0123456")
    jid = (await pro.post("/api/cases/generate", {"topic": "endodontics"}, headers={"Idempotency-Key": "leak-key-0001"})).json()["job_id"]
    await run_jobs()
    body = (await pro.get(f"/api/jobs/{jid}")).text
    assert "googleapis" not in body and "AIza" not in body and "403" not in body


async def test_generation_for_deleted_user_fails_permanently(world, fake_llm, run_jobs):
    # no FK-less jobs exist (cascade), so simulate the handler's guard directly
    import job_handlers
    pro = await world.make_user(plan="pro")
    with pytest.raises(JobError) as exc:
        await job_handlers.generate_case({"payload": {"topic": "endodontics"}, "user_id": uuid.uuid4(), "id": uuid.uuid4()},
                                         lambda *a: asyncio.sleep(0))
    assert exc.value.code == "user_gone" and exc.value.permanent
    with pytest.raises(JobError) as exc2:
        await job_handlers.generate_case({"payload": {"topic": "zzz"}, "user_id": pro.id, "id": uuid.uuid4()},
                                         lambda *a: asyncio.sleep(0))
    assert exc2.value.code == "unknown_topic" and exc2.value.permanent


async def test_get_job_unknown_and_malformed_ids(world, user_a):
    assert await jobs.get_job("zzz", user_a.id) is None
    assert await jobs.get_job(str(uuid.uuid4()), user_a.id) is None
    assert await repo.get_user(user_a.id) is not None
