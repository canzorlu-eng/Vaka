"""Shared test infrastructure: environment, dedicated Postgres database, in-process app, actors and LLM fakes.

config.settings is read at import time, so the environment is configured BEFORE any application module is imported.
Nothing here talks to Google/Gemini/OpenAI/Redis: the cache uses its in-process fallback and llm.* is faked.
"""
import asyncio
from http.cookiejar import DefaultCookiePolicy
import json
import logging
import os
import secrets
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DB_NAME = os.environ.get("TEST_DB_NAME", f"vaka_test_{os.getpid()}")  # per-process: concurrent runs never collide
ADMIN_DSN = os.environ.get("TEST_ADMIN_DSN", "postgresql://vaka:vaka@localhost:55432/postgres")
TEST_DSN = os.environ.get("TEST_DATABASE_URL", f"postgresql://vaka:vaka@localhost:55432/{DB_NAME}")
BASE_URL = "http://localhost:8001"
ADMIN_EMAIL = "boss@example.com"
FAKE_GEMINI_KEY = "AIzaSyFAKEFAKEFAKEFAKEFAKEFAKE0123456"
FAKE_OPENAI_KEY = "sk-FAKEFAKEFAKEFAKEFAKEFAKE0123456789"

_FORCED_ENV = {
    "APP_ENV": "development", "PUBLIC_BASE_URL": BASE_URL, "CORS_ORIGINS": "", "LOG_LEVEL": "INFO",
    "AUTO_MIGRATE": "false", "DATABASE_URL": TEST_DSN, "REDIS_URL": "",
    "SECRET_KEY": "test-secret-key-0123456789-abcdefghijklmnop",
    "GOOGLE_CLIENT_ID": "test-client-id", "GOOGLE_CLIENT_SECRET": "test-client-secret",
    "ADMIN_EMAILS": ADMIN_EMAIL, "GEMINI_API_KEY": "", "OPENAI_API_KEY": "", "ALERT_WEBHOOK_URL": "",
    "JOB_WORKERS": "0", "JOB_TIMEOUT_S": "180", "JOB_MAX_ATTEMPTS": "3",
    "MAX_BODY_BYTES": "32768", "MAX_CHAT_CHARS": "600", "GLOBAL_IP_LIMIT_PER_MIN": "300",
    "USER_DAILY_COST_CAP_FREE_USD": "0.05", "USER_DAILY_COST_CAP_PRO_USD": "1.50",
    "SESSION_TTL_DAYS": "30",
}
os.environ.update(_FORCED_ENV)

import asyncpg  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

import auth  # noqa: E402
import db  # noqa: E402
import jobs  # noqa: E402
import llm  # noqa: E402
import repo  # noqa: E402
import server  # noqa: E402
from case_store import CASES  # noqa: E402

logging.getLogger().handlers[:] = []  # drop the stdout handler bound at import; tests attach their own
CASE_ID = CASES[0]["case_id"]
ORIGIN = {"Origin": BASE_URL}


# ----------------------------- database -----------------------------
async def _ensure_database() -> None:
    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", DB_NAME):
            await conn.execute(f'CREATE DATABASE "{DB_NAME}"')
    finally:
        await conn.close()


async def _tables() -> List[str]:
    conn = await asyncpg.connect(TEST_DSN)
    try:
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'")
        return [r["tablename"] for r in rows]
    finally:
        await conn.close()


async def _drop_database() -> None:
    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{DB_NAME}" WITH (FORCE)')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def _schema():
    asyncio.run(_ensure_database())
    from alembic import command
    from alembic.config import Config
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(cfg, "head")
    tables = asyncio.run(_tables())
    yield tables
    asyncio.run(_drop_database())


