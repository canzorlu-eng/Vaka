"""Case presentation, scoring and examiner feedback (pure domain logic; no HTTP, no database)."""
import json
from typing import Any, Dict, Optional

import llm
from config import settings
from xray_library import XRAY_LIB, xray_public


def public_case(c: Dict[str, Any], lang: str) -> Dict[str, Any]:
    """Return a language-resolved, spoiler-free case for the client."""
    def L(v):
        return v.get(lang, v.get("tr")) if isinstance(v, dict) else v
    return {
        "case_id": c["case_id"],
        "topic": c.get("topic"),
        "difficulty": c["difficulty"],
        "title": L(c["title"]),
        "chief_complaint": L(c["chief_complaint"]),
        "patient": {
            "name": L(c["patient"]["name"]),
            "age": c["patient"]["age"],
            "sex": L(c["patient"]["sex"]),
            "setting": L(c["patient"]["setting"]),
            "avatar_mood": c["patient"]["avatar_mood"],
        },
        "vitals": c["vitals"],
        "exam_actions": [{"id": a["id"], "label": L(a["label"]), "tooth": a.get("tooth"), "severity": infer_severity(a, lang)} for a in c["exam_actions"]],
        "tests": [{"id": t["id"], "label": L(t["label"]), "has_xray": bool(t.get("xray") or t.get("xray_lib"))} for t in c["tests"]],
        "diagnosis_options": [{"id": d["id"], "label": L(d["label"])} for d in c["diagnosis_options"]],
        "treatment_options": [{"id": t["id"], "label": L(t["label"])} for t in c["treatment_options"]],
    }


def infer_severity(action: Dict[str, Any], lang: str) -> str:
    if action.get("severity"):
        return action["severity"]
    txt = norm(action["result"].get(lang, action["result"]["tr"]))
    for w in ["normal", "yok", "negatif", "negative", "no ", "saglam", "intact"]:
        if w in txt:
            return "normal"
    return "finding"


def resolve_xray(test: Dict[str, Any], lang: str):
    """Return spoiler-free xray payload for a test, from library or inline."""
    if test.get("xray_lib"):
        return xray_public(test["xray_lib"], lang)
    if test.get("xray"):
        xr = test["xray"]
        return {"image": xr["image"], "question": xr["question"].get(lang, xr["question"]["tr"]),
                "options": [{"id": o["id"], "label": o["label"].get(lang, o["label"]["tr"])} for o in xr["options"]]}
    return None


def xray_options_full(test: Dict[str, Any]):
    """Return full options (with correct flag) + explanation for a test's xray."""
    if test.get("xray_lib"):
        e = XRAY_LIB.get(test["xray_lib"])
        if e:
            return e["options"], e["explanation"]
    if test.get("xray"):
        return test["xray"]["options"], test["xray"]["explanation"]
    return None, None


def norm(s: str) -> str:
    s = s.lower()
    trmap = str.maketrans("çğıöşü", "cgiosu")
    return s.translate(trmap)


DIMENSIONS = [
    {"id": "anamnesis", "weight": 25, "label": {"tr": "Anamnez", "en": "History Taking"}},
    {"id": "examination", "weight": 20, "label": {"tr": "Klinik Muayene", "en": "Clinical Examination"}},
    {"id": "testing", "weight": 15, "label": {"tr": "Test Yönetimi", "en": "Test Stewardship"}},
    {"id": "diagnosis", "weight": 25, "label": {"tr": "Tanı Doğruluğu", "en": "Diagnostic Accuracy"}},
    {"id": "treatment", "weight": 15, "label": {"tr": "Tedavi Planı", "en": "Treatment Planning"}},
]


def grade_from(pct: float) -> (str, Dict[str, str]):
    if pct >= 90:
        return "A", {"tr": "Usta Klinisyen", "en": "Master Clinician"}
    if pct >= 80:
        return "B", {"tr": "Yetkin Hekim", "en": "Competent Practitioner"}
    if pct >= 70:
        return "C", {"tr": "Gelişen Stajyer", "en": "Developing Trainee"}
    if pct >= 60:
        return "D", {"tr": "Acemi", "en": "Novice"}
    return "F", {"tr": "Tekrar Denemeli", "en": "Needs Retry"}


