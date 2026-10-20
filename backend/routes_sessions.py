"""Practice sessions. Every route requires a signed-in user and every query is scoped to that user (404 otherwise)."""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import cache
import catalogue
import llm
import repo
from auth import current_user
from casetools import (deterministic_score, examiner_narrative, history_llm_coverage, infer_severity,
                       public_case, resolve_xray, xray_options_full)
from config import settings
from plans import plan_for
from ratelimit import limit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["sessions"])


class SessionCreate(BaseModel):
    case_id: str = Field(max_length=80)
    lang: str = Field("tr", pattern="^(tr|en)$")


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=settings.max_chat_chars)


class ActionIn(BaseModel):
    action_id: str = Field(max_length=80)


class CommitIn(BaseModel):
    diagnosis_id: Optional[str] = Field(None, max_length=80)
    treatment_id: Optional[str] = Field(None, max_length=80)


class XrayAnswerIn(BaseModel):
    test_id: str = Field(max_length=80)
    option_id: str = Field(max_length=80)


class TTSIn(BaseModel):
    text: str = Field(min_length=1, max_length=llm.TTS_MAX_CHARS)


async def _own_session(sid: str, user: Dict[str, Any]) -> Dict[str, Any]:
    s = await repo.get_session(sid, user["id"])
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s


@router.post("/sessions", dependencies=[Depends(limit("sessions", 30, 600))])
async def create_session(body: SessionCreate, user: Dict[str, Any] = Depends(current_user)):
    case = await catalogue.get_case(body.case_id, user)
    plan = await plan_for(user)
    used = await repo.count_sessions_this_month(user["id"])
    if used >= plan.sessions_per_month:
        raise HTTPException(status_code=402, detail={"code": "quota_exceeded", "plan": plan.name,
                                                      "limit": plan.sessions_per_month, "used": used})
    sid = str(uuid.uuid4())
    doc = {"id": sid, "case_id": body.case_id, "lang": body.lang, "phase": "anamnez", "transcript": [],
           "exams_done": [], "tests_ordered": [], "diagnosis_id": None, "treatment_id": None,
           "started_at": datetime.now(timezone.utc).isoformat(), "ended": False}
    await repo.insert_session(user["id"], doc)
    return {**doc, "case": public_case(case, body.lang)}


@router.get("/sessions")
async def my_sessions(limit_: int = Query(20, ge=1, le=50, alias="limit"), before: Optional[datetime] = None,
                      user: Dict[str, Any] = Depends(current_user)):
    rows = await repo.list_sessions(user["id"], limit_, before)
    return {"items": [{**r, "id": str(r["id"])} for r in rows],
            "next_before": rows[-1]["created_at"].isoformat() if len(rows) == limit_ else None}


@router.get("/sessions/{sid}")
async def get_session(sid: str, user: Dict[str, Any] = Depends(current_user)):
    s = await _own_session(sid, user)
    return {**s, "case": public_case(await catalogue.get_case(s["case_id"], user), s["lang"])}


