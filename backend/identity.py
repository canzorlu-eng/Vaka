"""Request identity resolution shared by auth dependencies and rate limiting (kept separate to avoid import cycles)."""
import hashlib
from typing import Any, Dict, Optional

from fastapi import Request

import repo
from logging_setup import user_id_var
from middleware import SESSION_COOKIE


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def optional_user(request: Request) -> Optional[Dict[str, Any]]:
    """The signed-in user for this request (or None). Resolved once per request and memoised on request.state."""
    cached = getattr(request.state, "user", None)
    if cached is not None:
        return cached
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    user = await repo.user_for_token(hash_token(token))
    if user:
        request.state.user = user
        request.state.user_id = str(user["id"])
        user_id_var.set(str(user["id"]))
    return user
