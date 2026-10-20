"""AI usage ledger: every LLM/TTS call is recorded with tokens/characters and estimated USD cost, so spend can be
capped per user, alerted globally and measured per end-to-end run."""
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

import db
from config import settings

# model -> [(effective_from_utc, input_usd_per_1M, output_usd_per_1M)] (output includes thinking tokens)
# Source: https://ai.google.dev/gemini-api/docs/pricing (read 2026-10-20).
_D = datetime
MODEL_PRICES = {
    "gemini-3.5-flash-lite": [(_D(2000, 1, 1, tzinfo=timezone.utc), 0.30, 2.50)],
    "gemini-2.5-flash": [(_D(2000, 1, 1, tzinfo=timezone.utc), 0.30, 2.50)],
    "gemini-3-flash-preview": [(_D(2000, 1, 1, tzinfo=timezone.utc), 0.50, 3.00)],
    "gemini-3.1-flash-lite": [(_D(2000, 1, 1, tzinfo=timezone.utc), 0.25, 1.50)],
    "gemini-3.6-flash": [(_D(2000, 1, 1, tzinfo=timezone.utc), 0.75, 3.75), (_D(2027, 1, 1, tzinfo=timezone.utc), 1.50, 7.50)],
    "gemini-3.8-flash": [(_D(2000, 1, 1, tzinfo=timezone.utc), 0.75, 3.75), (_D(2027, 1, 1, tzinfo=timezone.utc), 1.50, 7.50)],
}


def gemini_price(model: str, now: Optional[datetime] = None) -> Tuple[float, float]:
    """(input, output) USD per 1M tokens in effect now. Unknown models fall back to the configured prices."""
    now = now or datetime.now(timezone.utc)
    schedule = MODEL_PRICES.get(model)
    if not schedule:
        return settings.price_gemini_in_per_m, settings.price_gemini_out_per_m
    current = [s for s in schedule if s[0] <= now][-1]
    return current[1], current[2]


def gemini_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = gemini_price(model)
    return (input_tokens * pin + output_tokens * pout) / 1_000_000


def tts_cost(chars: int) -> float:
    return chars * settings.price_tts_per_m_chars / 1_000_000


async def record(user_id: Optional[uuid.UUID], kind: str, provider: str, model: str, *, input_tokens: int = 0,
                 output_tokens: int = 0, chars: int = 0, cost_usd: float = 0.0, latency_ms: int = 0,
                 ref: Optional[str] = None) -> None:
    await db.pool().execute(
        """INSERT INTO llm_usage (user_id, kind, provider, model, input_tokens, output_tokens, chars, cost_usd, latency_ms, ref)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
        user_id, kind, provider, model, input_tokens, output_tokens, chars, round(cost_usd, 6), latency_ms, ref)


async def user_spend_24h(user_id: uuid.UUID) -> float:
    v = await db.pool().fetchval(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_usage WHERE user_id = $1 AND created_at > now() - interval '24 hours'",
        user_id)
    return float(v)


async def user_spend_month(user_id: uuid.UUID) -> float:
    v = await db.pool().fetchval(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_usage WHERE user_id = $1 AND created_at >= date_trunc('month', now())",
        user_id)
    return float(v)


async def global_spend_today() -> float:
    v = await db.pool().fetchval(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_usage WHERE created_at >= date_trunc('day', now())")
    return float(v)
