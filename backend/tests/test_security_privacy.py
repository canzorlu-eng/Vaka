"""Logging and privacy: secret redaction and no sensitive data in logs."""
import json
import logging

import pytest

import logging_setup
from conftest import FAKE_GEMINI_KEY, FAKE_OPENAI_KEY

SECRETS = {
    "google key": (f"calling with {FAKE_GEMINI_KEY} now", FAKE_GEMINI_KEY),
    "openai key": (f"key={FAKE_OPENAI_KEY}", FAKE_OPENAI_KEY),
    "bearer": ("Authorization: Bearer ya29.a0AfH6SMBxyz-123_abc", "ya29.a0AfH6SMBxyz-123_abc"),
    "postgres url": ("connect postgresql://vaka:s3cretpw@db.internal:5432/vaka failed", "s3cretpw"),
    "postgres short scheme": ("postgres://admin:hunter2@host/db", "hunter2"),
    "cookie": ("Cookie: vaka_session=abcDEF123456", "abcDEF123456"),
    "set-cookie": ("Set-Cookie: vaka_session=tokenvalue987; HttpOnly", "tokenvalue987"),
    "api_key kv": ("api_key=thisisasecretvalue", "thisisasecretvalue"),
    "secret json": ('{"client_secret": "shhh-very-secret"}', "shhh-very-secret"),
    "password": ("password: p@ssw0rd!", "p@ssw0rd!"),
    "signature": ("signature=deadbeefcafebabe", "deadbeefcafebabe"),
}


@pytest.mark.parametrize("name", sorted(SECRETS))
def test_redact_removes_secret(name):
    text, secret = SECRETS[name]
    out = logging_setup.redact(text)
    assert secret not in out and "REDACTED" in out


def test_redact_leaves_normal_text_alone():
    msg = "user signed in from /api/topics status=200"
    assert logging_setup.redact(msg) == msg


def test_json_formatter_redacts_messages_and_tracebacks():
    try:
        raise RuntimeError(f"upstream said key={FAKE_GEMINI_KEY}")
    except RuntimeError:
        import sys
        rec = logging.LogRecord("t", logging.ERROR, __file__, 1, f"failed with {FAKE_OPENAI_KEY}", None, sys.exc_info())
    out = logging_setup.JsonFormatter().format(rec)
    assert FAKE_GEMINI_KEY not in out and FAKE_OPENAI_KEY not in out
    assert json.loads(out)["level"] == "ERROR"


async def test_api_use_never_logs_bodies_cookies_or_secrets(world, fake_llm, user_a, log_capture, monkeypatch):
    marker = "UNIQUE-CHAT-MARKER-7f3a9c"
    sid = await world.new_session(user_a)
    r = await user_a.post(f"/api/sessions/{sid}/message", {"text": f"{marker} ağrı var"})
    assert r.status_code == 200
    await user_a.post(f"/api/sessions/{sid}/score")
    await user_a.get("/api/topics?lang=en&q=QUERY-STRING-MARKER")
    await user_a.get("/api/me/export")
    # error paths that include secrets in exception text must be redacted by the formatter
    fake_llm.replies["narrative"] = RuntimeError(f"provider rejected key {FAKE_GEMINI_KEY}")
    sid2 = await world.new_session(user_a)
    await user_a.post(f"/api/sessions/{sid2}/score")
    logging.getLogger("vaka").error("leaky %s", FAKE_GEMINI_KEY, extra={"extra_fields": {"note": "x"}})
    await user_a.get("/api/sessions", headers={"Authorization": "Bearer abc.def.ghi"})

    text = log_capture.text()
    assert text, "expected some log output"
    for needle in (marker, FAKE_GEMINI_KEY, FAKE_OPENAI_KEY, user_a.token, "QUERY-STRING-MARKER", "abc.def.ghi"):
        assert needle not in text, f"{needle!r} leaked into formatted logs"
    for rec in log_capture.raw:
        blob = rec.getMessage() + str(getattr(rec, "extra_fields", ""))
        assert marker not in blob and user_a.token not in blob and "QUERY-STRING-MARKER" not in blob


async def test_access_log_has_method_path_status_duration_without_query(world, user_a, log_capture):
    await user_a.get("/api/topics?lang=en&token=SHOULD-NOT-APPEAR")
    lines = [json.loads(line) for line in log_capture.text().splitlines() if line.startswith("{")]
    access = [line for line in lines if line["logger"] == "vaka.access" and line.get("path") == "/api/topics"]
    assert len(access) == 1
    rec = access[0]
    assert rec["method"] == "GET" and rec["status"] == 200 and isinstance(rec["duration_ms"], int)
    assert rec["request_id"] != "-"
    assert "SHOULD-NOT-APPEAR" not in log_capture.text() and "?" not in rec["path"]
    assert rec["user_id"] in ("-", str(user_a.id))


async def test_health_checks_are_not_logged(world, log_capture):
    await world.anon.get("/api/health")
    assert "vaka.access" not in log_capture.text()


async def test_5xx_is_logged_as_error_with_request_id(world, monkeypatch, log_capture):
    import catalogue

    async def boom(*a, **k):
        raise RuntimeError("kaput")

    monkeypatch.setattr(catalogue, "visible_cases", boom)
    r = await world.anon.get("/api/topics")
    assert r.status_code == 500
    text = log_capture.text()
    assert "unhandled error" in text and r.json()["request_id"] in text


async def test_job_handler_crash_logs_are_redacted(world, user_a, log_capture, monkeypatch):
    import jobs

    async def crash(job, progress):
        raise RuntimeError(f"boom {FAKE_GEMINI_KEY} postgresql://u:pw123@h/db")

    monkeypatch.setitem(jobs.HANDLERS, "crashy", crash)
    await jobs.enqueue(user_a.id, "crashy", {}, "crash-key-0001")
    await jobs._run(await jobs._claim())
    text = log_capture.text()
    assert "job handler crashed" in text
    assert FAKE_GEMINI_KEY not in text and "pw123" not in text


async def test_auth_failures_do_not_log_credentials(world, log_capture):
    await world.anon.get("/api/auth/google/callback", params={"code": "AUTHCODE-SECRET-1", "state": "STATE-SECRET-2"})
    text = log_capture.text()
    assert "AUTHCODE-SECRET-1" not in text and "STATE-SECRET-2" not in text
    assert "oauth callback rejected" in text