@router.post("/sessions/{sid}/message", dependencies=[Depends(limit("chat", 40, 60)), Depends(limit("chat-hour", 400, 3600))])
async def patient_message(sid: str, body: ChatIn, user: Dict[str, Any] = Depends(current_user)):
    s = await _own_session(sid, user)
    if s.get("ended"):
        raise HTTPException(status_code=409, detail="Session already ended")
    if len(s["transcript"]) >= 2 * settings.max_messages_per_session:
        raise HTTPException(status_code=409, detail={"code": "session_message_limit", "limit": settings.max_messages_per_session})
    c = await catalogue.get_case(s["case_id"], user)
    lang = s["lang"]
    facts = "\n".join(f"- ({f['id']}) {f['text'].get(lang, f['text']['tr'])}" for f in c["hidden_facts"])
    langname = "Turkish" if lang == "tr" else "English"
    name = c["patient"]["name"].get(lang, c["patient"]["name"]["tr"])
    cc = c["chief_complaint"].get(lang, c["chief_complaint"]["tr"])
    system = (
        f"You are a virtual PATIENT named {name}, age {c['patient']['age']}, in a dental clinic. "
        f"You are a layperson, NOT a medical professional. Speak ONLY in {langname}, in first person, "
        f"warm and natural, 1-3 short sentences. Your chief complaint: \"{cc}\".\n\n"
        f"You know these facts about yourself, but you ONLY reveal a fact when the student specifically asks "
        f"about that topic. NEVER volunteer facts that weren't asked. NEVER use clinical/technical terms. "
        f"NEVER give a diagnosis or suggest treatment. If asked something not covered, answer plausibly and "
        f"conservatively in character (e.g. 'no', 'I'm not sure').\n\nFACTS:\n{facts}\n\n"
        f"Respond with ONLY the patient's spoken reply, no narration."
    )
    history = "\n".join(f"{'Student' if m['role'] == 'student' else 'Patient'}: {m['text']}" for m in s["transcript"][-8:])
    prompt = f"Conversation so far:\n{history}\n\nStudent asks: {body.text}\n\nPatient replies:"
    reply = await llm.llm_call(system, prompt, temperature=0.85, user=user, kind="chat", ref=f"session:{sid}")
    if not reply:
        reply = "Üzgünüm, şu an cevap veremiyorum." if lang == "tr" else "Sorry, I can't answer right now."
    reply = reply.strip().strip('"')
    now = datetime.now(timezone.utc).isoformat()
    msgs = [{"role": "student", "text": body.text, "ts": now}, {"role": "patient", "text": reply, "ts": now}]
    await repo.update_session(sid, user["id"], lambda cur: {**cur, "transcript": [*cur["transcript"], *msgs]})
    return {"reply": reply, "mood": c["patient"]["avatar_mood"]}


@router.post("/sessions/{sid}/exam", dependencies=[Depends(limit("actions", 120, 60))])
async def run_exam(sid: str, body: ActionIn, user: Dict[str, Any] = Depends(current_user)):
    s = await _own_session(sid, user)
    c = await catalogue.get_case(s["case_id"], user)
    lang = s["lang"]
    action = next((a for a in c["exam_actions"] if a["id"] == body.action_id), None)
    if not action:
        raise HTTPException(status_code=404, detail="Exam action not found")
    if body.action_id not in s["exams_done"]:
        await repo.update_session(sid, user["id"], lambda cur: {
            **cur, "exams_done": list(dict.fromkeys([*cur["exams_done"], body.action_id]))})
    return {"action_id": body.action_id, "label": action["label"].get(lang, action["label"]["tr"]),
            "result": action["result"].get(lang, action["result"]["tr"]), "tooth": action.get("tooth"),
            "severity": infer_severity(action, lang)}


@router.post("/sessions/{sid}/test", dependencies=[Depends(limit("actions", 120, 60))])
async def order_test(sid: str, body: ActionIn, user: Dict[str, Any] = Depends(current_user)):
    s = await _own_session(sid, user)
    c = await catalogue.get_case(s["case_id"], user)
    lang = s["lang"]
    test = next((t for t in c["tests"] if t["id"] == body.action_id), None)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    if body.action_id not in s["tests_ordered"]:
        await repo.update_session(sid, user["id"], lambda cur: {
            **cur, "tests_ordered": list(dict.fromkeys([*cur["tests_ordered"], body.action_id]))})
    resp = {"test_id": body.action_id, "label": test["label"].get(lang, test["label"]["tr"]),
            "result": test["result"].get(lang, test["result"]["tr"]), "indicated": test["indicated"]}
    xr = resolve_xray(test, lang)
    if xr:
        resp["xray"] = xr
    return resp


