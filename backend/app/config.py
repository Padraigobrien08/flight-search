from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5-5"

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
