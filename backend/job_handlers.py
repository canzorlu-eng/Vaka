"""Background job handlers. Imported for its side effect of registering them with jobs.HANDLERS."""
import logging
from typing import Any, Dict

import catalogue
import generation
import jobs
import llm
import repo
from config import settings
from case_store import TOPICS

logger = logging.getLogger(__name__)


@jobs.handler("case_generation")
async def generate_case(job: Dict[str, Any], progress: jobs.ProgressFn) -> Dict[str, Any]:
    payload = job["payload"]
    topic, lang = payload["topic"], payload.get("lang", "tr")
    topic_name = next((t["name"]["en"] for t in TOPICS if t["id"] == topic), None)
    if topic_name is None:
        raise jobs.JobError("unknown_topic", permanent=True)
    user = await repo.get_user(job["user_id"])
    if user is None:
        raise jobs.JobError("user_gone", permanent=True)
    if not llm.llm_available():
        raise jobs.JobError("generation_unavailable", permanent=True)

    await progress(10, "drafting")
    existing = ", ".join(c["title"]["en"] for c in catalogue.builtin_cases(topic))
    prompt = generation.build_prompt(topic_name, existing)
    ref = f"job:{job['id']}"
    raw = await llm.llm_call(generation.SYSTEM_PROMPT, prompt, temperature=0.9, user=user, kind="generate", ref=ref, json_mode=True,
                                 model=settings.gemini_model_generation or None)
    data = generation._extract_json(raw)
    if not data:
        await progress(55, "repairing")
        raw = await llm.llm_call(generation.SYSTEM_PROMPT, prompt + "\nReturn ONLY JSON.", temperature=0.7,
                                 user=user, kind="generate", ref=ref, json_mode=True,
                                 model=settings.gemini_model_generation or None)
        data = generation._extract_json(raw)
    if not data:
        raise jobs.JobError("invalid_model_output")

    await progress(85, "validating")
    case = generation._normalize_generated(data)
    case["case_id"] = f"gen-{job['id'].hex[:12]}"   # deterministic: a retried job cannot create a second case
    case["topic"] = topic
    await repo.insert_ai_case(case, user["id"]) if not await repo.get_ai_case(case["case_id"], user["id"]) else None
    return {"case_id": case["case_id"], "title": case["title"].get(lang, case["title"]["tr"])}
