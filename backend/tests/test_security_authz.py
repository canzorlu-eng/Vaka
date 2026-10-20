"""Authentication and authorization: anonymous rejection, bad cookies, logout, tenant isolation, admin, role escalation."""
import re
import uuid

import pytest
from fastapi.routing import APIRoute

import auth
import db
import repo
import server
from conftest import CASE_ID

PUBLIC = {
    ("GET", "/api/health"), ("GET", "/api/ready"), ("GET", "/api/auth/config"), ("GET", "/api/auth/google/login"),
    ("GET", "/api/auth/google/callback"), ("GET", "/api/auth/me"), ("POST", "/api/auth/logout"),
    ("GET", "/api/topics"), ("GET", "/api/cases"), ("GET", "/api/cases/{case_id}"), ("GET", "/api/demo"),
    # billing: public price list; callback/webhook are authenticated by the provider token/signature, not a cookie
    ("GET", "/api/billing/plans"), ("GET", "/api/billing/callback"), ("POST", "/api/billing/callback"),
    ("POST", "/api/billing/webhook"),
}
UUID_ = str(uuid.uuid4())


def _api_routes():
    out = []
    for r in server.app.routes:
        if isinstance(r, APIRoute) and r.path.startswith("/api/"):
            for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                out.append((m, r.path))
    return out


def _fill(path: str) -> str:
    return re.sub(r"\{[^}]+\}", UUID_, path)


def test_route_inventory_is_not_empty():
    assert len(_api_routes()) >= 15


async def test_every_non_public_route_rejects_anonymous(world):
    offenders = []
    for method, path in _api_routes():
        if (method, path) in PUBLIC:
            continue
        r = await world.anon.req(method, _fill(path), json_body={}, headers={"Idempotency-Key": "abcdefgh12345"})
        if r.status_code != 401:
            offenders.append((method, path, r.status_code))
    assert not offenders, f"routes reachable without a session: {offenders}"


async def test_public_whitelist_has_no_stale_entries():
    paths = set(_api_routes())
    # billing is optional; everything else in the whitelist must still exist
    stale = {p for p in PUBLIC if p not in paths and "/billing/" not in p[1]}
    assert not stale


@pytest.mark.parametrize("cookie", ["garbage", "", "a" * 5000, "x'; DROP TABLE users;--", "%00", "Bearer abc"])
async def test_garbage_cookies_are_rejected(world, cookie):
    r = await world.http.get("/api/sessions", headers={"Cookie": f"{auth.SESSION_COOKIE}={cookie}"})
    assert r.status_code == 401
    me = await world.http.get("/api/auth/me", headers={"Cookie": f"{auth.SESSION_COOKIE}={cookie}"})
    assert me.json() == {"authenticated": False}


async def test_expired_session_is_rejected(world):
    expired = await world.make_user(ttl_days=-1)
    r = await expired.get("/api/sessions")
    assert r.status_code == 401


async def test_forged_cookie_using_stored_hash_is_rejected(world, user_a):
    stored_hash = auth._hash_token(user_a.token)
    r = await world.http.get("/api/sessions", headers={"Cookie": f"{auth.SESSION_COOKIE}={stored_hash}"})
    assert r.status_code == 401


async def test_state_cookie_cannot_be_used_as_session(world):
    r = await world.http.get("/api/auth/google/login")
    value = r.cookies.get(auth.STATE_COOKIE) or r.headers["set-cookie"].split(";")[0].split("=", 1)[1]
    r2 = await world.http.get("/api/sessions", headers={"Cookie": f"{auth.SESSION_COOKIE}={value}"})
    assert r2.status_code == 401


async def test_logout_invalidates_token_server_side(world, user_a):
    assert (await user_a.get("/api/sessions")).status_code == 200
    r = await user_a.post("/api/auth/logout")
    assert r.status_code == 200
    assert await world.count("auth_sessions", "user_id = $1", user_a.id) == 0
    # replaying the old cookie after logout must fail
    assert (await user_a.get("/api/sessions")).status_code == 401
    assert (await user_a.get("/api/auth/me")).json() == {"authenticated": False}


async def test_logout_only_ends_own_session(world, user_a, user_b):
    await user_a.post("/api/auth/logout")
    assert (await user_b.get("/api/sessions")).status_code == 200