@router.post("/sessions/{sid}/xray-answer", dependencies=[Depends(limit("actions", 120, 60))])
async def xray_answer(sid: str, body: XrayAnswerIn, user: Dict[str, Any] = Depends(current_user)):
    s = await _own_session(sid, user)
    c = await catalogue.get_case(s["case_id"], user)
    lang = s["lang"]
    test = next((t for t in c["tests"] if t["id"] == body.test_id), None)
    if not test:
        raise HTTPException(status_code=404, detail="X-ray not found")
    options, explanation = xray_options_full(test)
    if not options:
        raise HTTPException(status_code=404, detail="X-ray not found")
    correct_opt = next((o for o in options if o["correct"]), None)
    chosen = next((o for o in options if o["id"] == body.option_id), None)
    is_correct = bool(chosen and chosen["correct"])
    answer = {"option_id": body.option_id, "correct": is_correct}
    await repo.update_session(sid, user["id"], lambda cur: {
        **cur, "xray_answers": {**(cur.get("xray_answers") or {}), body.test_id: answer}})
    return {"correct": is_correct, "correct_option_id": correct_opt["id"] if correct_opt else None,
            "correct_label": correct_opt["label"].get(lang, correct_opt["label"]["tr"]) if correct_opt else None,
            "explanation": explanation.get(lang, explanation["tr"]) if explanation else ""}


@router.post("/sessions/{sid}/commit", dependencies=[Depends(limit("actions", 120, 60))])
async def commit(sid: str, body: CommitIn, user: Dict[str, Any] = Depends(current_user)):
    s = await _own_session(sid, user)
    if s.get("ended"):
        raise HTTPException(status_code=409, detail="Session already ended")
    update = {k: v for k, v in (("diagnosis_id", body.diagnosis_id), ("treatment_id", body.treatment_id)) if v is not None}
    if update:
        await repo.update_session(sid, user["id"], lambda cur: {**cur, **update})
    return {"ok": True, **update}


@router.post("/sessions/{sid}/score", dependencies=[Depends(limit("score", 10, 600))])
async def score_session(sid: str, user: Dict[str, Any] = Depends(current_user)):
    """Idempotent: repeat/parallel calls return the stored report and never pay for the LLM twice."""
    s = await _own_session(sid, user)
    existing = await repo.get_report(sid, user["id"])
    if existing:
        return existing
    lock_key = f"score-lock:{sid}"
    holders, _ = await cache.incr(lock_key, 90)
    if holders > 1:  # another request is already scoring this session: wait for its result
        for _ in range(40):
            await asyncio.sleep(1.5)
            existing = await repo.get_report(sid, user["id"])
            if existing:
                return existing
        raise HTTPException(status_code=409, detail="Scoring is already in progress")
    try:
        existing = await repo.get_report(sid, user["id"])  # a concurrent scorer may have just finished
        if existing:
            return existing
        c = await catalogue.get_case(s["case_id"], user)
        covered = await history_llm_coverage(s, c, user=user, ref=f"session:{sid}")
        report = deterministic_score(s, c, covered_ids=covered)
        report["narrative"] = await examiner_narrative(report, c, s["lang"], user=user, ref=f"session:{sid}")
        report["case_title"] = c["title"].get(s["lang"], c["title"]["tr"])
        report["generated_at"] = datetime.now(timezone.utc).isoformat()
        return await repo.save_report(sid, user["id"], c["case_id"], report)
    finally:
        await cache.delete(lock_key)


@router.post("/tts", dependencies=[Depends(limit("tts", 40, 60)), Depends(limit("tts-hour", 400, 3600))])
async def tts(body: TTSIn, user: Dict[str, Any] = Depends(current_user)):
    """Natural patient voice. Pro plan only; others (and any failure) get audio=None and use the browser voice."""
    plan = await plan_for(user)
    if not plan.voice:
        return {"audio": None, "reason": "plan"}
    return {"audio": await llm.synthesize(body.text, user)}
