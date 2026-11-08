"""Shared FastAPI dependencies. Tests override these with fakes."""

from __future__ import annotations

from fastapi import Depends, HTTPException

from app.config import Settings, get_settings
from app.llm import LLM, LLMFactory, llm_factory


def get_llm_factory(settings: Settings = Depends(get_settings)) -> LLMFactory:
    """role -> LLM (parse, narrate, baseline)."""
    try:
        return llm_factory(settings)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def get_llm(factory: LLMFactory = Depends(get_llm_factory)) -> LLM:
    """The legacy chat loop narrates, so it uses the narrate model."""
    return factory("narrate")