# ----------------------------- tenant isolation -----------------------------
async def test_user_cannot_touch_another_users_session(world, fake_llm, user_a, user_b):
    sid = await world.new_session(user_a)
    assert (await user_a.get(f"/api/sessions/{sid}")).status_code == 200
    probes = [
        ("GET", f"/api/sessions/{sid}", None),
        ("POST", f"/api/sessions/{sid}/message", {"text": "hello"}),
        ("POST", f"/api/sessions/{sid}/exam", {"action_id": "x"}),
        ("POST", f"/api/sessions/{sid}/test", {"action_id": "x"}),
        ("POST", f"/api/sessions/{sid}/xray-answer", {"test_id": "x", "option_id": "y"}),
        ("POST", f"/api/sessions/{sid}/commit", {"diagnosis_id": "d"}),
        ("POST", f"/api/sessions/{sid}/score", None),
    ]
    missing = await user_b.get(f"/api/sessions/{uuid.uuid4()}")
    for method, path, body in probes:
        r = await user_b.req(method, path, json_body=body)
        assert r.status_code == 404, (method, path, r.status_code)
        assert r.json() == missing.json(), "foreign and non-existent sessions must be indistinguishable"
    assert fake_llm.count() == 0, "no LLM spend on someone else's session"
    # A's data untouched
    data = (await user_a.get(f"/api/sessions/{sid}")).json()
    assert data["transcript"] == [] and data["diagnosis_id"] is None
    assert (await user_b.get("/api/sessions")).json()["items"] == []


async def test_user_cannot_read_or_score_foreign_report(world, fake_llm, user_a, user_b):
    sid = await world.new_session(user_a)
    assert (await user_a.post(f"/api/sessions/{sid}/score")).status_code == 200
    assert await world.count("case_reports") == 1
    r = await user_b.post(f"/api/sessions/{sid}/score")
    assert r.status_code == 404
    assert "total" not in r.text
    assert all(i["id"] != sid for i in (await user_b.get("/api/sessions")).json()["items"])


async def test_user_cannot_see_foreign_job(world, user_a, user_b):
    job, _ = await __import__("jobs").enqueue(user_a.id, "case_generation", {"topic": "endodontics"}, "key-12345678")
    ok = await user_a.get(f"/api/jobs/{job['id']}")
    assert ok.status_code == 200
    r = await user_b.get(f"/api/jobs/{job['id']}")
    missing = await user_b.get(f"/api/jobs/{uuid.uuid4()}")
    assert r.status_code == 404 and r.json() == missing.json()
    assert (await user_b.get("/api/jobs/not-a-uuid")).status_code == 404


async def test_user_cannot_use_foreign_ai_case(world, user_a, user_b):
    cid = await world.add_ai_case(user_a.id)
    assert (await user_a.get(f"/api/cases/{cid}")).status_code == 200
    assert (await user_b.get(f"/api/cases/{cid}")).status_code == 404
    r = await user_b.post("/api/sessions", {"case_id": cid, "lang": "en"})
    assert r.status_code == 404
    assert await world.count("case_sessions", "user_id = $1", user_b.id) == 0
    assert (await user_a.post("/api/sessions", {"case_id": cid, "lang": "en"})).status_code == 200


async def test_repo_level_scoping(world, user_a, user_b):
    sid = await world.new_session(user_a)
    assert await repo.get_session(sid, user_b.id) is None
    assert await repo.update_session(sid, user_b.id, lambda cur: {**cur, "phase": "hacked"}) is None
    assert (await repo.get_session(sid, user_a.id))["phase"] == "anamnez"


# ----------------------------- admin -----------------------------
@pytest.mark.parametrize("path", ["/api/admin/overview", "/api/admin/users"])
async def test_admin_endpoints_role_gate(world, user_a, admin, path):
    assert (await world.anon.get(path)).status_code == 401
    assert (await user_a.get(path)).status_code == 403
    assert (await admin.get(path)).status_code == 200


async def test_admin_users_lists_everyone_for_admin_only(world, user_a, admin):
    emails = {u["email"] for u in (await admin.get("/api/admin/users")).json()}
    assert {"alice@example.com", "root@example.com"} <= emails


