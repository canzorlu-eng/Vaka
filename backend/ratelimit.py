"""Rate limiting (per user when authenticated, otherwise per client IP) on top of cache.incr.
Redis-backed in production so every instance shares the same counters."""
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Request

import cache
from identity import optional_user


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def limit(name: str, max_calls: int, per_seconds: int, by: str = "auto"):
    """FastAPI dependency. `by`: 'auto' (signed-in user, else IP), 'ip' or 'user'. It resolves the user itself
    (memoised per request), so it works as a route-decorator dependency regardless of declaration order."""

    async def dependency(request: Request, user: Optional[Dict[str, Any]] = Depends(optional_user)) -> None:
        uid = str(user["id"]) if user else None
        if by == "ip" or (by == "auto" and not uid):
            ident = f"ip:{client_ip(request)}"
        else:
            ident = f"u:{uid}"
        count, reset = await cache.incr(f"rl:{name}:{ident}", per_seconds)
        if count > max_calls:
            raise HTTPException(status_code=429, detail="Too many requests, please slow down",
                                headers={"Retry-After": str(reset)})

    return dependency
