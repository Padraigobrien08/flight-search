from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM: OpenAI, one model per role (app/llm/routing.py). Every model here needs a price in app/llm/spend.py.
    # gpt-6-astra is OpenAI's flagship for complex reasoning; parse and narrate could use a cheaper model.
    openai_api_key: str | None = None
    openai_model_parse: str = "gpt-6-astra"
    openai_model_narrate: str = "gpt-6-astra"
    openai_model_baseline: str = "gpt-6-astra"  # the `llm` planner: always the strongest model
    openai_reasoning_parse: str | None = "low"
    openai_reasoning_narrate: str | None = "low"
    openai_reasoning_baseline: str | None = "high"
    llm_monthly_cap_usd: float = 20.0
    llm_spend_ledger: str | None = "var/llm_spend.json"  # None keeps spend in memory only

    # Which live fare source to use. "fixture" needs no network or keys.
    fare_provider: Literal["fixture", "fli", "serpapi"] = "fixture"
    serpapi_api_key: str | None = None
    travelpayouts_token: str | None = None
    currency: str = "GBP"

    default_search_budget: int = 30
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
