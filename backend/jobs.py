"""Durable background jobs on PostgreSQL (no extra infrastructure).

States: pending -> processing -> completed | failed. Safe with several instances (FOR UPDATE SKIP LOCKED),
survives restarts (a crashed job's lease expires and it is re-claimed), retries with backoff, enforces a timeout,
and is idempotent per (user, kind, idempotency_key) so a re-clicked request never starts the work twice."""
import asyncio
import logging
import random
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

import alerts
import db
import usage
from config import settings

logger = logging.getLogger(__name__)
ProgressFn = Callable[[int, str], Awaitable[None]]
Handler = Callable[[Dict[str, Any], ProgressFn], Awaitable[Dict[str, Any]]]
HANDLERS: Dict[str, Handler] = {}
POLL_S = 1.0
# Billing drift repair (missed callbacks/webhooks, unmatched charges). The first run waits a little so short-lived
# processes (restarts, free-tier spin-downs) still get one, without hammering iyzico on every boot.
BILLING_RECONCILE_FIRST_S = 600
BILLING_RECONCILE_EVERY_S = 3600
PUBLIC_COLS = "id, kind, status, progress, stage, result, error, attempts, max_attempts, created_at, finished_at"


def handler(kind: str):
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn
    return register


async def enqueue(user_id: uuid.UUID, kind: str, payload: Dict[str, Any], idempotency_key: str,
                  max_attempts: Optional[int] = None) -> Tuple[Dict[str, Any], bool]:
    """Returns (job, created). A repeated key returns the existing job instead of creating another."""
    row = await db.pool().fetchrow(
        f"""INSERT INTO jobs (user_id, kind, idempotency_key, payload, max_attempts)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id, kind, idempotency_key) DO NOTHING RETURNING {PUBLIC_COLS}""",
        user_id, kind, idempotency_key, payload, max_attempts or settings.job_max_attempts)
    if row:
        return dict(row), True
    existing = await db.pool().fetchrow(
        f"SELECT {PUBLIC_COLS} FROM jobs WHERE user_id = $1 AND kind = $2 AND idempotency_key = $3",
        user_id, kind, idempotency_key)
    return dict(existing), False


async def get_by_key(user_id: uuid.UUID, kind: str, idempotency_key: str) -> Optional[Dict[str, Any]]:
    row = await db.pool().fetchrow(
        f"SELECT {PUBLIC_COLS} FROM jobs WHERE user_id = $1 AND kind = $2 AND idempotency_key = $3",
        user_id, kind, idempotency_key)
    return dict(row) if row else None


