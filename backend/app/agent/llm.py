"""Compatibility import: the LLM protocol now lives in app.llm (F10). Vendor code is in app/llm/ only."""

from app.llm.base import LLM, TurnResult

__all__ = ["LLM", "TurnResult"]
