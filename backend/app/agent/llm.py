"""A thin streaming interface over the Anthropic Messages API.

The agent only needs: stream text deltas, then the final content blocks and
stop reason. Keeping it this small makes the agent testable with a fake.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class TurnResult:
    content: list[dict[str, Any]] = field(default_factory=list)  # Anthropic content blocks as dicts
    stop_reason: str = "end_turn"


class LLM(Protocol):
    def stream_turn(self, system: str, tools: list[dict], messages: list[dict]) -> AsyncIterator[str | TurnResult]:
        """Yield text deltas (str), then exactly one TurnResult."""
        ...


class AnthropicLLM:
    def __init__(self, api_key: str, model: str, max_tokens: int = 4096):
        from anthropic import AsyncAnthropic

        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    async def stream_turn(self, system, tools, messages):  # noqa: ANN001, ANN201
        async with self.client.messages.stream(
            model=self.model, max_tokens=self.max_tokens, system=system, tools=tools, messages=messages
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield event.delta.text
                elif event.type == "content_block_start" and event.content_block.type == "text":
                    yield ""  # marks a new text block
            final = await stream.get_final_message()
        yield TurnResult(
            content=[b.model_dump(exclude_none=True) for b in final.content],
            stop_reason=final.stop_reason or "end_turn",
        )
