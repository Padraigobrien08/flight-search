from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent import stream as ui
from app.agent.agent import run_agent
from app.api.deps import get_llm, get_llm_factory
from app.api.plans import router as plans_router
from app.api.race import router as race_router
from app.config import Settings, get_settings
from app.llm import LLM, ROLES, model_for, spend_guard
from app.providers.factory import cache_provider

# get_llm and get_llm_factory are re-exported: tests and scripts/serve_fake.py override them via app.main.
__all__ = ["app", "get_llm", "get_llm_factory"]

app = FastAPI(title="Value-ranked flight search")
app.include_router(plans_router)
app.include_router(race_router)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["*"], allow_headers=["*"])


class ChatRequest(BaseModel):
    id: str
    messages: list[dict]


@app.get("/api/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "ok": True,
        "fare_provider": settings.fare_provider,
        "cache": cache_provider(settings).name,
        "llm": {role: model_for(role, settings) for role in ROLES} if settings.openai_api_key else None,
        "llm_spend_usd_this_month": round(spend_guard(settings).spent(), 4),
        "spend_cap_reached": spend_guard(settings).reached(),
    }


@app.post("/api/chat")
async def chat(req: ChatRequest, llm: LLM = Depends(get_llm), settings: Settings = Depends(get_settings)):
    return StreamingResponse(
        run_agent(req.messages, req.id, llm, settings), media_type="text/event-stream", headers=ui.HEADERS
    )
