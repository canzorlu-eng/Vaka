"""Public catalogue API, session flow smoke tests and health/readiness endpoints."""
import pytest

import db
from case_store import CASES, TOPICS
from conftest import CASE_ID


async def test_cases_pagination_headers_and_slicing(world):
    total = len(CASES)
    r = await world.anon.get("/api/cases", params={"limit": 10, "offset": 0})
    assert r.status_code == 200 and int(r.headers["x-total-count"]) == total and len(r.json()) == min(10, total)
    ids = []
    offset = 0
    while True:
        page = (await world.anon.get("/api/cases", params={"limit": 7, "offset": offset})).json()
        if not page:
            break
        ids += [c["case_id"] for c in page]
        offset += 7
    assert len(ids) == total and len(set(ids)) == total
    beyond = await world.anon.get("/api/cases", params={"limit": 5, "offset": total + 50})
    assert beyond.status_code == 200 and beyond.json() == [] and int(beyond.headers["x-total-count"]) == total


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"limit": -1}, {"offset": -1}, {"limit": "abc"},
                                    {"lang": "de"}, {"difficulty": "impossible"}])
async def test_cases_query_bounds_are_validated(world, params):
    assert (await world.anon.get("/api/cases", params=params)).status_code == 422


async def test_cases_filters_by_topic_and_difficulty_and_language(world):
    topic = TOPICS[0]["id"]
    r = await world.anon.get("/api/cases", params={"topic": topic, "difficulty": "easy", "limit": 100, "lang": "en"})
    expected = [c for c in CASES if c["topic"] == topic and c["difficulty"] == "easy"]
    assert int(r.headers["x-total-count"]) == len(expected)
    assert {c["case_id"] for c in r.json()} == {c["case_id"] for c in expected}
    assert all(c["topic"] == topic and c["difficulty"] == "easy" for c in r.json())
    assert r.json()[0]["title"] == expected[0]["title"]["en"]
    assert (await world.anon.get("/api/cases", params={"topic": "no-such-topic"})).json() == []


async def test_case_list_does_not_leak_answers(world):
    r = await world.anon.get("/api/cases", params={"limit": 100})
    assert "hidden_facts" not in r.text and "correct" not in r.text
    detail = (await world.anon.get(f"/api/cases/{CASE_ID}")).json()
    assert "hidden_facts" not in detail and all("correct" not in o for o in detail["diagnosis_options"])
    assert "correct" not in str(detail["tests"])


async def test_case_detail_404_for_unknown(world):
    assert (await world.anon.get("/api/cases/does-not-exist")).status_code == 404
    assert (await world.anon.get("/api/cases/gen-000000000000")).status_code == 404


async def test_topics_counts_are_consistent_with_cases(world):
    topics = (await world.anon.get("/api/topics")).json()
    assert [t["id"] for t in topics] == [t["id"] for t in TOPICS]
    total = 0
    for t in topics:
        assert t["count"] == sum(t["levels"].values()) == len([c for c in CASES if c["topic"] == t["id"]])
        listed = await world.anon.get("/api/cases", params={"topic": t["id"], "limit": 1})
        assert int(listed.headers["x-total-count"]) == t["count"]
        total += t["count"]
    assert total == len(CASES) == int((await world.anon.get("/api/cases", params={"limit": 1})).headers["x-total-count"])
    assert {"id", "icon", "color", "name", "blurb"} <= set(topics[0])


async def test_topics_language_switch(world):
    tr = (await world.anon.get("/api/topics", params={"lang": "tr"})).json()
    en = (await world.anon.get("/api/topics", params={"lang": "en"})).json()
    assert [t["name"] for t in tr] == [t["name"]["tr"] for t in TOPICS]
    assert [t["name"] for t in en] == [t["name"]["en"] for t in TOPICS]


async def test_anonymous_users_never_see_ai_cases(world, user_a):
    owned = await world.add_ai_case(user_a.id, topic=TOPICS[0]["id"])
    legacy = await world.add_ai_case(None, topic=TOPICS[0]["id"])
    anon_cases = (await world.anon.get("/api/cases", params={"limit": 100})).json()
    anon_ids = {c["case_id"] for c in anon_cases}
    assert owned not in anon_ids and legacy not in anon_ids
    assert not any(c["generated"] for c in anon_cases)
    assert int((await world.anon.get("/api/cases")).headers["x-total-count"]) == len(CASES)
    assert (await world.anon.get("/api/topics")).json() == (await world.anon.get("/api/topics")).json()
    anon_topic = {t["id"]: t["count"] for t in (await world.anon.get("/api/topics")).json()}
    assert anon_topic[TOPICS[0]["id"]] == len([c for c in CASES if c["topic"] == TOPICS[0]["id"]])
    assert (await world.anon.get(f"/api/cases/{owned}")).status_code == 404


async def test_legacy_ownerless_ai_case_detail_is_not_public(world):
    """Ownerless (pre-accounts) AI cases are hidden from the anonymous list, so detail must also require a login."""
    legacy = await world.add_ai_case(None)
    assert (await world.anon.get(f"/api/cases/{legacy}")).status_code == 404


async def test_signed_in_user_sees_own_ai_cases_in_counts(world, user_a, user_b):
    topic = TOPICS[0]["id"]
    owned = await world.add_ai_case(user_a.id, topic=topic)
    base = len([c for c in CASES if c["topic"] == topic])
    a_topics = {t["id"]: t["count"] for t in (await user_a.get("/api/topics")).json()}
    b_topics = {t["id"]: t["count"] for t in (await user_b.get("/api/topics")).json()}
    assert a_topics[topic] == base + 1 and b_topics[topic] == base
    listed = (await user_a.get("/api/cases", params={"topic": topic, "limit": 100})).json()
    assert owned in [c["case_id"] for c in listed]
    assert int((await user_a.get("/api/cases", params={"topic": topic})).headers["x-total-count"]) == base + 1


