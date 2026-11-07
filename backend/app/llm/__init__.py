"""The LLM layer: the only code that talks to an LLM vendor (OpenAI), one model per role, inside a spend cap."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from app.config import Settings
from app.llm.base import LLM, TurnResult
from app.llm.routing import ROLES, model_for, reasoning_effort_for
from app.llm.spend import SpendCapReached, SpendGuard

LLMFactory = Callable[[str], LLM]


@lru_cache
def _guard(cap_usd: float, ledger_path: str | None) -> SpendGuard:
    return SpendGuard(cap_usd, ledger_path)


def spend_guard(settings: Settings) -> SpendGuard:
    """One guard per (cap, ledger) per process, shared by every role."""
    return _guard(settings.llm_monthly_cap_usd, settings.llm_spend_ledger)


def llm_factory(settings: Settings) -> LLMFactory:
    """role -> LLM, with the role's model and reasoning effort, all under the same spend guard."""
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    from app.llm.openai_llm import OpenAILLM

    guard = spend_guard(settings)

    def make(role: str) -> LLM:
        return OpenAILLM(
            model_for(role, settings),
            guard,
            api_key=settings.openai_api_key,
            reasoning_effort=reasoning_effort_for(role, settings),
        )

    return make


__all__ = [
    "LLM",
    "LLMFactory",
    "ROLES",
    "SpendCapReached",
    "SpendGuard",
    "TurnResult",
    "llm_factory",
    "model_for",
    "spend_guard",
]