# ----------------------------- LLM fake -----------------------------
GENERATED_CASE_JSON = json.dumps({
    "title": {"tr": "Test vakası", "en": "Test case"}, "difficulty": "easy",
    "chief_complaint": {"tr": "Ağrı", "en": "Pain"},
    "patient": {"name": {"tr": "Ali", "en": "Al"}, "age": 33, "sex": {"tr": "Erkek", "en": "Male"},
                "setting": {"tr": "Klinik", "en": "Clinic"}, "avatar_mood": "pain"},
    "hidden_facts": [{"id": "onset", "topic": {"tr": "Başlangıç", "en": "Onset"}, "keywords": ["when", "ne zaman"],
                      "text": {"tr": "3 gün", "en": "3 days"}, "red_flag": True}],
    "exam_actions": [{"id": "perc", "label": {"tr": "Perküsyon", "en": "Percussion"},
                      "result": {"tr": "Ağrılı", "en": "Painful"}, "tooth": 36, "severity": "finding", "required": True}],
    "xray_lib_ids": [],
    "diagnosis_options": [{"id": "d1", "label": {"tr": "A", "en": "A"}, "correct": True}],
    "treatment_options": [{"id": "t1", "label": {"tr": "B", "en": "B"}, "correct": True}],
})


class FakeLLM:
    """Records calls to llm.llm_call and returns canned replies per `kind`."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.replies: Dict[str, Any] = {"chat": "Evet, ağrım var.", "coverage": "[]", "narrative": "Iyi is.",
                                        "generate": GENERATED_CASE_JSON}
        self.delay = 0.0

    def count(self, kind: Optional[str] = None) -> int:
        return len([c for c in self.calls if kind is None or c["kind"] == kind])

    async def __call__(self, system, prompt, temperature=0.7, *, user=None, kind="chat", ref=None, json_mode=False,
                       model=None):
        self.calls.append({"kind": kind, "prompt": prompt, "ref": ref, "user": user and str(user["id"])})
        if self.delay:
            await asyncio.sleep(self.delay)
        reply = self.replies.get(kind)
        if isinstance(reply, BaseException):
            raise reply
        return reply(prompt) if callable(reply) else reply


@pytest.fixture
def fake_llm(monkeypatch) -> FakeLLM:
    fake = FakeLLM()
    monkeypatch.setattr(llm, "llm_call", fake)
    monkeypatch.setattr(llm, "llm_available", lambda: True)

    async def no_tts(text, user, ref=None):
        return None
    monkeypatch.setattr(llm, "synthesize", no_tts)
    return fake


# ----------------------------- app + actors -----------------------------
class Actor:
    """A caller of the in-process app. `token` None means anonymous."""

    def __init__(self, http: httpx.AsyncClient, user: Optional[Dict[str, Any]], token: Optional[str]) -> None:
        self.http, self.user, self.token = http, user, token

    @property
    def id(self) -> uuid.UUID:
        return self.user["id"]

    def headers(self, extra: Optional[Dict[str, str]] = None, origin: bool = True) -> Dict[str, str]:
        h: Dict[str, str] = dict(ORIGIN) if origin else {}
        if self.token is not None:
            h["Cookie"] = f"{auth.SESSION_COOKIE}={self.token}"
        h.update(extra or {})
        return h

    async def req(self, method: str, path: str, *, json_body: Any = None, headers: Optional[Dict[str, str]] = None,
                  origin: bool = True, **kw) -> httpx.Response:
        return await self.http.request(method, path, json=json_body, headers=self.headers(headers, origin), **kw)

    async def get(self, path: str, **kw) -> httpx.Response:
        return await self.req("GET", path, **kw)

    async def post(self, path: str, json_body: Any = None, **kw) -> httpx.Response:
        return await self.req("POST", path, json_body=json_body, **kw)

    async def delete(self, path: str, json_body: Any = None, **kw) -> httpx.Response:
        return await self.req("DELETE", path, json_body=json_body, **kw)


class World:
    """Everything a test needs: the running app, an HTTP client and user factories."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http
        self.anon = Actor(http, None, None)

    async def make_user(self, email: Optional[str] = None, *, role: str = "user", plan: str = "free",
                        ttl_days: int = 30, sub: Optional[str] = None) -> Actor:
        email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
        user = await repo.upsert_google_user(sub or f"sub-{uuid.uuid4().hex}", email, True, "Test User", None, [])
        if role == "admin":
            await db.pool().execute("UPDATE users SET role='admin' WHERE id=$1", user["id"])
            user = await repo.get_user(user["id"])
        if plan == "pro":
            await self.subscribe(user["id"], "active")
        token = secrets.token_urlsafe(32)
        await repo.create_auth_session(auth._hash_token(token), user["id"], ttl_days, "pytest")
        return Actor(self.http, user, token)

    async def subscribe(self, user_id: uuid.UUID, status: str = "active") -> None:
        await db.pool().execute(
            """INSERT INTO subscriptions (user_id, plan, status, current_period_end)
               VALUES ($1, 'pro_monthly', $2, now() + interval '30 days')
               ON CONFLICT (user_id) DO UPDATE SET status = EXCLUDED.status""", user_id, status)

    async def new_session(self, actor: Actor, case_id: str = CASE_ID, lang: str = "tr") -> str:
        r = await actor.post("/api/sessions", {"case_id": case_id, "lang": lang})
        assert r.status_code == 200, r.text
        return r.json()["id"]

    async def add_ai_case(self, owner: Optional[uuid.UUID], case_id: Optional[str] = None,
                          topic: str = "endodontics") -> str:
        case_id = case_id or f"gen-{uuid.uuid4().hex[:12]}"
        await repo.insert_ai_case({**CASES[0], "case_id": case_id, "topic": topic, "generated": True}, owner)
        return case_id

    async def count(self, table: str, where: str = "true", *args) -> int:
        return await db.pool().fetchval(f"SELECT count(*) FROM {table} WHERE {where}", *args)