async def test_cache_control_differs_for_anonymous_and_signed_in(world, user_a):
    assert "public" in (await world.anon.get("/api/topics")).headers["cache-control"]
    assert (await user_a.get("/api/topics")).headers["cache-control"].startswith("private")


async def test_demo_endpoint(world):
    r = await world.anon.get("/api/demo", params={"lang": "en"})
    body = r.json()
    assert r.status_code == 200 and body["script"] and body["diagnosis"] and body["case"]["case_id"] == "acute-pulpitis"


# ----------------------------- sessions happy path -----------------------------
async def test_full_session_flow(world, fake_llm, user_a):
    case = CASES[0]
    created = await user_a.post("/api/sessions", {"case_id": case["case_id"], "lang": "en"})
    body = created.json()
    sid = body["id"]
    assert created.status_code == 200 and body["transcript"] == [] and "hidden_facts" not in body["case"]
    chat = (await user_a.post(f"/api/sessions/{sid}/message", {"text": "When did it start?"})).json()
    assert chat["reply"] == "Evet, ağrım var."
    exam = case["exam_actions"][0]["id"]
    assert (await user_a.post(f"/api/sessions/{sid}/exam", {"action_id": exam})).status_code == 200
    assert (await user_a.post(f"/api/sessions/{sid}/exam", {"action_id": "nope"})).status_code == 404
    assert (await user_a.post(f"/api/sessions/{sid}/test", {"action_id": "nope"})).status_code == 404
    dx = next(d["id"] for d in case["diagnosis_options"] if d["correct"])
    tx = next(d["id"] for d in case["treatment_options"] if d["correct"])
    assert (await user_a.post(f"/api/sessions/{sid}/commit", {"diagnosis_id": dx, "treatment_id": tx})).json()["ok"]
    report = (await user_a.post(f"/api/sessions/{sid}/score")).json()
    assert report["diagnosis"]["is_correct"] and report["treatment"]["is_correct"] and 0 < report["total"] <= 100
    assert report["narrative"] == "Iyi is."
    listing = (await user_a.get("/api/sessions")).json()
    assert listing["items"][0]["id"] == sid and listing["items"][0]["grade"] == report["grade"]
    assert (await user_a.get(f"/api/sessions/{sid}")).json()["ended"] is True


async def test_unknown_case_cannot_start_a_session(world, user_a):
    assert (await user_a.post("/api/sessions", {"case_id": "nope", "lang": "tr"})).status_code == 404
    assert await world.count("case_sessions") == 0


async def test_session_list_pagination(world, user_a):
    await world.subscribe(user_a.id)
    for _ in range(5):
        await world.new_session(user_a)
    first = (await user_a.get("/api/sessions", params={"limit": 2})).json()
    assert len(first["items"]) == 2 and first["next_before"]
    second = (await user_a.get("/api/sessions", params={"limit": 2, "before": first["next_before"]})).json()
    assert not {i["id"] for i in first["items"]} & {i["id"] for i in second["items"]}
    assert (await user_a.get("/api/sessions", params={"limit": 0})).status_code == 422
    assert (await user_a.get("/api/sessions", params={"limit": 51})).status_code == 422


async def test_session_list_includes_localised_case_titles(world, user_a):
    await world.new_session(user_a)  # starts CASE_ID in Turkish
    item = (await user_a.get("/api/sessions")).json()["items"][0]
    expected = (await world.anon.get(f"/api/cases/{item['case_id']}", params={"lang": "tr"})).json()["title"]
    assert item["case_title"] == expected and item["case_title"] != item["case_id"]


async def test_session_list_survives_a_case_that_no_longer_exists(world, user_a):
    sid = await world.new_session(user_a)
    await db.pool().execute("UPDATE case_sessions SET case_id = 'gen-deleted' WHERE id = $1::uuid", str(sid))
    item = (await user_a.get("/api/sessions")).json()["items"][0]
    assert item["case_title"] is None


async def test_malformed_session_ids_are_404(world, user_a):
    for sid in ("zzz", "123", "%2e%2e%2fetc", "00000000-0000-0000-0000-000000000000"):
        assert (await user_a.get(f"/api/sessions/{sid}")).status_code == 404


# ----------------------------- health -----------------------------
async def test_health_and_ready_ok(world):
    assert (await world.anon.get("/api/health")).json() == {"status": "ok"}
    r = await world.anon.get("/api/ready")
    assert r.status_code == 200 and r.json() == {"status": "ok", "database": True, "cache": True}


async def test_ready_returns_503_when_database_down(world, monkeypatch):
    async def down():
        return False

    monkeypatch.setattr(db, "ping", down)
    r = await world.anon.get("/api/ready")
    assert r.status_code == 503 and r.json()["database"] is False and r.json()["status"] == "degraded"
    assert (await world.anon.get("/api/health")).status_code == 200, "liveness must not depend on the database"


async def test_ready_degraded_but_200_when_only_cache_down(world, monkeypatch):
    import cache

    async def down():
        return False

    monkeypatch.setattr(cache, "ping", down)
    r = await world.anon.get("/api/ready")
    assert r.status_code == 200 and r.json()["status"] == "degraded" and r.json()["cache"] is False


async def test_ready_exposes_nothing_sensitive(world):
    text = (await world.anon.get("/api/ready")).text
    assert "postgres" not in text and "vaka" not in text.lower().replace("vaka_test", "")


async def test_openapi_docs_available_in_development_only(world):
    assert (await world.anon.get("/api/openapi.json")).status_code == 200
