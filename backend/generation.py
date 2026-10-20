"""AI case generation: prompt, JSON extraction and normalisation of the model output into the internal schema."""
import json
import uuid
from typing import Any, Dict

from xray_library import XRAY_LIB


XRAY_LIB_HINT = "\n".join(f'- "{k}": {v["finding_en"]}' for k, v in XRAY_LIB.items())


def _extract_json(text: str):
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if "```" in t[3:] else t
        t = t.replace("json", "", 1) if t.lstrip().startswith("json") else t
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(t[start:end + 1])
    except Exception:
        return None


def _normalize_generated(g: Dict[str, Any]) -> Dict[str, Any]:
    """Validate & normalize an LLM-generated case into the internal schema."""
    def bil(v, fb=""):
        if isinstance(v, dict):
            return {"tr": v.get("tr", v.get("en", fb)), "en": v.get("en", v.get("tr", fb))}
        return {"tr": str(v or fb), "en": str(v or fb)}

    diff = g.get("difficulty", "moderate")
    if diff not in ("easy", "moderate", "hard"):
        diff = "moderate"
    mood = (g.get("patient", {}) or {}).get("avatar_mood", "neutral")
    if mood not in ("neutral", "pain", "anxious"):
        mood = "neutral"

    hidden = []
    hist_checklist = []
    for i, f in enumerate(g.get("hidden_facts", [])[:8]):
        fid = str(f.get("id") or f"f{i}")
        kws = f.get("keywords") or []
        if isinstance(kws, str):
            kws = [kws]
        kws = [str(k) for k in kws][:8] or ["?"]
        topic = bil(f.get("topic"), fid)
        hidden.append({"id": fid, "keywords": kws, "text": bil(f.get("text")), "topic": topic})
        hist_checklist.append({"id": fid, "keywords": kws, "red_flag": bool(f.get("red_flag")), "label": topic})

    exams = []
    exam_checklist = []
    for i, a in enumerate(g.get("exam_actions", [])[:6]):
        aid = str(a.get("id") or f"e{i}")
        sev = a.get("severity", "finding")
        if sev not in ("finding", "normal", "neutral"):
            sev = "finding"
        tooth = a.get("tooth")
        try:
            tooth = int(tooth) if tooth not in (None, "", "null") else None
        except Exception:
            tooth = None
        label = bil(a.get("label"), aid)
        exams.append({"id": aid, "label": label, "result": bil(a.get("result")),
                      "tooth": tooth, "severity": sev, "required": bool(a.get("required", True))})
        if a.get("required", True):
            exam_checklist.append({"id": aid, "red_flag": bool(a.get("red_flag", sev == "finding")), "label": label})

    # Tests: chosen library x-rays (indicated) + standard over-order traps
    lib_ids = [x for x in (g.get("xray_lib_ids") or []) if x in XRAY_LIB][:2]
    if not lib_ids:
        lib_ids = ["normal_bitewing"]
    tests = []
    for i, lid in enumerate(lib_ids):
        tests.append({"id": f"xray_{i+1}", "indicated": True,
                      "label": {"tr": f"Radyografi {i+1}", "en": f"Radiograph {i+1}"},
                      "result": {"tr": "Radyografik inceleme yapıldı.", "en": "Radiographic examination performed."},
                      "xray_lib": lid})
    tests.append({"id": "cbct", "indicated": False, "label": {"tr": "CBCT (3B tomografi)", "en": "CBCT (3D scan)"},
                  "result": {"tr": "Bu tabloda rutin endike değil.", "en": "Not routinely indicated here."}})
    tests.append({"id": "cbc", "indicated": False, "label": {"tr": "Tam kan sayımı", "en": "Complete blood count"},
                  "result": {"tr": "Lokalize diş tablosunda gerekli değil.", "en": "Not required for a localized dental presentation."}})

    def norm_options(key):
        opts = g.get(key, []) or []
        out = []
        for i, o in enumerate(opts[:4]):
            out.append({"id": str(o.get("id") or f"o{i}"), "label": bil(o.get("label")), "correct": bool(o.get("correct"))})
        if not out:
            out = [{"id": "o0", "label": {"tr": "Seçenek", "en": "Option"}, "correct": True}]
        if not any(o["correct"] for o in out):
            out[0]["correct"] = True
        seen = False
        for o in out:  # exactly one correct
            if o["correct"] and not seen:
                seen = True
            elif o["correct"]:
                o["correct"] = False
        return out

    p = g.get("patient", {}) or {}
    return {
        "case_id": f"gen-{uuid.uuid4().hex[:8]}",
        "generated": True,
        "difficulty": diff,
        "title": bil(g.get("title"), "Yeni Vaka"),
        "chief_complaint": bil(g.get("chief_complaint")),
        "patient": {"name": bil(p.get("name"), "Hasta"), "age": int(p.get("age", 40) or 40),
                    "sex": bil(p.get("sex"), ""), "setting": bil(p.get("setting"), ""), "avatar_mood": mood},
        "vitals": {"bp": str((g.get("vitals", {}) or {}).get("bp", "120/80")),
                   "hr": (g.get("vitals", {}) or {}).get("hr", 76),
                   "temp": str((g.get("vitals", {}) or {}).get("temp", "36.7°C")),
                   "spo2": str((g.get("vitals", {}) or {}).get("spo2", "99%"))},
        "hidden_facts": hidden or [{"id": "f0", "keywords": ["?"], "text": bil(g.get("chief_complaint")), "topic": bil("Şikayet", "Complaint")}],
        "exam_actions": exams or [{"id": "visual", "label": {"tr": "Görsel muayene", "en": "Visual inspection"},
                                   "result": bil("Muayene yapıldı.", "Examined."), "tooth": None, "severity": "finding", "required": True}],
        "tests": tests,
        "diagnosis_options": norm_options("diagnosis_options"),
        "treatment_options": norm_options("treatment_options"),
        "checklist": {"history": hist_checklist or [{"id": "f0", "keywords": ["?"], "red_flag": False, "label": bil("Şikayet", "Complaint")}],
                      "exam": exam_checklist or [{"id": "visual", "red_flag": False, "label": {"tr": "Görsel muayene", "en": "Visual inspection"}}]},
    }



