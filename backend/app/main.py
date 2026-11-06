from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent import stream as ui
from app.agent.agent import run_agent
from app.agent.llm import LLM, AnthropicLLM
from app.config import Settings, get_settings
from app.engine.planner import plan
from app.models import PlanResult, Preferences, TripRequest
from app.providers.factory import budgeted, cache_provider

app = FastAPI(title="Value-ranked flight search")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["*"], allow_headers=["*"])


class ChatRequest(BaseModel):
    id: str
    messages: list[dict]


def get_llm(settings: Settings = Depends(get_settings)) -> LLM:
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not set")
    return AnthropicLLM(settings.anthropic_api_key, settings.anthropic_model)


@app.get("/api/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "ok": True,
        "fare_provider": settings.fare_provider,
        "cache": cache_provider(settings).name,
        "llm": settings.anthropic_model if settings.anthropic_api_key else None,
    }


@app.post("/api/chat")
async def chat(req: ChatRequest, llm: LLM = Depends(get_llm), settings: Settings = Depends(get_settings)):
    return StreamingResponse(
        run_agent(req.messages, req.id, llm, settings), media_type="text/event-stream", headers=ui.HEADERS
    )


class PlanRequest(BaseModel):
    trip: TripRequest
    preferences: Preferences = Preferences()


@app.post("/api/plan", response_model=PlanResult)
async def plan_endpoint(req: PlanRequest, settings: Settings = Depends(get_settings)) -> PlanResult:
    """Run the planner directly, without the LLM. Useful for debugging and evaluation."""
    return await plan(req.trip, req.preferences, budgeted(settings, req.trip.search_budget), cache_provider(settings))
