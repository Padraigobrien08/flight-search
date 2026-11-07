"""The LLM protocol every caller uses, whatever the vendor.

The internal message format is content blocks: text, tool_use and tool_result
(Anthropic-style dicts). Adapters convert to and from their vendor's format.
An adapter may add opaque blocks of its own (e.g. OpenAI reasoning items) that
callers pass through history untouched.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class TurnResult:
    content: list[dict[str, Any]] = field(default_factory=list)  # content blocks as dicts
    stop_reason: str = "end_turn"  # "end_turn", "tool_use" or "max_tokens"
    usage: dict[str, int] = field(default_factory=dict)  # input_tokens, cached_tokens, output_tokens


class LLM(Protocol):
    def stream_turn(self, system: str, tools: list[dict], messages: list[dict]) -> AsyncIterator[str | TurnResult]:
        """Yield text deltas (str; "" marks the start of a new text block), then exactly one TurnResult."""
        ...
