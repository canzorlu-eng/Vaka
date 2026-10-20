"""Plans and entitlements. Enforced on the backend only - the UI merely reflects them.
Numbers are deliberately conservative defaults; tune them with the measured per-run cost
(scripts/cost_probe.py)."""
import uuid
from dataclasses import dataclass
from typing import Any, Dict

import db
import repo
from config import settings


@dataclass(frozen=True)
class Plan:
    name: str
    sessions_per_month: int
    generations_per_month: int
    voice: bool                 # server-side natural TTS
    daily_cost_cap_usd: float   # hard stop on AI spend per user per day
    monthly_cost_cap_usd: float  # hard stop on AI spend per user per calendar month


FREE = Plan("free", sessions_per_month=3, generations_per_month=0, voice=False,
            daily_cost_cap_usd=settings.user_daily_cost_cap_free,
            monthly_cost_cap_usd=settings.user_monthly_cost_cap_free)
PRO = Plan("pro", sessions_per_month=60, generations_per_month=10, voice=True,
           daily_cost_cap_usd=settings.user_daily_cost_cap_pro,
           monthly_cost_cap_usd=settings.user_monthly_cost_cap_pro)
PLANS = {"free": FREE, "pro": PRO}


async def plan_name_for(user: Dict[str, Any]) -> str:
    if user["role"] == "admin":
        return "pro"
    row = await db.pool().fetchrow(
        """SELECT 1 FROM subscriptions WHERE user_id = $1
           AND (status = 'active' OR (status IN ('canceled', 'past_due') AND current_period_end > now()))""", user["id"])
    return "pro" if row else "free"


async def plan_for(user: Dict[str, Any]) -> Plan:
    return PLANS[await plan_name_for(user)]


async def generations_this_month(user_id: uuid.UUID) -> int:
    return await db.pool().fetchval(
        """SELECT count(*) FROM jobs WHERE user_id = $1 AND kind = 'case_generation'
           AND status <> 'failed' AND created_at >= date_trunc('month', now())""", user_id)


async def usage_snapshot(user: Dict[str, Any]) -> Dict[str, Any]:
    plan = await plan_for(user)
    used = await repo.count_sessions_this_month(user["id"])
    gens = await generations_this_month(user["id"])
    return {
        "plan": plan.name,
        "limits": {"sessions_per_month": plan.sessions_per_month,
                   "generations_per_month": plan.generations_per_month, "voice": plan.voice},
        "used": {"sessions_this_month": used, "generations_this_month": gens},
    }
