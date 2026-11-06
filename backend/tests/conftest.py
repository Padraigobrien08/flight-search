import pytest

from app.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(fare_provider="fixture", anthropic_api_key=None, travelpayouts_token=None, serpapi_api_key=None)
