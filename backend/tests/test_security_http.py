"""CSRF origin check, security headers, request ids, body/field size limits."""
import re

import pytest

from conftest import BASE_URL, CASE_ID

STATE_CHANGING = [("POST", "/api/sessions", {"case_id": CASE_ID, "lang": "tr"}), ("POST", "/api/auth/logout", None),
                  ("DELETE", "/api/me", {"confirm": "DELETE"})]


@pytest.mark.parametrize("method,path,body", STATE_CHANGING)
async def test_missing_origin_with_session_cookie_is_blocked(world, user_a, method, path, body):
    r = await user_a.req(method, path, json_body=body, origin=False)
    assert r.status_code == 403
    assert await world.count("users") == 1


@pytest.mark.parametrize("origin", ["https://evil.example", "http://localhost:8002", "null", "http://localhost:8001.evil.com",
                                    "https://localhost:8001"])
async def test_foreign_origin_is_blocked(world, user_a, origin):
    r = await user_a.post("/api/sessions", {"case_id": CASE_ID, "lang": "tr"}, headers={"Origin": origin})
    assert r.status_code == 403
    assert await world.count("case_sessions") == 0


async def test_foreign_referer_blocked_and_same_site_referer_allowed(world, user_a):
    body = {"case_id": CASE_ID, "lang": "tr"}
    bad = await user_a.req("POST", "/api/sessions", json_body=body, origin=False,
                           headers={"Referer": "https://evil.example/page"})
    assert bad.status_code == 403
    good = await user_a.req("POST", "/api/sessions", json_body=body, origin=False,
                            headers={"Referer": f"{BASE_URL}/practice"})
    assert good.status_code == 200


async def test_same_origin_post_allowed_and_get_needs_no_origin(world, user_a):
    assert (await user_a.post("/api/sessions", {"case_id": CASE_ID, "lang": "tr"})).status_code == 200
    assert (await user_a.get("/api/sessions", origin=False)).status_code == 200


async def test_cookieless_post_is_not_a_csrf_target(world):
    r = await world.anon.post("/api/sessions", {"case_id": CASE_ID}, origin=False)
    assert r.status_code == 401  # no ambient credentials -> nothing to forge; auth still enforced


async def test_cors_not_enabled_for_foreign_origins(world):
    r = await world.anon.get("/api/topics", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


@pytest.mark.parametrize("path", ["/api/health", "/api/topics", "/api/sessions", "/api/does-not-exist"])
async def test_security_headers_on_every_response(world, path):
    r = await world.anon.get(path)
    h = r.headers
    csp = h["content-security-policy"]
    for directive in ("default-src 'self'", "frame-ancestors 'none'", "object-src 'none'", "base-uri 'self'"):
        assert directive in csp
    assert "unsafe-eval" not in csp and "script-src 'self'" in csp and "'unsafe-inline'" not in csp.split("style-src")[0]
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in h["permissions-policy"] and "geolocation=()" in h["permissions-policy"]


async def test_api_responses_are_not_cacheable_by_default(world, user_a):
    r = await user_a.get("/api/sessions")
    assert r.headers["cache-control"] == "no-store"
    assert (await user_a.get("/api/auth/me")).headers["cache-control"] == "no-store"


async def test_security_headers_present_on_error_paths(world, user_a):
    r = await user_a.post("/api/sessions", {"case_id": CASE_ID}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.headers["x-content-type-options"] == "nosniff" and "x-request-id" in r.headers
    big = await user_a.post("/api/sessions", None, content=b"x" * 40_000)
    assert big.status_code == 413 and r.headers["x-frame-options"] == "DENY"


async def test_request_id_is_generated_and_echoed(world):
    r = await world.anon.get("/api/health")
    assert re.fullmatch(r"[0-9a-f]{32}", r.headers["x-request-id"])
    r2 = await world.anon.get("/api/health", headers={"X-Request-ID": "trace-abc-123"})
    assert r2.headers["x-request-id"] == "trace-abc-123"
    for bad in ("x" * 65, "has space", "a;b", "<script>"):
        r3 = await world.anon.get("/api/health", headers={"X-Request-ID": bad})
        assert r3.headers["x-request-id"] != bad and re.fullmatch(r"[0-9a-f]{32}", r3.headers["x-request-id"])


async def test_unhandled_error_returns_generic_500_with_request_id(world, monkeypatch):
    import catalogue

    async def boom(*a, **k):
        raise RuntimeError("secret internal detail postgres://u:pw@db/x")

    monkeypatch.setattr(catalogue, "visible_cases", boom)
    r = await world.anon.get("/api/topics", headers={"X-Request-ID": "req-500-test"})
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal server error", "request_id": "req-500-test"}
    assert "secret" not in r.text and "postgres" not in r.text


# ----------------------------- size limits -----------------------------
async def test_body_over_limit_is_rejected_with_413(world, user_a):
    r = await user_a.post("/api/sessions", None, content=b'{"case_id": "' + b"a" * 40_000 + b'"}',
                          headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    r2 = await world.anon.post("/api/sessions", None, content=b"x" * 32_769)
    assert r2.status_code == 413  # limit applies before auth


async def test_body_at_limit_is_not_413(world, user_a):
    r = await user_a.post("/api/sessions", None, content=b"x" * 32_768, headers={"Content-Type": "application/json"})
    assert r.status_code != 413


async def test_streamed_body_over_limit_without_content_length_is_413(world, user_a):
    async def chunks():
        for _ in range(10):
            yield b"a" * 8_000

    r = await user_a.post("/api/sessions", None, content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


async def test_chat_text_limits(world, fake_llm, user_a):
    sid = await world.new_session(user_a)
    ok = await user_a.post(f"/api/sessions/{sid}/message", {"text": "a" * 600})
    assert ok.status_code == 200
    assert (await user_a.post(f"/api/sessions/{sid}/message", {"text": "a" * 601})).status_code == 422
    assert (await user_a.post(f"/api/sessions/{sid}/message", {"text": ""})).status_code == 422
    assert (await user_a.post(f"/api/sessions/{sid}/message", {})).status_code == 422
    assert fake_llm.count("chat") == 1


async def test_other_field_length_limits(world, user_a):
    assert (await user_a.post("/api/sessions", {"case_id": "a" * 81, "lang": "tr"})).status_code == 422
    assert (await user_a.post("/api/sessions", {"case_id": CASE_ID, "lang": "xx"})).status_code == 422
    assert (await user_a.post("/api/tts", {"text": "a" * 601})).status_code == 422