@pytest_asyncio.fixture
async def world(_schema):
    conn = await asyncpg.connect(TEST_DSN)
    try:
        await conn.execute("TRUNCATE " + ", ".join(f'"{t}"' for t in _schema) + " RESTART IDENTITY CASCADE")
    finally:
        await conn.close()
    async with server.lifespan(server.app):
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as http:
            # tests send cookies explicitly; a persistent jar would silently authenticate "anonymous" callers
            http.cookies.jar.set_policy(DefaultCookiePolicy(allowed_domains=[]))
            yield World(http)


@pytest_asyncio.fixture
async def user_a(world: World) -> Actor:
    return await world.make_user("alice@example.com")


@pytest_asyncio.fixture
async def user_b(world: World) -> Actor:
    return await world.make_user("bob@example.com")


@pytest_asyncio.fixture
async def admin(world: World) -> Actor:
    return await world.make_user("root@example.com", role="admin")


class LogCapture:
    def __init__(self, stream, raw):
        self.stream, self.raw = stream, raw

    def text(self) -> str:
        return self.stream.getvalue()


@pytest.fixture
def log_capture():
    """Captures log output through the app's real JSON formatter (which applies redaction), plus raw records."""
    import io
    import logging_setup
    stream = io.StringIO()
    raw: List[logging.LogRecord] = []

    class Collect(logging.Handler):
        def emit(self, record):
            raw.append(record)

    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging_setup.JsonFormatter())
    collector = Collect()
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.addHandler(collector)
    root.setLevel(logging.DEBUG)
    try:
        yield LogCapture(stream, raw)
    finally:
        root.removeHandler(handler)
        root.removeHandler(collector)
        root.setLevel(old_level)


@pytest.fixture
def run_jobs():
    """Drive the job queue deterministically: claim + run one pending job (no sleeping workers)."""
    async def step() -> Optional[Dict[str, Any]]:
        job = await jobs._claim()
        if job:
            await jobs._run(job)
        return job
    return step
