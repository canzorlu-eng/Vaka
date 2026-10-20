import pytest
pytestmark = pytest.mark.live

"""Backend tests for Vaka virtual dental patient simulator (iteration 2).
Covers 10-case pack, dual X-rays, X-ray-blended Test Stewardship scoring,
exam severity, /api/cases/generate, /api/tts, and regression on core flow.
"""
import os
import time
import pytest
import requests

def _load_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")) as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    return ln.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_url()
API = f"{BASE_URL}/api"

EXPECTED_CASES = {
    "acute-pulpitis", "apical-abscess", "dentin-sensitivity", "pericoronitis",
    "cracked-tooth", "periodontitis", "early-caries", "failed-rct",
    "retained-root", "bruxism",
}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- Cases list (10 authored) ----------
class TestCasesList:
    def test_list_cases_contains_all_10(self, client):
        r = client.get(f"{API}/cases?lang=tr")
        assert r.status_code == 200
        data = r.json()
        ids = {c["case_id"] for c in data}
        assert EXPECTED_CASES.issubset(ids), f"Missing: {EXPECTED_CASES - ids}"
        for c in data:
            assert "generated" in c

    def test_list_cases_en(self, client):
        r = client.get(f"{API}/cases?lang=en")
        assert r.status_code == 200
        assert len(r.json()) >= 10


# ---------- Dual radiographs ----------
class TestDualXrays:
    @pytest.mark.parametrize("case_id,tests_and_correct", [
        ("cracked-tooth", [("periapical_xray", "fracture"), ("bitewing", "normal")]),
        ("periodontitis", [("periapical_xray", "bone_loss"), ("bitewing", "caries")]),
    ])
    def test_two_xrays_per_case(self, client, case_id, tests_and_correct):
        r = client.post(f"{API}/sessions", json={"case_id": case_id, "lang": "en"})
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        case = r.json()["case"]
        xray_tests = [t for t in case["tests"] if t.get("has_xray")]
        assert len(xray_tests) >= 2, f"{case_id} needs 2 xrays, got {len(xray_tests)}"

        for test_id, correct_opt in tests_and_correct:
            t = client.post(f"{API}/sessions/{sid}/test", json={"action_id": test_id}).json()
            assert "xray" in t, f"{case_id}/{test_id} missing xray"
            assert t["xray"]["image"].startswith("http")
            assert len(t["xray"]["options"]) == 4
            ans = client.post(f"{API}/sessions/{sid}/xray-answer",
                              json={"test_id": test_id, "option_id": correct_opt}).json()
            assert ans["correct"] is True, f"{case_id}/{test_id} expected {correct_opt}"
            assert ans["explanation"] and len(ans["explanation"]) > 5


# ---------- Exam severity ----------
class TestExamSeverity:
    def test_pathology_and_normal_severity(self, client):
        r = client.post(f"{API}/sessions", json={"case_id": "acute-pulpitis", "lang": "en"})
        sid = r.json()["id"]
        # cold_test on acute-pulpitis is a pathological finding
        r1 = client.post(f"{API}/sessions/{sid}/exam", json={"action_id": "cold_test"}).json()
        assert "severity" in r1
        assert r1["severity"] in ("finding", "normal", "neutral")
        # public case exam_actions should also include severity
        case = client.get(f"{API}/cases/acute-pulpitis?lang=en").json()
        assert all("severity" in a for a in case["exam_actions"])


# ---------- Scoring blend (test stewardship + xray reading) ----------
class TestScoringBlend:
    def _run(self, client, xray_answers):
        """Run cracked-tooth flow; xray_answers is list of (test_id, option_id)."""
        r = client.post(f"{API}/sessions", json={"case_id": "cracked-tooth", "lang": "en"})
        sid = r.json()["id"]
        # Order both indicated xrays
        for test_id in ("periapical_xray", "bitewing"):
            client.post(f"{API}/sessions/{sid}/test", json={"action_id": test_id})
        for test_id, opt in xray_answers:
            client.post(f"{API}/sessions/{sid}/xray-answer",
                        json={"test_id": test_id, "option_id": opt})
        client.post(f"{API}/sessions/{sid}/commit",
                    json={"diagnosis_id": "cracked_tooth", "treatment_id": "crown"})
        return client.post(f"{API}/sessions/{sid}/score").json()

    def test_all_correct_high_testing(self, client):
        report = self._run(client, [("periapical_xray", "fracture"), ("bitewing", "normal")])
        ts = report["test_stewardship"]
        assert "xray_findings" in ts and len(ts["xray_findings"]) >= 2
        assert ts["xray_score"] == {"correct": 2, "total": 2}
        testing_dim = next(d for d in report["dimensions"] if d["id"] == "testing")
        # Full: stewardship 1.0 * 0.6 + xray 1.0 * 0.4 = 1.0 -> full weight
        assert testing_dim["score"] == testing_dim["max"], testing_dim

    def test_all_wrong_lowers_testing(self, client):
        report = self._run(client, [("periapical_xray", "normal"), ("bitewing", "caries")])
        ts = report["test_stewardship"]
        assert ts["xray_score"] == {"correct": 0, "total": 2}
        testing_dim = next(d for d in report["dimensions"] if d["id"] == "testing")
        # stewardship 1.0 * 0.6 + 0 * 0.4 = 0.6 -> ~60% of max weight
        assert testing_dim["score"] < testing_dim["max"], testing_dim
        assert testing_dim["pct"] <= 65


