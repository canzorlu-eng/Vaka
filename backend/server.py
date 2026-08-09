from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import re
import json
import logging
import uuid
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from cases_seed import CASES

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')
LLM_MODEL = ("gemini", "gemini-3-flash-preview")

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ----------------------------- Models -----------------------------
class SessionCreate(BaseModel):
    case_id: str
    lang: str = "tr"


class Message(BaseModel):
    role: str
    text: str
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ChatIn(BaseModel):
    text: str


class ActionIn(BaseModel):
    action_id: str


class CommitIn(BaseModel):
    diagnosis_id: Optional[str] = None
    treatment_id: Optional[str] = None


# ----------------------------- Helpers -----------------------------
def public_case(c: Dict[str, Any], lang: str) -> Dict[str, Any]:
    """Return a language-resolved, spoiler-free case for the client."""
    def L(v):
        return v.get(lang, v.get("tr")) if isinstance(v, dict) else v
    return {
        "case_id": c["case_id"],
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
        "exam_actions": [{"id": a["id"], "label": L(a["label"]), "tooth": a.get("tooth")} for a in c["exam_actions"]],
        "tests": [{"id": t["id"], "label": L(t["label"])} for t in c["tests"]],
        "diagnosis_options": [{"id": d["id"], "label": L(d["label"])} for d in c["diagnosis_options"]],
        "treatment_options": [{"id": t["id"], "label": L(t["label"])} for t in c["treatment_options"]],
    }


def get_case(case_id: str) -> Dict[str, Any]:
    for c in CASES:
        if c["case_id"] == case_id:
            return c
    raise HTTPException(status_code=404, detail="Case not found")


def norm(s: str) -> str:
    s = s.lower()
    trmap = str.maketrans("çğıöşü", "cgiosu")
    return s.translate(trmap)


async def llm_call(system: str, prompt: str, temperature: float = 0.7) -> Optional[str]:
    if not EMERGENT_LLM_KEY:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=str(uuid.uuid4()),
                       system_message=system).with_model(*LLM_MODEL)
        resp = await chat.send_message(UserMessage(text=prompt))
        return resp if isinstance(resp, str) else str(resp)
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return None


# ----------------------------- Routes -----------------------------
@api_router.get("/")
async def root():
    return {"message": "Vaka API"}


@api_router.get("/cases")
async def list_cases(lang: str = "tr"):
    return [
        {
            "case_id": c["case_id"],
            "difficulty": c["difficulty"],
            "title": c["title"].get(lang, c["title"]["tr"]),
            "chief_complaint": c["chief_complaint"].get(lang, c["chief_complaint"]["tr"]),
            "patient_name": c["patient"]["name"].get(lang, c["patient"]["name"]["tr"]),
            "age": c["patient"]["age"],
            "mood": c["patient"]["avatar_mood"],
        }
        for c in CASES
    ]


@api_router.get("/cases/{case_id}")
async def case_detail(case_id: str, lang: str = "tr"):
    return public_case(get_case(case_id), lang)


@api_router.post("/sessions")
async def create_session(body: SessionCreate):
    get_case(body.case_id)
    sid = str(uuid.uuid4())
    doc = {
        "id": sid, "case_id": body.case_id, "lang": body.lang,
        "phase": "anamnez", "transcript": [], "exams_done": [], "tests_ordered": [],
        "diagnosis_id": None, "treatment_id": None, "started_at": datetime.now(timezone.utc).isoformat(),
        "ended": False,
    }
    await db.sessions.insert_one(dict(doc))
    doc.pop("_id", None)
    return {**doc, "case": public_case(get_case(body.case_id), body.lang)}


