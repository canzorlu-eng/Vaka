"""Long-running work as jobs: the client gets a job id immediately and polls for progress. A timed-out or
double-clicked request never loses or duplicates work (Idempotency-Key)."""
import re
from typing import Any, Dict

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

import jobs
import llm
from auth import current_user
from case_store import TOPICS
from plans import generations_this_month, plan_for
from ratelimit import limit

router = APIRouter(prefix="/api", tags=["jobs"])
_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{8,80}$")


class GenerateIn(BaseModel):
    topic: str = Field(max_length=40)
    lang: str = Field("tr", pattern="^(tr|en)$")


def _public(job: Dict[str, Any]) -> Dict[str, Any]:
    return {"job_id": str(job["id"]), "kind": job["kind"], "status": job["status"], "progress": job["progress"],
            "stage": job["stage"], "result": job["result"], "error": job["error"],
            "attempts": job["attempts"], "max_attempts": job["max_attempts"]}


@router.post("/cases/generate", status_code=202, dependencies=[Depends(limit("generate", 5, 3600))])
async def generate_case(body: GenerateIn, idempotency_key: str = Header(..., alias="Idempotency-Key"),
                        user: Dict[str, Any] = Depends(current_user)):
    if not _KEY_RE.match(idempotency_key):
        raise HTTPException(status_code=400, detail="Invalid Idempotency-Key")
    if body.topic not in {t["id"] for t in TOPICS}:
        raise HTTPException(status_code=400, detail="Unknown topic")
    if not llm.llm_available():
        raise HTTPException(status_code=503, detail="Generation unavailable")
    plan = await plan_for(user)
    used = await generations_this_month(user["id"])
    existing_key_job = None
    if used >= plan.generations_per_month:
        # a retry of an already-accepted request must still return its job, not a quota error
        existing_key_job = await jobs.get_by_key(user["id"], "case_generation", idempotency_key)
        if not existing_key_job:
            raise HTTPException(status_code=402, detail={"code": "quota_exceeded" if plan.generations_per_month else "upgrade_required",
                                                          "plan": plan.name, "limit": plan.generations_per_month, "used": used})
    job, _ = (existing_key_job, False) if existing_key_job else await jobs.enqueue(
        user["id"], "case_generation", {"topic": body.topic, "lang": body.lang}, idempotency_key, max_attempts=2)
    return _public(job)


@router.get("/jobs/{job_id}")
async def job_status(job_id: str, user: Dict[str, Any] = Depends(current_user)):
    job = await jobs.get_job(job_id, user["id"])
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _public(job)