def deterministic_score(s: Dict[str, Any], c: Dict[str, Any], covered_ids=None) -> Dict[str, Any]:
    lang = s["lang"]
    covered_ids = covered_ids or set()
    student_text = norm(" ".join(m["text"] for m in s["transcript"] if m["role"] == "student"))

    # History checklist (keyword match OR AI-judged semantic coverage)
    hist = []
    for item in c["checklist"]["history"]:
        asked = (item["id"] in covered_ids) or any(norm(k) in student_text for k in item["keywords"])
        hist.append({"id": item["id"], "label": item["label"].get(lang, item["label"]["tr"]),
                     "asked": asked, "red_flag": item["red_flag"]})
    hist_asked = sum(1 for h in hist if h["asked"])
    anamnesis_pct = (hist_asked / len(hist)) if hist else 1.0

    # Exam checklist
    exam = []
    for item in c["checklist"]["exam"]:
        done = item["id"] in s["exams_done"]
        exam.append({"id": item["id"], "label": item["label"].get(lang, item["label"]["tr"]),
                     "done": done, "red_flag": item["red_flag"]})
    exam_done = sum(1 for e in exam if e["done"])
    exam_pct = (exam_done / len(exam)) if exam else 1.0

    # Test stewardship
    indicated = [t["id"] for t in c["tests"] if t["indicated"]]
    ordered = s["tests_ordered"]
    ordered_indicated = [t for t in ordered if t in indicated]
    over_ordered = [t for t in ordered if t not in indicated]
    ind_pct = (len(ordered_indicated) / len(indicated)) if indicated else 1.0
    penalty = min(0.5, 0.25 * len(over_ordered))
    stewardship_pct = max(0.0, ind_pct - penalty)

    # X-ray finding recognition
    xray_tests = [t for t in c["tests"] if (t.get("xray") or t.get("xray_lib"))]
    xray_answers = s.get("xray_answers", {}) or {}
    xray_findings = []
    for t in xray_tests:
        ans = xray_answers.get(t["id"])
        xray_findings.append({
            "label": t["label"].get(lang, t["label"]["tr"]),
            "answered": ans is not None,
            "correct": bool(ans and ans.get("correct")),
        })
    xray_total = len(xray_tests)
    xray_correct = sum(1 for f in xray_findings if f["correct"])
    xray_pct = (xray_correct / xray_total) if xray_total else None

    # Blend: 60% test selection stewardship + 40% x-ray reading (if the case has x-rays)
    if xray_pct is not None:
        testing_pct = 0.6 * stewardship_pct + 0.4 * xray_pct
    else:
        testing_pct = stewardship_pct

    # Diagnosis
    dx = next((d for d in c["diagnosis_options"] if d["id"] == s.get("diagnosis_id")), None)
    dx_correct = bool(dx and dx["correct"])
    diagnosis_pct = 1.0 if dx_correct else (0.0 if dx else 0.0)

    # Treatment
    tx = next((t for t in c["treatment_options"] if t["id"] == s.get("treatment_id")), None)
    tx_correct = bool(tx and tx["correct"])
    treatment_pct = 1.0 if tx_correct else 0.0

    pcts = {"anamnesis": anamnesis_pct, "examination": exam_pct, "testing": testing_pct,
            "diagnosis": diagnosis_pct, "treatment": treatment_pct}

    total = 0.0
    dims = []
    for d in DIMENSIONS:
        p = pcts[d["id"]]
        score = round(p * d["weight"])
        total += score
        dims.append({"id": d["id"], "label": d["label"].get(lang, d["label"]["tr"]),
                     "score": score, "max": d["weight"], "pct": round(p * 100)})

    total = round(total)
    grade, rank = grade_from(total)

    red_flags = []
    for h in hist:
        if h["red_flag"]:
            red_flags.append({"label": h["label"], "caught": h["asked"]})
    for e in exam:
        if e["red_flag"]:
            red_flags.append({"label": e["label"], "caught": e["done"]})

    correct_dx = next((d for d in c["diagnosis_options"] if d["correct"]), None)
    correct_tx = next((t for t in c["treatment_options"] if t["correct"]), None)

    return {
        "total": total, "grade": grade, "rank": rank.get(lang, rank["tr"]),
        "dimensions": dims,
        "history_checklist": hist,
        "exam_checklist": exam,
        "red_flags": red_flags,
        "test_stewardship": {
            "ordered_indicated": [next(t["label"].get(lang, t["label"]["tr"]) for t in c["tests"] if t["id"] == x) for x in ordered_indicated],
            "missed_indicated": [next(t["label"].get(lang, t["label"]["tr"]) for t in c["tests"] if t["id"] == x) for x in indicated if x not in ordered],
            "over_ordered": [next(t["label"].get(lang, t["label"]["tr"]) for t in c["tests"] if t["id"] == x) for x in over_ordered],
            "xray_findings": xray_findings,
            "xray_score": {"correct": xray_correct, "total": xray_total},
        },
        "diagnosis": {"chosen": (dx["label"].get(lang, dx["label"]["tr"]) if dx else None),
                      "correct": correct_dx["label"].get(lang, correct_dx["label"]["tr"]) if correct_dx else None,
                      "is_correct": dx_correct},
        "treatment": {"chosen": (tx["label"].get(lang, tx["label"]["tr"]) if tx else None),
                      "correct": correct_tx["label"].get(lang, correct_tx["label"]["tr"]) if correct_tx else None,
                      "is_correct": tx_correct},
    }