@api_router.get("/sessions/{sid}")
async def get_session(sid: str):
    s = await db.sessions.find_one({"id": sid}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return {**s, "case": public_case(get_case(s["case_id"]), s["lang"])}


@api_router.post("/sessions/{sid}/message")
async def patient_message(sid: str, body: ChatIn):
    s = await db.sessions.find_one({"id": sid})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    c = get_case(s["case_id"])
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
    history = "\n".join(f"{'Student' if m['role']=='student' else 'Patient'}: {m['text']}" for m in s["transcript"][-8:])
    prompt = f"Conversation so far:\n{history}\n\nStudent asks: {body.text}\n\nPatient replies:"

    reply = await llm_call(system, prompt, temperature=0.85)
    if not reply:
        reply = ("Üzgünüm, şu an cevap veremiyorum." if lang == "tr"
                 else "Sorry, I can't answer right now.")
    reply = reply.strip().strip('"')

    student_msg = {"role": "student", "text": body.text, "ts": datetime.now(timezone.utc).isoformat()}
    patient_msg = {"role": "patient", "text": reply, "ts": datetime.now(timezone.utc).isoformat()}
    await db.sessions.update_one({"id": sid}, {"$push": {"transcript": {"$each": [student_msg, patient_msg]}}})
    return {"reply": reply, "mood": c["patient"]["avatar_mood"]}


@api_router.post("/sessions/{sid}/exam")
async def run_exam(sid: str, body: ActionIn):
    s = await db.sessions.find_one({"id": sid})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    c = get_case(s["case_id"])
    lang = s["lang"]
    action = next((a for a in c["exam_actions"] if a["id"] == body.action_id), None)
    if not action:
        raise HTTPException(status_code=404, detail="Exam action not found")
    result = action["result"].get(lang, action["result"]["tr"])
    if body.action_id not in s["exams_done"]:
        await db.sessions.update_one({"id": sid}, {"$push": {"exams_done": body.action_id}})
    return {"action_id": body.action_id, "label": action["label"].get(lang, action["label"]["tr"]),
            "result": result, "tooth": action.get("tooth")}


@api_router.post("/sessions/{sid}/test")
async def order_test(sid: str, body: ActionIn):
    s = await db.sessions.find_one({"id": sid})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    c = get_case(s["case_id"])
    lang = s["lang"]
    test = next((t for t in c["tests"] if t["id"] == body.action_id), None)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    if body.action_id not in s["tests_ordered"]:
        await db.sessions.update_one({"id": sid}, {"$push": {"tests_ordered": body.action_id}})
    resp = {"test_id": body.action_id, "label": test["label"].get(lang, test["label"]["tr"]),
            "result": test["result"].get(lang, test["result"]["tr"]), "indicated": test["indicated"]}
    if test.get("xray"):
        xr = test["xray"]
        resp["xray"] = {
            "image": xr["image"],
            "question": xr["question"].get(lang, xr["question"]["tr"]),
            "options": [{"id": o["id"], "label": o["label"].get(lang, o["label"]["tr"])} for o in xr["options"]],
        }
    return resp


class XrayAnswerIn(BaseModel):
    test_id: str
    option_id: str


@api_router.post("/sessions/{sid}/xray-answer")
async def xray_answer(sid: str, body: XrayAnswerIn):
    s = await db.sessions.find_one({"id": sid})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    c = get_case(s["case_id"])
    lang = s["lang"]
    test = next((t for t in c["tests"] if t["id"] == body.test_id), None)
    if not test or not test.get("xray"):
        raise HTTPException(status_code=404, detail="X-ray not found")
    xr = test["xray"]
    correct_opt = next((o for o in xr["options"] if o["correct"]), None)
    chosen = next((o for o in xr["options"] if o["id"] == body.option_id), None)
    is_correct = bool(chosen and chosen["correct"])
    await db.sessions.update_one(
        {"id": sid},
        {"$set": {f"xray_answers.{body.test_id}": {"option_id": body.option_id, "correct": is_correct}}},
    )
    return {
        "correct": is_correct,
        "correct_option_id": correct_opt["id"] if correct_opt else None,
        "correct_label": correct_opt["label"].get(lang, correct_opt["label"]["tr"]) if correct_opt else None,
        "explanation": xr["explanation"].get(lang, xr["explanation"]["tr"]),
    }


@api_router.post("/sessions/{sid}/commit")
async def commit(sid: str, body: CommitIn):
    s = await db.sessions.find_one({"id": sid})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    update = {}
    if body.diagnosis_id is not None:
        update["diagnosis_id"] = body.diagnosis_id
    if body.treatment_id is not None:
        update["treatment_id"] = body.treatment_id
    if update:
        await db.sessions.update_one({"id": sid}, {"$set": update})
    return {"ok": True, **update}


# ----------------------------- Scoring -----------------------------
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


def deterministic_score(s: Dict[str, Any], c: Dict[str, Any]) -> Dict[str, Any]:
    lang = s["lang"]
    student_text = norm(" ".join(m["text"] for m in s["transcript"] if m["role"] == "student"))

    # History checklist
    hist = []
    for item in c["checklist"]["history"]:
        asked = any(norm(k) in student_text for k in item["keywords"])
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
    testing_pct = max(0.0, ind_pct - penalty)

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
        },
        "diagnosis": {"chosen": (dx["label"].get(lang, dx["label"]["tr"]) if dx else None),
                      "correct": correct_dx["label"].get(lang, correct_dx["label"]["tr"]) if correct_dx else None,
                      "is_correct": dx_correct},
        "treatment": {"chosen": (tx["label"].get(lang, tx["label"]["tr"]) if tx else None),
                      "correct": correct_tx["label"].get(lang, correct_tx["label"]["tr"]) if correct_tx else None,
                      "is_correct": tx_correct},
    }


