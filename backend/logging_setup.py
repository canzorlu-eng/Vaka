"""Structured JSON logging with request-id correlation and secret redaction (OWASP Logging Cheat Sheet)."""
import contextvars
import json
import logging
import re
import sys
from datetime import datetime, timezone

from config import settings

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="-")

_REDACT = [
    (re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), "[REDACTED_GOOGLE_KEY]"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)postgres(?:ql)?://[^@\s/]+@"), "postgresql://[REDACTED]@"),
    (re.compile(r"(?i)((?:api[_-]?key|secret|token|password|authorization|cookie|set-cookie|signature)[\"']?\s*[:=]\s*[\"']?)[^\s,\"'}]+"),
     r"\1[REDACTED]"),
]


def redact(text: str) -> str:
    for pattern, repl in _REDACT:
        text = pattern.sub(repl, text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
            "request_id": request_id_var.get(),
            "user_id": user_id_var.get(),
            "env": settings.env,
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def setup() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level.upper())
    for noisy in ("httpx", "httpcore", "google_genai.models", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)  # access logs come from our middleware (no query strings)
