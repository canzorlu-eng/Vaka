"""Offline checks on the case catalogue (no network, no database)."""
import re

import pytest

from case_store import CASES, TOPICS, CaseError, expand, validate

TOPIC_IDS = {t["id"] for t in TOPICS}
LANGS = ("tr", "en")


def test_catalogue_is_nonempty_and_ids_unique():
    ids = [c["case_id"] for c in CASES]
    assert len(ids) == len(set(ids)) > 0


def test_every_topic_has_cases_at_each_level():
    for t in TOPICS:
        levels = {c["difficulty"] for c in CASES if c["topic"] == t["id"]}
        assert levels == {"easy", "moderate", "hard"}, f"{t['id']} covers {levels}"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["case_id"])
def test_case_is_valid_and_bilingual(case):
    validate(case, TOPIC_IDS)
    for lang in LANGS:
        assert case["title"][lang].strip() and case["chief_complaint"][lang].strip()
        for opt in case["diagnosis_options"] + case["treatment_options"]:
            assert opt["label"][lang].strip()
        for t in case["tests"]:
            assert t["label"][lang].strip() and t["result"][lang].strip()


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["case_id"])
def test_no_placeholder_text(case):
    blob = str(case)
    assert not re.search(r"\b(TODO|FIXME|XXX)\b|lorem ipsum", blob)


def test_validator_rejects_two_correct_answers():
    case = next(c for c in CASES)
    bad = {**case, "diagnosis_options": [{**o, "correct": True} for o in case["diagnosis_options"]]}
    with pytest.raises(CaseError):
        validate(bad, TOPIC_IDS)


def test_compact_expansion_shuffles_but_keeps_one_correct():
    doc = {
        "id": "t-1", "topic": "endodontics", "d": "easy", "title": ["Başlık", "Title"], "cc": ["Ağrı", "Pain"],
        "pt": ["A. B.", 30, "f", ["Klinik", "Clinic"], "pain"],
        "hx": [["a", ["Konu", "Topic"], "ağrı|pain", ["Evet", "Yes"], 1]] * 1,
        "ex": [["v", ["Görsel", "Visual"], ["N", "N"], None, 1, 1]],
        "ts": [["x", ["Film", "Film"], ["R", "R"], 1, None]],
        "dx": [["Doğru", "Right"], ["Y1", "W1"], ["Y2", "W2"], ["Y3", "W3"]],
        "tx": [["Doğru", "Right"], ["Y1", "W1"], ["Y2", "W2"], ["Y3", "W3"]],
    }
    out = expand(doc)
    assert sum(o["correct"] for o in out["diagnosis_options"]) == 1
    assert out == expand(doc)  # deterministic
