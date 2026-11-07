import pytest

from app.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(fare_provider="fixture", openai_api_key=None, llm_spend_ledger=None, travelpayouts_token=None, serpapi_api_key=None)