# ---------- Case Generation (LLM) ----------
class TestGeneration:
    def test_generate_and_play(self, client):
        r = client.post(f"{API}/cases/generate?lang=en", timeout=60)
        if r.status_code == 502:
            pytest.skip("LLM unavailable for generation")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "case_id" in data and data["case_id"].startswith("gen-")
        assert "title" in data and isinstance(data["title"], str)
        cid = data["case_id"]

        # Detail
        detail = client.get(f"{API}/cases/{cid}?lang=en").json()
        assert len(detail["diagnosis_options"]) == 4
        assert len(detail["treatment_options"]) == 4
        xr_tests = [t for t in detail["tests"] if t.get("has_xray")]
        assert len(xr_tests) >= 1

        # In listing, marked generated=true
        listing = client.get(f"{API}/cases?lang=en").json()
        found = next((c for c in listing if c["case_id"] == cid), None)
        assert found and found.get("generated") is True

        # Play a session on it & score
        sess = client.post(f"{API}/sessions", json={"case_id": cid, "lang": "en"}).json()
        sid = sess["id"]
        # Order xray tests & pick first dx/tx
        for t in xr_tests:
            client.post(f"{API}/sessions/{sid}/test", json={"action_id": t["id"]})
        client.post(f"{API}/sessions/{sid}/commit",
                    json={"diagnosis_id": detail["diagnosis_options"][0]["id"],
                          "treatment_id": detail["treatment_options"][0]["id"]})
        rep = client.post(f"{API}/sessions/{sid}/score").json()
        assert 0 <= rep["total"] <= 100


# ---------- TTS ----------
class TestTTS:
    @pytest.mark.parametrize("text", [
        "Merhaba, dişim çok ağrıyor.",
        "Hello, my tooth is hurting a lot.",
    ])
    def test_tts_returns_audio(self, client, text):
        r = client.post(f"{API}/tts", json={"text": text}, timeout=45)
        assert r.status_code == 200
        data = r.json()
        assert "audio" in data
        if data["audio"] is None:
            pytest.skip("TTS unavailable (LLM key/service)")
        assert isinstance(data["audio"], str)
        assert len(data["audio"]) > 1000  # base64 should be reasonably long


# ---------- Regression: core flow ----------
class TestRegressionCoreFlow:
    def test_full_flow_authored_case(self, client):
        r = client.post(f"{API}/sessions", json={"case_id": "acute-pulpitis", "lang": "tr"})
        assert r.status_code == 200
        sid = r.json()["id"]
        # message
        m = client.post(f"{API}/sessions/{sid}/message",
                        json={"text": "Ağrı ne zaman başladı?"}).json()
        assert m["reply"] and isinstance(m["reply"], str)
        # exam
        e = client.post(f"{API}/sessions/{sid}/exam",
                        json={"action_id": "cold_test"}).json()
        assert e["action_id"] == "cold_test"
        assert "severity" in e
        # test w/ xray
        t = client.post(f"{API}/sessions/{sid}/test",
                        json={"action_id": "periapical_xray"}).json()
        assert "xray" in t
        # commit + score
        client.post(f"{API}/sessions/{sid}/commit",
                    json={"diagnosis_id": "irreversible_pulpitis", "treatment_id": "rct"})
        report = client.post(f"{API}/sessions/{sid}/score").json()
        assert report["total"] > 0
        assert report["diagnosis"]["is_correct"] is True
        assert "xray_findings" in report["test_stewardship"]