async def get_job(job_id: str, user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        return None
    row = await db.pool().fetchrow(f"SELECT {PUBLIC_COLS} FROM jobs WHERE id = $1 AND user_id = $2", jid, user_id)
    return dict(row) if row else None


async def _claim() -> Optional[Dict[str, Any]]:
    row = await db.pool().fetchrow(
        """UPDATE jobs SET status = 'processing', started_at = COALESCE(started_at, now()), attempts = attempts + 1,
                  locked_until = now() + ($1 * interval '1 second')
           WHERE id = (SELECT id FROM jobs
                       WHERE run_after <= now()
                         AND (status = 'pending' OR (status = 'processing' AND locked_until < now() AND attempts < max_attempts))
                       ORDER BY run_after LIMIT 1 FOR UPDATE SKIP LOCKED)
           RETURNING *""", settings.job_timeout_s + 30)
    return dict(row) if row else None


async def _finish(job_id: uuid.UUID, result: Dict[str, Any]) -> None:
    await db.pool().execute(
        """UPDATE jobs SET status = 'completed', result = $2, progress = 100, stage = 'done',
                  error = NULL, finished_at = now(), locked_until = NULL WHERE id = $1""", job_id, result)


async def _fail_or_retry(job: Dict[str, Any], error_code: str) -> None:
    if job["attempts"] >= job["max_attempts"]:
        await db.pool().execute(
            "UPDATE jobs SET status = 'failed', error = $2, finished_at = now(), locked_until = NULL WHERE id = $1",
            job["id"], error_code)
        logger.error("job failed permanently", extra={"extra_fields": {"job_id": str(job["id"]), "kind": job["kind"], "error": error_code}})
        return
    backoff = min(60, 5 * 2 ** (job["attempts"] - 1)) + random.uniform(0, 2)
    await db.pool().execute(
        """UPDATE jobs SET status = 'pending', error = $2, locked_until = NULL,
                  run_after = now() + ($3 * interval '1 second') WHERE id = $1""", job["id"], error_code, backoff)
    logger.warning("job will retry", extra={"extra_fields": {"job_id": str(job["id"]), "attempt": job["attempts"], "in_s": round(backoff, 1)}})


async def _run(job: Dict[str, Any]) -> None:
    fn = HANDLERS.get(job["kind"])
    if fn is None:
        await _fail_or_retry({**job, "attempts": job["max_attempts"]}, "unknown_job_kind")
        return

    async def progress(pct: int, stage: str) -> None:
        await db.pool().execute(
            "UPDATE jobs SET progress = $2, stage = $3, locked_until = now() + ($4 * interval '1 second') WHERE id = $1",
            job["id"], max(0, min(99, pct)), stage, settings.job_timeout_s + 30)

    try:
        result = await asyncio.wait_for(fn(job, progress), timeout=settings.job_timeout_s)
        await _finish(job["id"], result)
    except asyncio.TimeoutError:
        await _fail_or_retry(job, "timeout")
    except JobError as e:
        await _fail_or_retry({**job, "attempts": job["max_attempts"]} if e.permanent else job, e.code)
    except asyncio.CancelledError:
        raise  # shutdown: lease expires and another worker resumes the job
    except Exception:  # noqa: BLE001
        logger.exception("job handler crashed", extra={"extra_fields": {"job_id": str(job["id"]), "kind": job["kind"]}})
        await _fail_or_retry(job, "internal_error")


class JobError(Exception):
    def __init__(self, code: str, permanent: bool = False):
        super().__init__(code)
        self.code, self.permanent = code, permanent


async def worker_loop(stop: asyncio.Event, name: str) -> None:
    logger.info("job worker started", extra={"extra_fields": {"worker": name}})
    while not stop.is_set():
        try:
            job = await _claim()
        except Exception as e:  # noqa: BLE001
            logger.error("job claim failed: %s", type(e).__name__)
            job = None
        if job is None:
            try:
                await asyncio.wait_for(stop.wait(), timeout=POLL_S)
            except asyncio.TimeoutError:
                pass
            continue
        await _run(job)
    logger.info("job worker stopped", extra={"extra_fields": {"worker": name}})


async def _reconcile_billing() -> None:
    try:
        import billing   # optional module (see server.py); imported lazily
    except ImportError:
        return
    await billing.reconcile_all()


async def maintenance_loop(stop: asyncio.Event) -> None:
    """Retention + housekeeping + cost alerting (every 5 minutes), billing reconciliation (hourly)."""
    loop = asyncio.get_running_loop()
    next_billing = loop.time() + BILLING_RECONCILE_FIRST_S
    while not stop.is_set():
        try:
            pool = db.pool()
            await pool.execute("DELETE FROM auth_sessions WHERE expires_at < now()")
            await pool.execute("DELETE FROM jobs WHERE finished_at < now() - ($1 * interval '1 day')", settings.retention_jobs_days)
            await pool.execute("DELETE FROM case_sessions WHERE created_at < now() - ($1 * interval '1 day')",
                               settings.retention_sessions_days)
            await pool.execute(
                """UPDATE jobs SET status = 'failed', error = 'abandoned', finished_at = now()
                   WHERE status = 'processing' AND locked_until < now() AND attempts >= max_attempts""")
            spent = await usage.global_spend_today()
            if spent >= settings.global_daily_cost_alert:
                await alerts.send("daily-cost", f"AI spend today is ${spent:.2f} (alert threshold ${settings.global_daily_cost_alert:.2f})")
        except Exception as e:  # noqa: BLE001
            logger.error("maintenance failed: %s", type(e).__name__)
        if loop.time() >= next_billing:
            next_billing = loop.time() + BILLING_RECONCILE_EVERY_S
            try:
                await _reconcile_billing()
            except Exception:  # noqa: BLE001 - never let billing take housekeeping down
                logger.exception("billing reconcile failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=300)
        except asyncio.TimeoutError:
            pass