SYSTEM_PROMPT = (
    "You are a dental education content author. Invent ONE clinically-plausible dental virtual-patient case "
    "for students to practise recognising findings. Output ONLY valid minified JSON, no prose, no markdown. "
    "Every human-readable string MUST be an object {\"tr\":..., \"en\":...} (Turkish + English). "
    "Keep all clinical facts realistic and internally consistent."
)


def build_prompt(topic_name: str, existing_titles: str) -> str:
    return (
        "Create a NEW dental case in the specialty '" + topic_name + "', different from these existing ones: " + existing_titles + ".\n\n"
        "Available X-ray library (id: true finding) — pick 1-2 ids whose findings fit your case, they will be shown to the learner:\n"
        + XRAY_LIB_HINT +
        "\n\nReturn JSON with EXACTLY these keys:\n"
        "{\"title\":{tr,en},\"difficulty\":\"easy|moderate|hard\",\"chief_complaint\":{tr,en},"
        "\"patient\":{\"name\":{tr,en},\"age\":int,\"sex\":{tr,en},\"setting\":{tr,en},\"avatar_mood\":\"neutral|pain|anxious\"},"
        "\"vitals\":{\"bp\":str,\"hr\":int,\"temp\":str,\"spo2\":str},"
        "\"hidden_facts\":[{\"id\":str,\"topic\":{tr,en},\"keywords\":[strings in BOTH tr and en],\"text\":{tr,en},\"red_flag\":bool}] (5-7 items),"
        "\"exam_actions\":[{\"id\":str,\"label\":{tr,en},\"result\":{tr,en},\"tooth\":int-or-null,\"severity\":\"finding|normal|neutral\",\"required\":bool}] (3-5 items),"
        "\"xray_lib_ids\":[1-2 ids from the library above],"
        "\"diagnosis_options\":[{\"id\":str,\"label\":{tr,en},\"correct\":bool}] (exactly 4, one correct),"
        "\"treatment_options\":[{\"id\":str,\"label\":{tr,en},\"correct\":bool}] (exactly 4, one correct)}"
    )
