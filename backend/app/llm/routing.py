"""Which model does which job: the one place a role is mapped to a model."""

from __future__ import annotations

from typing import Literal

from app.config import Settings

Role = Literal["parse", "narrate", "baseline"]
ROLES: tuple[Role, ...] = ("parse", "narrate", "baseline")


def model_for(role: str, settings: Settings) -> str:
    """parse: free text to preferences. narrate: trade-off explanations. baseline: the `llm` search planner."""
    if role not in ROLES:
        raise ValueError(f"unknown LLM role {role!r}; roles are {', '.join(ROLES)}")
    return getattr(settings, f"openai_model_{role}")


def reasoning_effort_for(role: str, settings: Settings) -> str | None:
    if role not in ROLES:
        raise ValueError(f"unknown LLM role {role!r}; roles are {', '.join(ROLES)}")
    return getattr(settings, f"openai_reasoning_{role}") or None
