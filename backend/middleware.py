"""Pure-ASGI middleware: request id + access log + metrics, body-size limit, CSRF origin check,
global per-IP rate limit and security headers. Nothing here logs bodies, headers or query strings."""
import json
import logging
import os
import time
import uuid
from collections import Counter
from typing import Dict, List, Tuple
from urllib.parse import urlparse

import cache
from config import settings
from logging_setup import request_id_var, user_id_var

logger = logging.getLogger("vaka.access")
SLOW_REQUEST_S = float(os.environ.get("SLOW_REQUEST_S", "2.0"))
SESSION_COOKIE = "vaka_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Provider-to-us calls that cannot carry our Origin; both are authenticated by signature / one-time token instead.
CSRF_EXEMPT_PATHS = {"/api/billing/webhook", "/api/billing/callback"}

METRICS: Dict[str, Counter] = {"status": Counter(), "paths": Counter()}
INFLIGHT = {"n": 0}


def _csv_env(name: str) -> List[str]:
    return [x.strip() for x in os.environ.get(name, "").split(",") if x.strip()]


def _csp() -> str:
    script = " ".join(["'self'", *_csv_env("CSP_EXTRA_SCRIPT")])
    connect = " ".join(["'self'", *_csv_env("CSP_EXTRA_CONNECT")])
    frame = " ".join(_csv_env("CSP_EXTRA_FRAME")) or "'none'"
    form = " ".join(["'self'", *_csv_env("CSP_EXTRA_FORM")])
    return "; ".join([
        "default-src 'self'",
        f"script-src {script}",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com data:",
        "img-src 'self' data: blob: https:",
        "media-src 'self' data: blob:",
        f"connect-src {connect}",
        f"frame-src {frame}",
        f"form-action {form}",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "base-uri 'self'",
    ])


SECURITY_HEADERS: List[Tuple[bytes, bytes]] = [
    (b"content-security-policy", _csp().encode()),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"camera=(), geolocation=(), microphone=(self)"),
]
if settings.secure_cookies:
    SECURITY_HEADERS.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))


def _header(scope, name: bytes) -> str:
    for k, v in scope.get("headers", []):
        if k == name:
            return v.decode("latin-1")
    return ""


async def _send_json(send, status: int, body: dict, extra: List[Tuple[bytes, bytes]] = ()) -> None:
    raw = json.dumps(body).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(raw)).encode()), *extra]})
    await send({"type": "http.response.body", "body": raw})


class RequestContextMiddleware:
    """Request id, structured access log, slow-request warning, metrics and security headers."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        inbound = _header(scope, b"x-request-id")
        rid = inbound if inbound and len(inbound) <= 64 and inbound.replace("-", "").isalnum() else uuid.uuid4().hex
        request_id_var.set(rid)
        user_id_var.set("-")
        scope.setdefault("state", {})["request_id"] = rid
        start = time.perf_counter()
        status = {"code": 500}
        INFLIGHT["n"] += 1

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", rid.encode()))
                if scope["path"].startswith("/api/"):
                    headers.append((b"cache-control", b"no-store")) if not any(k == b"cache-control" for k, _ in headers) else None
                present = {k for k, _ in headers}
                headers.extend(h for h in SECURITY_HEADERS if h[0] not in present)
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:  # noqa: BLE001
            logger.exception("unhandled error", extra={"extra_fields": {"path": scope["path"], "method": scope["method"]}})
            if status["code"] == 500:
                await _send_json(send, 500, {"detail": "Internal server error", "request_id": rid})
        finally:
            INFLIGHT["n"] -= 1
            elapsed = time.perf_counter() - start
            METRICS["status"][str(status["code"])[0] + "xx"] += 1
            path = scope["path"]
            fields = {"method": scope["method"], "path": path, "status": status["code"],
                      "duration_ms": round(elapsed * 1000)}
            if path.startswith("/api/") and path != "/api/health":
                if elapsed > SLOW_REQUEST_S:
                    logger.warning("slow request", extra={"extra_fields": fields})
                elif status["code"] >= 500:
                    logger.error("request failed", extra={"extra_fields": fields})
                else:
                    logger.info("request", extra={"extra_fields": fields})


class BodyLimitMiddleware:
    """Reject oversized request bodies (declared or streamed) before they reach route code."""

    def __init__(self, app, max_bytes: int):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in SAFE_METHODS:
            return await self.app(scope, receive, send)
        declared = _header(scope, b"content-length")
        if declared.isdigit() and int(declared) > self.max_bytes:
            return await _send_json(send, 413, {"detail": "Request body too large"})
        received = {"n": 0}
        state = {"too_large": False, "started": False}

        async def limited_receive():
            message = await receive()
            if message["type"] == "http.request":
                received["n"] += len(message.get("body", b""))
                if received["n"] > self.max_bytes:
                    state["too_large"] = True
                    return {"type": "http.disconnect"}  # stop the app from reading further
            return message

        async def tracking_send(message):
            if message["type"] == "http.response.start":
                state["started"] = True
            if not state["too_large"]:
                await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except Exception:  # noqa: BLE001 - the app may fail once its body stream was cut
            if not state["too_large"]:
                raise
        if state["too_large"]:
            await _send_json(send, 413, {"detail": "Request body too large"})


class _TooLarge(Exception):
    pass


class CsrfOriginMiddleware:
    """Defence in depth on top of SameSite=Lax cookies: state-changing requests that carry the session
    cookie must come from an allowed Origin (or Referer)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in SAFE_METHODS or scope["path"] in CSRF_EXEMPT_PATHS:
            return await self.app(scope, receive, send)
        if SESSION_COOKIE + "=" in _header(scope, b"cookie"):
            origin = _header(scope, b"origin")
            if not origin:
                ref = _header(scope, b"referer")
                if ref:
                    p = urlparse(ref)
                    origin = f"{p.scheme}://{p.netloc}"
            if origin not in settings.allowed_origins:
                return await _send_json(send, 403, {"detail": "Cross-site request blocked"})
        await self.app(scope, receive, send)


class GlobalRateLimitMiddleware:
    """Coarse per-IP ceiling (DoS/abuse); finer per-route limits are dependencies in the routers."""

    def __init__(self, app, per_minute: int):
        self.app, self.per_minute = app, per_minute

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/") or scope["path"] == "/api/health":
            return await self.app(scope, receive, send)
        client = scope.get("client")
        ip = client[0] if client else "unknown"
        count, reset = await cache.incr(f"rl:global:{ip}", 60)
        if count > self.per_minute:
            return await _send_json(send, 429, {"detail": "Too many requests"}, [(b"retry-after", str(reset).encode())])
        await self.app(scope, receive, send)