async def examiner_narrative(report: Dict[str, Any], c: Dict[str, Any], lang: str,
                             user: Optional[Dict[str, Any]] = None, ref: Optional[str] = None) -> str:
    langname = "Turkish" if lang == "tr" else "English"
    missed_hist = [h["label"] for h in report["history_checklist"] if not h["asked"]]
    missed_flags = [r["label"] for r in report["red_flags"] if not r["caught"]]
    system = (f"You are a strict but fair dental examiner. Write a 3-4 sentence debrief in {langname}, "
              f"second person ('you'), constructive and specific. Do not use markdown.")
    prompt = (f"Total score: {report['total']}/100 (grade {report['grade']}). "
              f"Diagnosis correct: {report['diagnosis']['is_correct']}. "
              f"Treatment correct: {report['treatment']['is_correct']}. "
              f"Missed history questions: {missed_hist}. Missed red flags: {missed_flags}. "
              f"Over-ordered tests: {report['test_stewardship']['over_ordered']}. "
              f"Write the examiner's narrative feedback.")
    text = await llm.llm_call(system, prompt, temperature=0.4, user=user, kind="narrative", ref=ref,
                              model=settings.gemini_model_scoring or None)
    if text:
        return text.strip().strip('"')
    # deterministic fallback
    if lang == "tr":
        parts = [f"Toplam {report['total']}/100 puan aldınız."]
        parts.append("Tanınız doğru." if report["diagnosis"]["is_correct"] else "Tanı seçiminiz hatalıydı.")
        if missed_flags:
            parts.append("Atlanan kırmızı bayraklar: " + ", ".join(missed_flags) + ".")
        parts.append("Sistematik anamnez ve hedefe yönelik testlerle daha da gelişebilirsiniz.")
        return " ".join(parts)
    parts = [f"You scored {report['total']}/100."]
    parts.append("Your diagnosis was correct." if report["diagnosis"]["is_correct"] else "Your diagnosis was incorrect.")
    if missed_flags:
        parts.append("Missed red flags: " + ", ".join(missed_flags) + ".")
    parts.append("Focus on a systematic history and targeted testing to improve further.")
    return " ".join(parts)


async def history_llm_coverage(s: Dict[str, Any], c: Dict[str, Any],
                               user: Optional[Dict[str, Any]] = None, ref: Optional[str] = None) -> set:
    """Ask the LLM which history topics the student's free-text questions actually covered.
    Compact single call; returns a set of topic ids (empty on failure -> keyword fallback)."""
    questions = [m["text"] for m in s["transcript"] if m["role"] == "student"]
    if not questions:
        return set()
    lang = s["lang"]
    topics = "; ".join(f'{i["id"]}={i["label"].get(lang, i["label"]["tr"])}' for i in c["checklist"]["history"])
    system = "You grade a dental student's history-taking. Output ONLY a JSON array of covered topic ids, nothing else."
    prompt = (f"Topics: {topics}\nStudent questions: {questions}\n"
              f"Return the ids of topics the student meaningfully asked about, as a JSON array e.g. [\"onset\",\"night\"].")
    raw = await llm.llm_call(system, prompt, temperature=0.0, user=user, kind="coverage", ref=ref,
                            model=settings.gemini_model_scoring or None)
    if not raw:
        return set()
    try:
        start, end = raw.find("["), raw.rfind("]")
        ids = json.loads(raw[start:end + 1]) if start != -1 and end != -1 else []
        valid = {i["id"] for i in c["checklist"]["history"]}
        return {str(x) for x in ids if str(x) in valid}
    except Exception:
        return set()