async def test_role_cannot_be_escalated_through_request_bodies(world, fake_llm, user_a):
    sid = await world.new_session(user_a)
    evil = {"role": "admin", "is_admin": True, "user_id": str(uuid.uuid4())}
    attempts = [
        ("POST", "/api/sessions", {"case_id": CASE_ID, "lang": "tr", **evil}),
        ("POST", f"/api/sessions/{sid}/commit", {"diagnosis_id": "x", **evil}),
        ("POST", f"/api/sessions/{sid}/message", {"text": "hi", **evil}),
        ("POST", "/api/auth/logout", evil),
    ]
    for method, path, body in attempts:
        await user_a.req(method, path, json_body=body, headers={"X-User-Role": "admin", "X-Admin": "1"})
    if (await user_a.get("/api/auth/me")).json()["authenticated"]:
        assert await db.pool().fetchval("SELECT role FROM users WHERE id = $1", user_a.id) == "user"
    assert (await user_a.get("/api/admin/overview")).status_code in (401, 403)


async def test_users_table_rejects_unknown_role(world, user_a):
    with pytest.raises(Exception):
        await db.pool().execute("UPDATE users SET role = 'root' WHERE id = $1", user_a.id)


# ----------------------------- OAuth -----------------------------
@pytest.mark.parametrize("nxt,expected", [
    ("/topics", "/topics"), ("/a/b?x=1", "/a/b?x=1"), ("//evil.com", "/"), ("https://evil.com", "/"),
    ("/\\evil.com", "/"), ("", "/"), (None, "/"), ("evil.com", "/"), ("javascript:alert(1)", "/"),
])
def test_safe_next(nxt, expected):
    assert auth._safe_next(nxt) == expected


class _FakeResp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("bad", request=None, response=None)

    def json(self):
        return self._d


def _fake_google(profile, token_status=200):
    import httpx
    from types import SimpleNamespace

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, data=None, **k):
            assert data["grant_type"] == "authorization_code" and data["code_verifier"]
            return _FakeResp({"access_token": "tok"}, token_status)

        async def get(self, url, headers=None, **k):
            assert headers["Authorization"] == "Bearer tok"
            return _FakeResp(profile)

    return SimpleNamespace(AsyncClient=Client, HTTPError=httpx.HTTPError)


async def _start_login(world, nxt=None):
    r = await world.http.get("/api/auth/google/login", params={"next": nxt} if nxt else None)
    assert r.status_code == 302
    state = re.search(r"state=([^&]+)", r.headers["location"]).group(1)
    cookie = re.search(rf"{auth.STATE_COOKIE}=([^;]+)", r.headers["set-cookie"]).group(1)
    return state, cookie, r


def _decode(raw_cookie):
    from http.cookies import SimpleCookie
    jar = SimpleCookie()
    jar.load(f"{auth.STATE_COOKIE}={raw_cookie}")
    return jar[auth.STATE_COOKIE].value


async def _callback(world, state, cookie, code="abc"):
    headers = {"Cookie": f"{auth.STATE_COOKIE}={cookie}"} if cookie is not None else {}
    params = {k: v for k, v in (("code", code), ("state", state)) if v is not None}
    return await world.http.get("/api/auth/google/callback", params=params, headers=headers)


async def test_login_redirect_sets_pkce_and_hardened_state_cookie(world):
    state, cookie, r = await _start_login(world, "//evil.com")
    assert "code_challenge_method=S256" in r.headers["location"] and "accounts.google.com" in r.headers["location"]
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "samesite=lax" in sc and "path=/api/auth" in sc
    assert auth._unsign(_decode(cookie)).split("|", 2)[2] == "/"


async def test_oauth_happy_path_creates_user_and_secure_cookie(world, monkeypatch):
    monkeypatch.setattr(auth, "httpx", _fake_google({"sub": "g-1", "email": "New.User@Example.com", "email_verified": True,
                                                     "name": "New User", "picture": "http://x/y.png"}))
    state, cookie, _ = await _start_login(world, "/topics?lang=en")
    r = await _callback(world, state, cookie)
    assert r.status_code == 302 and r.headers["location"] == "/topics?lang=en"
    cookies = r.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith(auth.SESSION_COOKIE + "="))
    low = session_cookie.lower()
    assert "httponly" in low and "samesite=lax" in low and "path=/" in low
    token = session_cookie.split("=", 1)[1].split(";")[0]
    me = (await world.http.get("/api/auth/me", headers={"Cookie": f"{auth.SESSION_COOKIE}={token}"})).json()
    assert me["authenticated"] and me["user"]["email"] == "New.User@Example.com" and me["user"]["role"] == "user"
    assert me["plan"] == "free"
    # the token is stored hashed, never in clear
    assert await world.count("auth_sessions", "token_hash = $1", auth._hash_token(token)) == 1
    assert await world.count("auth_sessions", "token_hash = $1", token) == 0
    # state cookie is cleared
    assert any(c.startswith(auth.STATE_COOKIE + "=") and ("max-age=0" in c.lower() or "expires" in c.lower()) for c in cookies)


