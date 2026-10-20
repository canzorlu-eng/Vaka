"""Case catalogue: loads topic-organised JSON cases from backend/cases/ and validates them.

Two on-disk formats are accepted:
  * expanded  - the internal schema (has "hidden_facts"); used as-is.
  * compact   - a terse authoring format that is expanded here (see `expand`).
Bilingual strings are written as [tr, en] in compact files.
"""
import json
import random
from pathlib import Path
from typing import Any, Dict, List

from xray_library import XRAY_LIB

CASES_DIR = Path(__file__).parent / "cases"
DIFFICULTIES = ("easy", "moderate", "hard")
MOODS = ("neutral", "pain", "anxious")
SEX = {"f": ("Kadın", "Female"), "m": ("Erkek", "Male")}
DEFAULT_VITALS = ("120/78", 74, "36.6°C", "99%")


class CaseError(ValueError):
    pass


def bi(v: Any) -> Dict[str, str]:
    """[tr, en] / {tr, en} / str -> {"tr": .., "en": ..}"""
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return {"tr": str(v[0]), "en": str(v[1])}
    if isinstance(v, dict) and "tr" in v and "en" in v:
        return {"tr": str(v["tr"]), "en": str(v["en"])}
    if isinstance(v, str):
        return {"tr": v, "en": v}
    raise CaseError(f"bad bilingual value: {v!r}")


def _options(rows: List[Any], seed: str) -> List[Dict[str, Any]]:
    """First row is the correct answer; order is shuffled deterministically per case."""
    opts = [{"id": f"o{i}", "label": bi(r), "correct": i == 0} for i, r in enumerate(rows)]
    random.Random(seed).shuffle(opts)
    return opts


def expand(c: Dict[str, Any]) -> Dict[str, Any]:
    """compact -> internal schema"""
    pname, age, sex, setting, mood = c["pt"]
    vit = c.get("vit") or DEFAULT_VITALS
    hidden, hist_check = [], []
    for hid, topic, kws, text, *rest in c["hx"]:
        kw = [k.strip() for k in kws.split("|") if k.strip()]
        hidden.append({"id": hid, "keywords": kw, "text": bi(text), "topic": bi(topic)})
        hist_check.append({"id": hid, "keywords": kw, "red_flag": bool(rest and rest[0]), "label": bi(topic)})
    exams, exam_check = [], []
    for eid, label, result, tooth, req, *rest in c["ex"]:
        exams.append({"id": eid, "label": bi(label), "result": bi(result), "tooth": tooth,
                      "required": bool(req), **({"severity": rest[1]} if len(rest) > 1 and rest[1] else {})})
        if req:
            exam_check.append({"id": eid, "red_flag": bool(rest and rest[0]), "label": bi(label)})
    tests = []
    for tid, label, result, indicated, *rest in c["ts"]:
        t = {"id": tid, "indicated": bool(indicated), "label": bi(label), "result": bi(result)}
        if rest and rest[0]:
            t["xray_lib"] = rest[0]
        tests.append(t)
    have = {t["id"] for t in tests}
    if "cbct" not in have:
        tests.append({"id": "cbct", "indicated": False, "label": {"tr": "CBCT (3B tomografi)", "en": "CBCT (3D scan)"},
                      "result": {"tr": "Bu tabloda rutin endike değil — gereksiz radyasyon.", "en": "Not routinely indicated here — unnecessary radiation."}})
    if "cbc" not in have:
        tests.append({"id": "cbc", "indicated": False, "label": {"tr": "Tam kan sayımı", "en": "Complete blood count"},
                      "result": {"tr": "Bu tabloda endike değil.", "en": "Not indicated in this presentation."}})
    return {
        "case_id": c["id"], "topic": c["topic"], "difficulty": c["d"],
        "title": bi(c["title"]), "chief_complaint": bi(c["cc"]),
        "patient": {"name": bi(pname), "age": age, "sex": {"tr": SEX[sex][0], "en": SEX[sex][1]},
                    "setting": bi(setting), "avatar_mood": mood},
        "vitals": {"bp": vit[0], "hr": vit[1], "temp": vit[2], "spo2": vit[3]},
        "hidden_facts": hidden, "exam_actions": exams, "tests": tests,
        "diagnosis_options": _options(c["dx"], c["id"] + "dx"),
        "treatment_options": _options(c["tx"], c["id"] + "tx"),
        "checklist": {"history": hist_check, "exam": exam_check},
    }


