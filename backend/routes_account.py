"""Account self-service (data export, deletion) and admin-only endpoints."""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

import cache
import db
import repo
import usage
from auth import current_user, require_admin
from middleware import INFLIGHT, METRICS, SESSION_COOKIE
from ratelimit import limit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["account"])


class DeleteAccountIn(BaseModel):
    confirm: str


@router.get("/me/export", dependencies=[Depends(limit("export", 5, 3600))])
async def export_my_data(user: Dict[str, Any] = Depends(current_user)):
    """Everything we hold about the caller (GDPR/KVKK access request)."""
    pool = db.pool()
    sessions = await pool.fetch("SELECT id, case_id, lang, created_at, data FROM case_sessions WHERE user_id = $1 ORDER BY created_at", user["id"])
    reports = await pool.fetch("SELECT session_id, case_id, total, grade, created_at, report FROM case_reports WHERE user_id = $1", user["id"])
    ai_cases = await pool.fetch("SELECT case_id, topic, created_at, data FROM ai_cases WHERE created_by = $1", user["id"])
    job_rows = await pool.fetch("SELECT id, kind, status, created_at, finished_at FROM jobs WHERE user_id = $1 ORDER BY created_at", user["id"])
    usage_rows = await pool.fetch("SELECT kind, provider, model, input_tokens, output_tokens, chars, cost_usd, created_at FROM llm_usage WHERE user_id = $1 ORDER BY created_at", user["id"])
    sub = await pool.fetchrow("SELECT plan, status, current_period_end, cancel_at_period_end, created_at FROM subscriptions WHERE user_id = $1", user["id"])
    return {
        "user": {k: (str(v) if k == "id" else v) for k, v in user.items() if k != "google_sub"},
        "subscription": dict(sub) if sub else None,
        "sessions": [{**dict(r), "id": str(r["id"])} for r in sessions],
        "reports": [{**dict(r), "session_id": str(r["session_id"])} for r in reports],
        "ai_cases": [dict(r) for r in ai_cases],
        "jobs": [{**dict(r), "id": str(r["id"])} for r in job_rows],
        "ai_usage": [{**dict(r), "cost_usd": float(r["cost_usd"])} for r in usage_rows],
    }


@router.delete("/me", dependencies=[Depends(limit("delete-account", 3, 3600))])
async def delete_my_account(body: DeleteAccountIn, response: Response, user: Dict[str, Any] = Depends(current_user)):
    if body.confirm != "DELETE":
        raise HTTPException(status_code=400, detail="Type DELETE to confirm")
    active = await db.pool().fetchval(
        "SELECT 1 FROM subscriptions WHERE user_id = $1 AND status IN ('active', 'past_due', 'pending')", user["id"])
    if active:
        raise HTTPException(status_code=409, detail={"code": "active_subscription",
                                                      "message": "Cancel your subscription before deleting the account"})
    await repo.delete_user(user["id"])
    response.delete_cookie(SESSION_COOKIE, path="/")
    logger.info("account deleted", extra={"extra_fields": {"user_id": str(user["id"])}})
    return {"ok": True}


# ----------------------------- admin -----------------------------
@router.get("/admin/overview")
async def admin_overview(_: Dict[str, Any] = Depends(require_admin)):
    pool = db.pool()
    users = await pool.fetchval("SELECT count(*) FROM users")
    pro = await pool.fetchval("SELECT count(*) FROM subscriptions WHERE status = 'active'")
    sessions_24h = await pool.fetchval("SELECT count(*) FROM case_sessions WHERE created_at > now() - interval '24 hours'")
    job_rows = await pool.fetch("SELECT status, count(*) AS n FROM jobs GROUP BY status")
    spend = await pool.fetch(
        """SELECT kind, count(*) AS calls, round(sum(cost_usd)::numeric, 4) AS usd FROM llm_usage
           WHERE created_at > now() - interval '30 days' GROUP BY kind ORDER BY usd DESC""")
    return {
        "users": users, "pro_subscribers": pro, "sessions_last_24h": sessions_24h,
        "jobs": {r["status"]: r["n"] for r in job_rows},
        "ai_spend_today_usd": round(await usage.global_spend_today(), 4),
        "ai_spend_30d_by_kind": [{**dict(r), "usd": float(r["usd"])} for r in spend],
        "runtime": {"db_pool": db.pool_stats(), "cache_backend": cache.backend(), "inflight_requests": INFLIGHT["n"],
                    "responses": dict(METRICS["status"])},
    }


@router.get("/admin/users")
async def admin_users(limit_: int = Query(50, ge=1, le=200, alias="limit"), offset: int = Query(0, ge=0),
                      _: Dict[str, Any] = Depends(require_admin)):
    rows = await db.pool().fetch(
        """SELECT u.id, u.email, u.role, u.created_at, u.last_login_at,
                  COALESCE(s.status, 'none') AS subscription
           FROM users u LEFT JOIN subscriptions s ON s.user_id = u.id
           ORDER BY u.created_at DESC LIMIT $1 OFFSET $2""", limit_, offset)
    return [{**dict(r), "id": str(r["id"])} for r in rows]