async def test_oauth_provider_cannot_set_role_but_admin_email_is_admin(world, monkeypatch):
    monkeypatch.setattr(auth, "httpx", _fake_google({"sub": "g-2", "email": "plain@example.com", "email_verified": True,
                                                     "role": "admin"}))
    state, cookie, _ = await _start_login(world)
    await _callback(world, state, cookie)
    assert await db.pool().fetchval("SELECT role FROM users WHERE email = 'plain@example.com'") == "user"
    monkeypatch.setattr(auth, "httpx", _fake_google({"sub": "g-3", "email": "BOSS@example.com", "email_verified": True}))
    state, cookie, _ = await _start_login(world)
    await _callback(world, state, cookie)
    assert await db.pool().fetchval("SELECT role FROM users WHERE google_sub = 'g-3'") == "admin"


async def test_oauth_unverified_email_is_refused(world, monkeypatch):
    monkeypatch.setattr(auth, "httpx", _fake_google({"sub": "g-4", "email": "boss@example.com", "email_verified": False}))
    state, cookie, _ = await _start_login(world)
    r = await _callback(world, state, cookie)
    assert r.headers["location"] == "/?login=unverified"
    assert await world.count("users") == 0


async def test_oauth_open_redirect_blocked_on_callback(world, monkeypatch):
    monkeypatch.setattr(auth, "httpx", _fake_google({"sub": "g-5", "email": "r@example.com", "email_verified": True}))
    for evil in ("https://evil.com", "//evil.com/x", "/\\evil.com"):
        state, cookie, _ = await _start_login(world, evil)
        r = await _callback(world, state, cookie)
        assert r.headers["location"] == "/"


async def test_oauth_callback_rejects_bad_or_missing_state(world, monkeypatch):
    monkeypatch.setattr(auth, "httpx", _fake_google({"sub": "g-6", "email": "s@example.com", "email_verified": True}))
    state, cookie, _ = await _start_login(world)
    cases = [
        await _callback(world, "wrong-state", cookie),
        await _callback(world, None, cookie),
        await _callback(world, state, None),
        await _callback(world, state, cookie, code=None),
        await world.http.get("/api/auth/google/callback", params={"error": "access_denied", "state": state},
                             headers={"Cookie": f"{auth.STATE_COOKIE}={cookie}"}),
    ]
    for r in cases:
        assert r.status_code == 302 and r.headers["location"] == "/?login=failed"
        assert auth.SESSION_COOKIE + "=" not in r.headers.get("set-cookie", "")
    assert await world.count("users") == 0


async def test_oauth_state_cookie_tampering_rejected(world, monkeypatch):
    monkeypatch.setattr(auth, "httpx", _fake_google({"sub": "g-7", "email": "t@example.com", "email_verified": True}))
    state, cookie, _ = await _start_login(world, "/safe")
    plain = auth._unsign(_decode(cookie))
    s, verifier, _nxt = plain.split("|", 2)
    forged_unsigned = f"{s}|{verifier}|https://evil.com"
    decoded = _decode(cookie)
    flipped_mac = decoded[:-1] + ("0" if decoded[-1] != "0" else "1")
    other_secret_sig = forged_unsigned + "." + "0" * 64
    for bad in (forged_unsigned, flipped_mac, other_secret_sig, "garbage", ""):
        r = await _callback(world, state, bad)
        assert r.headers["location"] == "/?login=failed", bad
    assert await world.count("users") == 0


async def test_oauth_token_exchange_failure_redirects_to_failed(world, monkeypatch):
    monkeypatch.setattr(auth, "httpx", _fake_google({"sub": "g-8", "email": "f@example.com", "email_verified": True},
                                                    token_status=400))
    state, cookie, _ = await _start_login(world)
    r = await _callback(world, state, cookie)
    assert r.headers["location"] == "/?login=failed"
    assert await world.count("users") == 0
