"""POST /api/preferences/parse: free text to a partial, clamped preferences update (F14).

GET /api/preferences/bounds gives the valid range of every slider, the same ranges the
parser clamps to, so the UI and the parser can't disagree.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agent.preferences import MAX_TEXT_CHARS, parse_preferences
from app.api.deps import get_llm_factory
from app.llm import LLMFactory
from app.llm.spend import SpendCapReached, UnpricedModel
from app.models import PREFERENCE_BOUNDS, Preferences

router = APIRouter()


class ParseRequest(BaseModel):
    text: str = Field(max_length=MAX_TEXT_CHARS)
    current: dict[str, Any] = Field({}, description="the sliders' current values, for relative statements")


class ParseResponse(BaseModel):
    preferences_update: dict[str, Any]
    clamped: dict[str, dict[str, float]] = {}
    ignored: dict[str, str] = {}
    note: str | None = None


@router.post("/api/preferences/parse", response_model=ParseResponse)
async def parse_endpoint(req: ParseRequest, factory: LLMFactory = Depends(get_llm_factory)) -> ParseResponse:
    try:
        current = Preferences.model_validate(req.current) if req.current else None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"current: {e}") from e
    if not req.text.strip():
        return ParseResponse(preferences_update={}, note="no text")
    try:
        result = await parse_preferences(req.text, factory("parse"), current)
    except (SpendCapReached, UnpricedModel) as e:
        raise HTTPException(status_code=503, detail=f"{e}. The sliders still work.") from e
    return ParseResponse(
        preferences_update=result.update, clamped=result.clamped, ignored=result.ignored, note=result.note
    )


@router.get("/api/preferences/bounds")
def bounds() -> dict[str, dict[str, float]]:
    defaults = Preferences()
    return {
        name: {"min": lo, "max": hi, "default": getattr(defaults, name)} for name, (lo, hi) in PREFERENCE_BOUNDS.items()
    }
