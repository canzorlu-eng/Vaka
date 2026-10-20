"""Data access for users, auth sessions, case sessions, reports and AI-generated cases.
Every case-session query is scoped by user_id: authorization is enforced in SQL, not only in routes."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

import db


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------- users & auth sessions -----------------------------
USER_COLS = "id, google_sub, email, email_verified, name, picture, role, created_at, last_login_at"


async def upsert_google_user(sub: str, email: str, email_verified: bool, name: Optional[str],
                             picture: Optional[str], admin_emails: List[str]) -> Dict[str, Any]:
    role = "admin" if email.lower() in admin_emails else "user"
    row = await db.pool().fetchrow(
        f"""INSERT INTO users (google_sub, email, email_verified, name, picture, role, last_login_at)
            VALUES ($1, $2, $3, $4, $5, $6, now())
            ON CONFLICT (google_sub) DO UPDATE SET
                email = EXCLUDED.email, email_verified = EXCLUDED.email_verified,
                name = EXCLUDED.name, picture = EXCLUDED.picture, last_login_at = now(),
                role = CASE WHEN EXCLUDED.role = 'admin' THEN 'admin' ELSE users.role END
            RETURNING {USER_COLS}""",
        sub, email, email_verified, name, picture, role)
    return dict(row)


async def get_user(user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    row = await db.pool().fetchrow(f"SELECT {USER_COLS} FROM users WHERE id = $1", user_id)
    return dict(row) if row else None


async def create_auth_session(token_hash: str, user_id: uuid.UUID, ttl_days: int, user_agent: str) -> None:
    await db.pool().execute(
        "INSERT INTO auth_sessions (token_hash, user_id, expires_at, user_agent) VALUES ($1, $2, $3, $4)",
        token_hash, user_id, _now() + timedelta(days=ttl_days), (user_agent or "")[:200])


async def user_for_token(token_hash: str) -> Optional[Dict[str, Any]]:
    row = await db.pool().fetchrow(
        f"""SELECT {', '.join('u.' + c.strip() for c in USER_COLS.split(','))}
            FROM auth_sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = $1 AND s.expires_at > now()""", token_hash)
    return dict(row) if row else None


async def delete_auth_session(token_hash: str) -> None:
    await db.pool().execute("DELETE FROM auth_sessions WHERE token_hash = $1", token_hash)


async def delete_user(user_id: uuid.UUID) -> None:
    """Hard-delete a user; FKs cascade sessions, reports, jobs, AI cases. llm_usage keeps anonymous cost rows."""
    await db.pool().execute("DELETE FROM users WHERE id = $1", user_id)


# ----------------------------- case sessions -----------------------------
async def insert_session(user_id: uuid.UUID, doc: Dict[str, Any]) -> None:
    await db.pool().execute(
        "INSERT INTO case_sessions (id, user_id, case_id, lang, data) VALUES ($1, $2, $3, $4, $5)",
        uuid.UUID(doc["id"]), user_id, doc["case_id"], doc["lang"], doc)


async def get_session(sid: str, user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    try:
        sid_u = uuid.UUID(sid)
    except ValueError:
        return None
    return await db.pool().fetchval("SELECT data FROM case_sessions WHERE id = $1 AND user_id = $2", sid_u, user_id)


async def update_session(sid: str, user_id: uuid.UUID,
                         fn: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Atomic read-modify-write under a row lock (prevents lost updates from concurrent requests)."""
    try:
        sid_u = uuid.UUID(sid)
    except ValueError:
        return None
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            cur = await conn.fetchval(
                "SELECT data FROM case_sessions WHERE id = $1 AND user_id = $2 FOR UPDATE", sid_u, user_id)
            if cur is None:
                return None
            new = fn(cur)
            await conn.execute(
                "UPDATE case_sessions SET data = $3, ended = $4, updated_at = now() WHERE id = $1 AND user_id = $2",
                sid_u, user_id, new, bool(new.get("ended")))
            return new


async def count_sessions_this_month(user_id: uuid.UUID) -> int:
    return await db.pool().fetchval(
        "SELECT count(*) FROM case_sessions WHERE user_id = $1 AND created_at >= date_trunc('month', now())", user_id)


async def list_sessions(user_id: uuid.UUID, limit: int, before: Optional[datetime]) -> List[Dict[str, Any]]:
    """Keyset pagination on created_at (newest first)."""
    rows = await db.pool().fetch(
        """SELECT s.id, s.case_id, s.lang, s.ended, s.created_at, r.total, r.grade
           FROM case_sessions s LEFT JOIN case_reports r ON r.session_id = s.id
           WHERE s.user_id = $1 AND ($3::timestamptz IS NULL OR s.created_at < $3)
           ORDER BY s.created_at DESC LIMIT $2""", user_id, limit, before)
    return [dict(r) for r in rows]


# ----------------------------- reports (idempotent) -----------------------------
async def get_report(sid: str, user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    try:
        sid_u = uuid.UUID(sid)
    except ValueError:
        return None
    return await db.pool().fetchval(
        "SELECT report FROM case_reports WHERE session_id = $1 AND user_id = $2", sid_u, user_id)


async def save_report(sid: str, user_id: uuid.UUID, case_id: str, report: Dict[str, Any]) -> Dict[str, Any]:
    """First writer wins; a concurrent duplicate scoring request gets the stored report back."""
    sid_u = uuid.UUID(sid)
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            inserted = await conn.fetchval(
                """INSERT INTO case_reports (session_id, user_id, case_id, total, grade, report)
                   VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (session_id) DO NOTHING RETURNING report""",
                sid_u, user_id, case_id, int(report["total"]), str(report["grade"]), report)
            if inserted is not None:
                await conn.execute(
                    "UPDATE case_sessions SET ended = true, data = jsonb_set(data, '{ended}', 'true'), updated_at = now() WHERE id = $1",
                    sid_u)
                return inserted
            return await conn.fetchval("SELECT report FROM case_reports WHERE session_id = $1", sid_u)


# ----------------------------- AI-generated cases -----------------------------
async def insert_ai_case(case: Dict[str, Any], user_id: Optional[uuid.UUID]) -> None:
    await db.pool().execute(
        "INSERT INTO ai_cases (case_id, topic, created_by, data) VALUES ($1, $2, $3, $4)",
        case["case_id"], case.get("topic") or "endodontics", user_id, case)


async def get_ai_case(case_id: str, user_id: Optional[uuid.UUID], is_admin: bool = False) -> Optional[Dict[str, Any]]:
    """Owner-only (or legacy ownerless) visibility."""
    return await db.pool().fetchval(
        """SELECT data FROM ai_cases WHERE case_id = $1
           AND ($3 OR created_by IS NULL OR created_by = $2)""", case_id, user_id, is_admin)


async def list_ai_cases(user_id: Optional[uuid.UUID], topic: Optional[str]) -> List[Dict[str, Any]]:
    rows = await db.pool().fetch(
        """SELECT data FROM ai_cases
           WHERE ($2::text IS NULL OR topic = $2) AND (created_by IS NULL OR created_by = $1)
           ORDER BY created_at DESC LIMIT 100""", user_id, topic)
    return [r["data"] for r in rows]
