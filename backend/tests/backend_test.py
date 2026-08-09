"""Backend tests for Vaka virtual dental patient simulator."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://patient-sim-4.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

EXPECTED_CASES = {"acute-pulpitis", "apical-abscess", "dentin-sensitivity", "pericoronitis"}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- Cases ----------
class TestCases:
    def test_list_cases_tr(self, client):
        r = client.get(f"{API}/cases?lang=tr")
        assert r.status_code == 200
        data = r.json()
        assert {c["case_id"] for c in data} == EXPECTED_CASES
        # TR title check
        ap = next(c for c in data if c["case_id"] == "acute-pulpitis")
        assert "Gece" in ap["title"]

    def test_list_cases_en(self, client):
        r = client.get(f"{API}/cases?lang=en")
        assert r.status_code == 200
        data = r.json()
        ap = next(c for c in data if c["case_id"] == "acute-pulpitis")
        assert "Pain" in ap["title"] or "pain" in ap["title"]

    def test_case_detail_spoiler_free(self, client):
        r = client.get(f"{API}/cases/acute-pulpitis?lang=en")
        assert r.status_code == 200
        data = r.json()
        assert "exam_actions" in data and "tests" in data
        assert "diagnosis_options" in data and "treatment_options" in data
        # Should NOT contain 'correct' flag or hidden_facts
        for d in data["diagnosis_options"]:
            assert "correct" not in d
        for t in data["treatment_options"]:
            assert "correct" not in t
        assert "hidden_facts" not in data
        # tests should not leak xray
        for t in data["tests"]:
            assert "xray" not in t

    def test_case_not_found(self, client):
        r = client.get(f"{API}/cases/does-not-exist")
        assert r.status_code == 404


# ---------- Sessions ----------
class TestSessionFlow:
    @pytest.fixture(scope="class")
    def session(self, client):
        r = client.post(f"{API}/sessions", json={"case_id": "acute-pulpitis", "lang": "tr"})
        assert r.status_code == 200
        data = r.json()
        assert "id" in data and data["case_id"] == "acute-pulpitis"
        assert "case" in data
        return data

    def test_session_get(self, client, session):
        r = client.get(f"{API}/sessions/{session['id']}")
        assert r.status_code == 200
        assert r.json()["id"] == session["id"]

    def test_message(self, client, session):
        r = client.post(f"{API}/sessions/{session['id']}/message",
                        json={"text": "Ağrı ne zaman başladı?"})
        assert r.status_code == 200
        data = r.json()
        assert "reply" in data and isinstance(data["reply"], str) and len(data["reply"]) > 0
        # Verify transcript persisted
        s2 = client.get(f"{API}/sessions/{session['id']}").json()
        assert len(s2["transcript"]) >= 2

    def test_exam(self, client, session):
        r = client.post(f"{API}/sessions/{session['id']}/exam",
                        json={"action_id": "cold_test"})
        assert r.status_code == 200
        data = r.json()
        assert data["action_id"] == "cold_test"
        assert "result" in data and "46" in data["result"]
        assert data["tooth"] == 46

    def test_exam_not_found(self, client, session):
        r = client.post(f"{API}/sessions/{session['id']}/exam",
                        json={"action_id": "nope"})
        assert r.status_code == 404

    def test_test_with_xray(self, client, session):
        r = client.post(f"{API}/sessions/{session['id']}/test",
                        json={"action_id": "periapical_xray"})
        assert r.status_code == 200
        data = r.json()
        assert "xray" in data
        xr = data["xray"]
        assert xr["image"].startswith("http")
        assert "question" in xr and len(xr["options"]) == 4
        # No leaking 'correct'
        for o in xr["options"]:
            assert "correct" not in o

    def test_xray_answer_correct(self, client, session):
        r = client.post(f"{API}/sessions/{session['id']}/xray-answer",
                        json={"test_id": "periapical_xray", "option_id": "deep_filling"})
        assert r.status_code == 200
        data = r.json()
        assert data["correct"] is True
        assert data["correct_option_id"] == "deep_filling"
        assert data["explanation"] and len(data["explanation"]) > 10

    def test_xray_answer_wrong(self, client, session):
        r = client.post(f"{API}/sessions/{session['id']}/xray-answer",
                        json={"test_id": "periapical_xray", "option_id": "fracture"})
        assert r.status_code == 200
        data = r.json()
        assert data["correct"] is False
        assert data["correct_option_id"] == "deep_filling"

    def test_commit(self, client, session):
        r = client.post(f"{API}/sessions/{session['id']}/commit",
                        json={"diagnosis_id": "irreversible_pulpitis", "treatment_id": "rct"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        s = client.get(f"{API}/sessions/{session['id']}").json()
        assert s["diagnosis_id"] == "irreversible_pulpitis"
        assert s["treatment_id"] == "rct"

    def test_score(self, client, session):
        r = client.post(f"{API}/sessions/{session['id']}/score")
        assert r.status_code == 200
        data = r.json()
        assert 0 <= data["total"] <= 100
        assert data["grade"] in {"A", "B", "C", "D", "F"}
        assert len(data["dimensions"]) == 5
        assert sum(d["max"] for d in data["dimensions"]) == 100
        assert data["diagnosis"]["is_correct"] is True
        assert data["treatment"]["is_correct"] is True
        assert "history_checklist" in data and "exam_checklist" in data
        assert "red_flags" in data and "test_stewardship" in data
        assert data["narrative"] and len(data["narrative"]) > 10


# ---------- Score on empty session (must not crash) ----------
class TestEmptyScore:
    def test_empty_session_score(self, client):
        r = client.post(f"{API}/sessions", json={"case_id": "pericoronitis", "lang": "en"})
        sid = r.json()["id"]
        r2 = client.post(f"{API}/sessions/{sid}/score")
        assert r2.status_code == 200
        data = r2.json()
        assert data["total"] >= 0
        assert data["diagnosis"]["is_correct"] is False


# ---------- Xray coverage for other radiographic tests ----------
@pytest.mark.parametrize("case_id,test_id,correct_opt", [
    ("apical-abscess", "periapical_xray", "periapical"),
    ("pericoronitis", "opg", "impaction"),
    ("dentin-sensitivity", "bitewing", "normal"),
])
def test_xray_flow_all_cases(client, case_id, test_id, correct_opt):
    r = client.post(f"{API}/sessions", json={"case_id": case_id, "lang": "en"})
    sid = r.json()["id"]
    t = client.post(f"{API}/sessions/{sid}/test", json={"action_id": test_id}).json()
    assert "xray" in t, f"No xray for {case_id}/{test_id}"
    ans = client.post(f"{API}/sessions/{sid}/xray-answer",
                      json={"test_id": test_id, "option_id": correct_opt}).json()
    assert ans["correct"] is True, f"Expected {correct_opt} to be correct for {case_id}"


# ---------- Demo ----------
class TestDemo:
    def test_demo_tr(self, client):
        r = client.get(f"{API}/demo?lang=tr")
        assert r.status_code == 200
        data = r.json()
        assert "case" in data and len(data["script"]) > 0
        assert data["diagnosis"] and data["treatment"]

    def test_demo_en(self, client):
        r = client.get(f"{API}/demo?lang=en")
        assert r.status_code == 200
        assert len(r.json()["script"]) > 0
