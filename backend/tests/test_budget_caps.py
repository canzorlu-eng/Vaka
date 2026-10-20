"""Month-to-date AI spend caps and the per-session message cap (cost abuse controls)."""
import pytest
from fastapi import HTTPException

import llm
import usage
from conftest import CASE_ID


async def test_monthly_cap_blocks_further_ai_calls(world, user_a):
    user = await world.user_row(user_a.id) if hasattr(world, "user_row") else None
    if user is None:
        import repo
        user = await repo.get_user(user_a.id)
    await usage.record(user["id"], "chat", "gemini", "x", cost_usd=1.0)  # far above the free monthly cap (0.15)
    with pytest.raises(HTTPException) as e:
        await llm.enforce_budget(user)
    assert e.value.status_code == 429
    assert e.value.detail in ("daily_ai_budget_reached", "monthly_ai_budget_reached")


async def test_message_cap_per_session(world, user_a, fake_llm):
    r = await user_a.post("/api/sessions", {"case_id": CASE_ID, "lang": "tr"})
    sid = r.json()["id"]
    from config import settings
    cap = settings.max_messages_per_session
    # fill the transcript directly instead of making `cap` HTTP calls
    import repo
    import uuid
    filler = [{"role": "student", "text": "q", "ts": "t"}, {"role": "patient", "text": "a", "ts": "t"}] * cap
    await repo.update_session(sid, uuid.UUID(str(user_a.id)), lambda cur: {**cur, "transcript": filler})
    r = await user_a.post(f"/api/sessions/{sid}/message", {"text": "one more?"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "session_message_limit"
    assert fake_llm.count("chat") == 0
