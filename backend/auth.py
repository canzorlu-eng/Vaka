"""Google sign-in (OAuth 2.0 authorization-code flow + PKCE) with server-side sessions.
No passwords are stored, so there is no password-reset surface; account recovery is Google's.
Authorization is enforced by the dependencies below and by user_id-scoped SQL in repo.py."""
import base64
import hashlib
import hmac
import logging
import secrets
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import asyncpg
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

import repo
from config import settings
from identity import hash_token, optional_user
from middleware import SESSION_COOKIE
from plans import usage_snapshot
from ratelimit import limit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
STATE_COOKIE = "vaka_oauth"


def _sign(value: str) -> str:
    mac = hmac.new(settings.secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{mac}"


def _unsign(signed: str) -> Optional[str]:
    value, _, mac = signed.rpartition(".")
    expected = hmac.new(settings.secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()
    return value if value and hmac.compare_digest(mac, expected) else None


_hash_token = hash_token  # kept for tests/tools that import it from here


def _redirect_uri() -> str:
    return f"{settings.public_base_url}/api/auth/google/callback"


def _safe_next(path: Optional[str]) -> str:
    """Only same-site relative paths (prevents open redirects)."""
    if path and path.startswith("/") and not path.startswith("//") and "\\" not in path:
        return path
    return "/"


# ----------------------------- dependencies -----------------------------
async def current_user(user: Optional[Dict[str, Any]] = Depends(optional_user)) -> Dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


async def require_admin(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ----------------------------- routes -----------------------------
@router.get("/config")
async def auth_config():
    return {"google_enabled": bool(settings.google_client_id and settings.google_client_secret)}


@router.get("/google/login", dependencies=[Depends(limit("auth-login", 20, 600, by="ip"))])
async def google_login(next: Optional[str] = None):
    if not (settings.google_client_id and settings.google_client_secret):
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params = {
        "client_id": settings.google_client_id, "redirect_uri": _redirect_uri(), "response_type": "code",
        "scope": "openid email profile", "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256", "prompt": "select_account", "access_type": "online",
    }
    resp = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=302)
    resp.set_cookie(STATE_COOKIE, _sign(f"{state}|{verifier}|{_safe_next(next)}"), max_age=600, httponly=True,
                    secure=settings.secure_cookies, samesite="lax", path="/api/auth")
    return resp


@router.get("/google/callback", dependencies=[Depends(limit("auth-callback", 30, 600, by="ip"))])
async def google_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None,
                          error: Optional[str] = None):
    raw = request.cookies.get(STATE_COOKIE)
    parts = (_unsign(raw) or "").split("|", 2) if raw else []
    if error or not code or not state or len(parts) != 3 or not hmac.compare_digest(parts[0], state):
        logger.warning("oauth callback rejected", extra={"extra_fields": {"google_error": error or "-"}})
        return RedirectResponse("/?login=failed", status_code=302)
    _, verifier, nxt = parts
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            tok = await client.post(GOOGLE_TOKEN_URL, data={
                "code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
                "redirect_uri": _redirect_uri(), "grant_type": "authorization_code", "code_verifier": verifier})
            tok.raise_for_status()
            info = await client.get(GOOGLE_USERINFO_URL,
                                    headers={"Authorization": f"Bearer {tok.json()['access_token']}"})
            info.raise_for_status()
            profile = info.json()
    except (httpx.HTTPError, KeyError) as e:
        logger.error("google token exchange failed: %s", type(e).__name__)
        return RedirectResponse("/?login=failed", status_code=302)
    if not profile.get("email") or not profile.get("email_verified"):
        return RedirectResponse("/?login=unverified", status_code=302)

    try:
        user = await repo.upsert_google_user(profile["sub"], profile["email"], True, profile.get("name"),
                                             profile.get("picture"), settings.admin_emails)
    except asyncpg.UniqueViolationError:  # same email under a different Google subject
        logger.warning("oauth sign-in rejected: email already bound to another Google account")
        return RedirectResponse("/?login=failed", status_code=302)
    token = secrets.token_urlsafe(32)
    await repo.create_auth_session(_hash_token(token), user["id"], settings.session_ttl_days,
                                   request.headers.get("user-agent", ""))
    resp = RedirectResponse(_safe_next(nxt), status_code=302)
    resp.set_cookie(SESSION_COOKIE, token, max_age=settings.session_ttl_days * 86400, httponly=True,
                    secure=settings.secure_cookies, samesite="lax", path="/")
    resp.delete_cookie(STATE_COOKIE, path="/api/auth")
    logger.info("user signed in", extra={"extra_fields": {"user_id": str(user["id"])}})
    return resp


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await repo.delete_auth_session(_hash_token(token))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: Optional[Dict[str, Any]] = Depends(optional_user)):
    if not user:
        return {"authenticated": False}
    return {"authenticated": True,
            "user": {"id": str(user["id"]), "email": user["email"], "name": user["name"],
                     "picture": user["picture"], "role": user["role"]},
            **await usage_snapshot(user)}