async def examiner_narrative(report: Dict[str, Any], c: Dict[str, Any], lang: str) -> str:
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
    text = await llm_call(system, prompt, temperature=0.4)
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


@api_router.post("/sessions/{sid}/score")
async def score_session(sid: str):
    s = await db.sessions.find_one({"id": sid})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    c = get_case(s["case_id"])
    report = deterministic_score(s, c)
    report["narrative"] = await examiner_narrative(report, c, s["lang"])
    report["case_title"] = c["title"].get(s["lang"], c["title"]["tr"])
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    await db.sessions.update_one({"id": sid}, {"$set": {"ended": True, "report": report}})
    await db.reports.insert_one({"id": str(uuid.uuid4()), "session_id": sid, "case_id": c["case_id"],
                                 "report": report, "created_at": report["generated_at"]})
    return report


@api_router.get("/demo")
async def demo(lang: str = "tr"):
    c = get_case("acute-pulpitis")
    L = lambda v: v.get(lang, v["tr"])
    script_tr = [
        ("student", "Merhaba, şikayetiniz nedir?"),
        ("patient", "Sağ alt azı dişimde geceleri artan zonklayıcı bir ağrı var."),
        ("student", "Bu ağrı ne zaman başladı?"),
        ("patient", "Yaklaşık 4 gündür var, gittikçe kötüleşiyor."),
        ("student", "Geceleri veya uzanınca değişiyor mu?"),
        ("patient", "Geceleri, özellikle uzandığımda çok daha kötü. Dün gece uyuyamadım."),
        ("student", "Soğuk veya sıcak içeceklerle ağrı oluyor mu?"),
        ("patient", "Soğuk içince keskin bir ağrı oluyor ve dakikalarca geçmiyor."),
        ("student", "Yüzünüzde şişlik var mı?"),
        ("patient", "Hayır, yüzümde şişlik yok."),
    ]
    script_en = [
        ("student", "Hello, what brings you in today?"),
        ("patient", "A throbbing pain in my lower right molar that gets worse at night."),
        ("student", "When did the pain start?"),
        ("patient", "It's been about 4 days and getting worse."),
        ("student", "Is it worse at night or when lying down?"),
        ("patient", "It's much worse at night, especially lying down. I couldn't sleep last night."),
        ("student", "Does cold or hot trigger the pain?"),
        ("patient", "Cold drinks trigger a sharp pain that lingers for minutes."),
        ("student", "Any swelling on your face?"),
        ("patient", "No, there's no swelling on my face."),
    ]
    return {
        "case": public_case(c, lang),
        "script": [{"role": r, "text": t} for r, t in (script_tr if lang == "tr" else script_en)],
        "exams": [{"label": L(a["label"]), "result": L(a["result"])} for a in c["exam_actions"][:3]],
        "tests": [{"label": L(t["label"]), "result": L(t["result"])} for t in c["tests"] if t["indicated"]],
        "diagnosis": L(next(d["label"] for d in c["diagnosis_options"] if d["correct"])),
        "treatment": L(next(t["label"] for t in c["treatment_options"] if t["correct"])),
    }


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
