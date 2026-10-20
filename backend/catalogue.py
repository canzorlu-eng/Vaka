"""Case catalogue access: built-in authored cases (public) + AI-generated cases (visible to their creator only)."""
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

import repo
from case_store import CASES, TOPICS

_BY_ID: Dict[str, Dict[str, Any]] = {}


def _index() -> Dict[str, Dict[str, Any]]:
    if not _BY_ID:
        _BY_ID.update({c["case_id"]: c for c in CASES})
    return _BY_ID


def builtin_cases(topic: Optional[str] = None) -> List[Dict[str, Any]]:
    return [c for c in CASES if topic is None or c["topic"] == topic]


async def get_case(case_id: str, user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    found = _index().get(case_id)
    if found:
        return found
    if case_id.startswith("gen-") and user:
        ai = await repo.get_ai_case(case_id, user["id"], user["role"] == "admin")
        if ai:
            return ai
    raise HTTPException(status_code=404, detail="Case not found")


async def visible_cases(user: Optional[Dict[str, Any]], topic: Optional[str] = None) -> List[Dict[str, Any]]:
    cases = builtin_cases(topic)
    if user:
        cases = cases + await repo.list_ai_cases(user["id"], topic)
    return cases


def topics() -> List[Dict[str, Any]]:
    return TOPICS
