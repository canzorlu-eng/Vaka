"""Public catalogue endpoints (topics, cases, demo). Browsing needs no account; AI cases appear only to their owner."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Response

import catalogue
from auth import optional_user
from casetools import public_case

router = APIRouter(prefix="/api", tags=["catalogue"])


def _cache_headers(response: Response, user: Optional[Dict[str, Any]]) -> None:
    response.headers["Cache-Control"] = "private, max-age=60" if user else "public, max-age=300"


@router.get("/topics")
async def list_topics(response: Response, lang: str = Query("tr", pattern="^(tr|en)$"),
                      user: Optional[Dict[str, Any]] = Depends(optional_user)):
    _cache_headers(response, user)
    cases = await catalogue.visible_cases(user)
    out = []
    for t in catalogue.topics():
        in_topic = [c for c in cases if c.get("topic") == t["id"]]
        out.append({
            "id": t["id"], "icon": t["icon"], "color": t["color"],
            "name": t["name"].get(lang, t["name"]["tr"]), "blurb": t["blurb"].get(lang, t["blurb"]["tr"]),
            "count": len(in_topic),
            "levels": {d: sum(1 for c in in_topic if c["difficulty"] == d) for d in ("easy", "moderate", "hard")},
        })
    return out


@router.get("/cases")
async def list_cases(response: Response, lang: str = Query("tr", pattern="^(tr|en)$"), topic: Optional[str] = None,
                     difficulty: Optional[str] = Query(None, pattern="^(easy|moderate|hard)$"),
                     limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                     user: Optional[Dict[str, Any]] = Depends(optional_user)):
    _cache_headers(response, user)
    cases = [c for c in await catalogue.visible_cases(user, topic) if not difficulty or c["difficulty"] == difficulty]
    response.headers["X-Total-Count"] = str(len(cases))
    page: List[Dict[str, Any]] = cases[offset:offset + limit]
    return [{
        "case_id": c["case_id"], "topic": c.get("topic"), "difficulty": c["difficulty"],
        "title": c["title"].get(lang, c["title"]["tr"]),
        "chief_complaint": c["chief_complaint"].get(lang, c["chief_complaint"]["tr"]),
        "patient_name": c["patient"]["name"].get(lang, c["patient"]["name"]["tr"]),
        "age": c["patient"]["age"], "mood": c["patient"]["avatar_mood"], "generated": bool(c.get("generated")),
    } for c in page]


@router.get("/cases/{case_id}")
async def case_detail(case_id: str, response: Response, lang: str = Query("tr", pattern="^(tr|en)$"),
                      user: Optional[Dict[str, Any]] = Depends(optional_user)):
    _cache_headers(response, user)
    return public_case(await catalogue.get_case(case_id, user), lang)


@router.get("/demo")
async def demo(response: Response, lang: str = Query("tr", pattern="^(tr|en)$")):
    response.headers["Cache-Control"] = "public, max-age=3600"
    c = await catalogue.get_case("acute-pulpitis", None)
    L = lambda v: v.get(lang, v["tr"])  # noqa: E731
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
