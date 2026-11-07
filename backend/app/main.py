from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent import stream as ui
from app.agent.agent import run_agent
from app.config import Settings, get_settings
from app.engine.planner import plan
from app.llm import LLM, ROLES, LLMFactory, llm_factory, model_for, spend_guard
from app.models import PlanResult, Preferences, TripRequest
from app.providers.factory import budgeted, cache_provider

app = FastAPI(title="Value-ranked flight search")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["*"], allow_headers=["*"])


class ChatRequest(BaseModel):
    id: str
    messages: list[dict]


def get_llm_factory(settings: Settings = Depends(get_settings)) -> LLMFactory:
    """role -> LLM (parse, narrate, baseline). Tests override this with fakes."""
    try:
        return llm_factory(settings)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def get_llm(factory: LLMFactory = Depends(get_llm_factory)) -> LLM:
    """The legacy chat loop narrates, so it uses the narrate model."""
    return factory("narrate")


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


class PlanRequest(BaseModel):
    trip: TripRequest
    preferences: Preferences = Preferences()


@app.post("/api/plan", response_model=PlanResult)
async def plan_endpoint(req: PlanRequest, settings: Settings = Depends(get_settings)) -> PlanResult:
    """Run the planner directly, without the LLM. Useful for debugging and evaluation."""
    return await plan(req.trip, req.preferences, budgeted(settings, req.trip.search_budget), cache_provider(settings))
