"""Serve the API with the scripted LLM and fixture fares: a real UI with no API key."""

import uvicorn

from app.config import Settings, get_settings
from app.main import app, get_llm
from tests.fakes import ScriptedLLM

app.dependency_overrides[get_llm] = lambda: ScriptedLLM()
app.dependency_overrides[get_settings] = lambda: Settings(fare_provider="fixture")

if __name__ == "__main__":
    uvicorn.run(app, port=8000, log_level="warning")