def validate(c: Dict[str, Any], topic_ids: set) -> None:
    cid = c.get("case_id", "?")
    def need(cond: bool, msg: str):
        if not cond:
            raise CaseError(f"{cid}: {msg}")
    need(c.get("topic") in topic_ids, f"unknown topic {c.get('topic')!r}")
    need(c["difficulty"] in DIFFICULTIES, "bad difficulty")
    need(c["patient"]["avatar_mood"] in MOODS, "bad mood")
    for k in ("title", "chief_complaint"):
        need(all(c[k].get(l) for l in ("tr", "en")), f"empty {k}")
    need(len(c["hidden_facts"]) >= 4, "needs >= 4 history facts")
    need(any(h["red_flag"] for h in c["checklist"]["history"]) or any(e["red_flag"] for e in c["checklist"]["exam"]),
         "needs at least one red flag")
    need(len(c["exam_actions"]) >= 3, "needs >= 3 exam actions")
    need(any(t["indicated"] for t in c["tests"]), "needs an indicated test")
    for group in ("hidden_facts", "exam_actions", "tests", "diagnosis_options", "treatment_options"):
        ids = [x["id"] for x in c[group]]
        need(len(ids) == len(set(ids)), f"duplicate ids in {group}")
    for group in ("diagnosis_options", "treatment_options"):
        need(len(c[group]) == 4, f"{group} must have 4 options")
        need(sum(o["correct"] for o in c[group]) == 1, f"{group} needs exactly one correct")
    for t in c["tests"]:
        if t.get("xray_lib"):
            need(t["xray_lib"] in XRAY_LIB, f"unknown xray_lib {t['xray_lib']}")
    for h in c["hidden_facts"]:
        need(h["keywords"], f"fact {h['id']} has no keywords")
        need(h["text"]["tr"] and h["text"]["en"], f"fact {h['id']} missing language")
    for e in c["exam_actions"]:
        need(e["result"]["tr"] and e["result"]["en"], f"exam {e['id']} missing language")


def load_topics() -> List[Dict[str, Any]]:
    return json.loads((CASES_DIR / "topics.json").read_text(encoding="utf-8"))


def load_cases() -> List[Dict[str, Any]]:
    topics = load_topics()
    topic_ids = {t["id"] for t in topics}
    cases, seen = [], set()
    for path in sorted(CASES_DIR.glob("*/*.json")):
        docs = json.loads(path.read_text(encoding="utf-8"))
        for doc in (docs if isinstance(docs, list) else [docs]):
            try:
                c = doc if "hidden_facts" in doc else expand(doc)
                c.setdefault("topic", path.parent.name)
                validate(c, topic_ids)
            except (CaseError, KeyError, ValueError, TypeError) as e:
                raise CaseError(f"{path.relative_to(CASES_DIR)}: {e!r}") from e
            if c["case_id"] in seen:
                raise CaseError(f"duplicate case id {c['case_id']} ({path.name})")
            seen.add(c["case_id"])
            cases.append(c)
    return cases


_cache: Dict[str, Any] = {}


def __getattr__(name: str):
    """Lazy catalogue: `from case_store import CASES, TOPICS` loads (and validates) on first access, so
    tooling such as scripts/check_cases.py can import this module even if some case file is mid-edit."""
    if name in ("CASES", "TOPICS"):
        if "topics" not in _cache:
            _cache["topics"] = load_topics()
            _cache["cases"] = load_cases()
        return _cache["cases" if name == "CASES" else "topics"]
    raise AttributeError(name)
