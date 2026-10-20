"""Shared ephemeral state: Redis when REDIS_URL is set, otherwise a process-local fallback (dev/tests).
Used for rate-limit counters, response caches and in-flight counters. Redis failures degrade to
fail-open behaviour and are logged - they never take the API down."""
import logging
import time
from typing import Dict, Optional, Tuple

from config import settings

logger = logging.getLogger(__name__)
_redis = None
_mem: Dict[str, Tuple[float, str]] = {}  # key -> (expires_at, value)
_MEM_MAX = 20_000


async def init() -> None:
    global _redis
    if not settings.redis_url:
        logger.warning("REDIS_URL not set: using in-process cache/rate limits (single instance only)")
        return
    import redis.asyncio as aioredis
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2,
                               health_check_interval=30)
    await _redis.ping()
    logger.info("redis connected")


async def close() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
    _mem.clear()


def backend() -> str:
    return "redis" if _redis is not None else "memory"


async def ping() -> bool:
    if _redis is None:
        return True
    try:
        return bool(await _redis.ping())
    except Exception:  # noqa: BLE001
        return False


def _mem_gc(now: float) -> None:
    if len(_mem) < _MEM_MAX:
        return
    for k in [k for k, (exp, _) in _mem.items() if exp <= now][: _MEM_MAX // 2]:
        _mem.pop(k, None)
    if len(_mem) >= _MEM_MAX:
        _mem.clear()


async def get(key: str) -> Optional[str]:
    if _redis is not None:
        try:
            return await _redis.get(key)
        except Exception as e:  # noqa: BLE001
            logger.error("redis get failed: %s", e)
            return None
    item = _mem.get(key)
    if item and item[0] > time.monotonic():
        return item[1]
    _mem.pop(key, None)
    return None


async def set(key: str, value: str, ttl: int) -> None:
    if _redis is not None:
        try:
            await _redis.set(key, value, ex=ttl)
        except Exception as e:  # noqa: BLE001
            logger.error("redis set failed: %s", e)
        return
    now = time.monotonic()
    _mem_gc(now)
    _mem[key] = (now + ttl, value)


async def delete(key: str) -> None:
    if _redis is not None:
        try:
            await _redis.delete(key)
        except Exception as e:  # noqa: BLE001
            logger.error("redis delete failed: %s", e)
        return
    _mem.pop(key, None)


async def incr(key: str, ttl: int) -> Tuple[int, int]:
    """Atomic fixed-window counter. Returns (count, seconds_until_reset). Fails open (count 0) if Redis is down."""
    if _redis is not None:
        try:
            pipe = _redis.pipeline()
            pipe.incr(key)
            pipe.ttl(key)
            count, remaining = await pipe.execute()
            if remaining < 0:  # first hit (or missing expiry): set the window
                await _redis.expire(key, ttl)
                remaining = ttl
            return int(count), int(remaining)
        except Exception as e:  # noqa: BLE001
            logger.error("redis incr failed (failing open): %s", e)
            return 0, ttl
    now = time.monotonic()
    _mem_gc(now)
    exp, val = _mem.get(key, (0.0, "0"))
    if exp <= now:
        exp, val = now + ttl, "0"
    count = int(val) + 1
    _mem[key] = (exp, str(count))
    return count, max(1, int(exp - now))


async def decr(key: str) -> None:
    if _redis is not None:
        try:
            await _redis.decr(key)
        except Exception as e:  # noqa: BLE001
            logger.error("redis decr failed: %s", e)
        return
    if key in _mem:
        exp, val = _mem[key]
        _mem[key] = (exp, str(max(0, int(val) - 1)))


async def get_int(key: str) -> int:
    v = await get(key)
    return int(v) if v and v.lstrip("-").isdigit() else 0
