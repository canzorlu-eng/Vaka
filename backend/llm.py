"""LLM (Gemini) and TTS (OpenAI) gateway: concurrency limits, per-user daily spend caps, timeouts, retries,
cost accounting and an audio cache. Route code never talks to providers directly."""
import asyncio
import base64
import hashlib
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import HTTPException

import cache
import usage
from config import settings
from plans import plan_for

logger = logging.getLogger(__name__)
_semaphore = asyncio.Semaphore(settings.llm_max_concurrency)
MAX_INFLIGHT_PER_USER = 2
TTS_CACHE_TTL = 7 * 86400
TTS_MAX_CHARS = 600


def llm_available() -> bool:
    return bool(settings.gemini_api_key)


def tts_available() -> bool:
    return bool(settings.openai_api_key)


async def enforce_budget(user: Dict[str, Any]) -> None:
    """Hard stop when the user's AI spend over the last 24h / this month reaches their plan's caps."""
    plan = await plan_for(user)
    spent = await usage.user_spend_24h(user["id"])
    if spent >= plan.daily_cost_cap_usd:
        logger.warning("daily AI budget reached", extra={"extra_fields": {"user_id": str(user["id"]), "spent": round(spent, 4)}})
        raise HTTPException(status_code=429, detail="daily_ai_budget_reached", headers={"Retry-After": "3600"})
    month = await usage.user_spend_month(user["id"])
    if month >= plan.monthly_cost_cap_usd:
        logger.warning("monthly AI budget reached", extra={"extra_fields": {"user_id": str(user["id"]), "spent": round(month, 4)}})
        raise HTTPException(status_code=429, detail="monthly_ai_budget_reached", headers={"Retry-After": "86400"})


@asynccontextmanager
async def slot(user_id: Optional[uuid.UUID]):
    """Bound concurrent provider calls globally (semaphore) and per user (shared counter)."""
    key = f"inflight:{user_id}" if user_id else None
    if key:
        n, _ = await cache.incr(key, 120)
        if n > MAX_INFLIGHT_PER_USER:
            await cache.decr(key)
            raise HTTPException(status_code=429, detail="too_many_concurrent_ai_requests", headers={"Retry-After": "5"})
    try:
        async with _semaphore:
            yield
    finally:
        if key:
            await cache.decr(key)


async def llm_call(system: str, prompt: str, temperature: float = 0.7, *, user: Optional[Dict[str, Any]] = None,
                   kind: str = "chat", ref: Optional[str] = None, json_mode: bool = False,
                   model: Optional[str] = None) -> Optional[str]:
    if not llm_available():
        return None
    if user:
        await enforce_budget(user)
    uid = user["id"] if user else None
    model = model or settings.gemini_model
    try:
        from google import genai
        from google.genai import types
        cfg: Dict[str, Any] = {"system_instruction": system, "temperature": temperature}
        if json_mode:
            cfg["response_mime_type"] = "application/json"
        if settings.gemini_thinking_budget >= 0:
            cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=settings.gemini_thinking_budget)
        client = genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(
            timeout=settings.llm_timeout_ms,
            retry_options=types.HttpRetryOptions(attempts=4, http_status_codes=[429, 500, 503])))
        started = time.perf_counter()
        async with slot(uid):
            resp = await client.aio.models.generate_content(
                model=model, contents=prompt, config=types.GenerateContentConfig(**cfg))
        latency = int((time.perf_counter() - started) * 1000)
        meta = resp.usage_metadata
        in_tok = int(getattr(meta, "prompt_token_count", 0) or 0)
        out_tok = int((getattr(meta, "candidates_token_count", 0) or 0) + (getattr(meta, "thoughts_token_count", 0) or 0))
        await usage.record(uid, kind, "gemini", model, input_tokens=in_tok, output_tokens=out_tok,
                           cost_usd=usage.gemini_cost(model, in_tok, out_tok), latency_ms=latency, ref=ref)
        return resp.text
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error("LLM call failed: %s", type(e).__name__)
        return None


async def synthesize(text: str, user: Dict[str, Any], ref: Optional[str] = None) -> Optional[str]:
    """Returns base64 MP3 or None (client then falls back to the browser voice). Cached by content."""
    text = text.strip()[:TTS_MAX_CHARS]
    if not text or not tts_available():
        return None
    key = "tts:" + hashlib.sha256(f"{settings.tts_model}|{settings.tts_voice}|{text}".encode()).hexdigest()
    cached = await cache.get(key) if cache.backend() == "redis" else None
    if cached:
        return cached
    await enforce_budget(user)
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=30)
        started = time.perf_counter()
        async with slot(user["id"]):
            resp = await client.audio.speech.create(model=settings.tts_model, voice=settings.tts_voice,
                                                    input=text, response_format="mp3")
        latency = int((time.perf_counter() - started) * 1000)
        audio = base64.b64encode(resp.content).decode("ascii")
        await usage.record(user["id"], "tts", "openai", settings.tts_model, chars=len(text),
                           cost_usd=usage.tts_cost(len(text)), latency_ms=latency, ref=ref)
        if cache.backend() == "redis":
            await cache.set(key, audio, TTS_CACHE_TTL)
        return audio
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error("TTS failed: %s", type(e).__name__)
        return None
