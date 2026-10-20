"""Operational alerts to a Slack/Discord-compatible webhook (ALERT_WEBHOOK_URL). De-duplicated via the shared cache
so an incident produces one message per cooldown window, not one per request."""
import logging

import httpx

import cache
from config import settings
from logging_setup import redact

logger = logging.getLogger(__name__)


async def send(key: str, message: str, cooldown_s: int = 3600) -> None:
    logger.error("ALERT %s: %s", key, message)
    if not settings.alert_webhook_url:
        return
    if await cache.get(f"alert:{key}"):
        return
    await cache.set(f"alert:{key}", "1", cooldown_s)
    text = redact(f"[Vaka/{settings.env}] {message}")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(settings.alert_webhook_url, json={"text": text, "content": text})
    except httpx.HTTPError as e:
        logger.error("alert webhook failed: %s", type(e).__name__)
