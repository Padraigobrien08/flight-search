"""Vercel AI SDK "UI message stream" protocol (v1), as server-sent events.

The frontend's `useChat` parses each `data:` line against a strict schema,
so every chunk here carries exactly the fields the SDK expects.
"""

from __future__ import annotations

import json
from typing import Any

HEADERS = {
    "x-vercel-ai-ui-message-stream": "v1",
    "cache-control": "no-cache",
    "x-accel-buffering": "no",
}


def sse(chunk: dict[str, Any]) -> str:
    return f"data: {json.dumps(chunk, separators=(',', ':'), default=str)}\n\n"


DONE = "data: [DONE]\n\n"


def start(message_id: str) -> str:
    return sse({"type": "start", "messageId": message_id})


def start_step() -> str:
    return sse({"type": "start-step"})


def finish_step() -> str:
    return sse({"type": "finish-step"})


def text_start(part_id: str) -> str:
    return sse({"type": "text-start", "id": part_id})


def text_delta(part_id: str, delta: str) -> str:
    return sse({"type": "text-delta", "id": part_id, "delta": delta})


def text_end(part_id: str) -> str:
    return sse({"type": "text-end", "id": part_id})


def tool_input(call_id: str, name: str, args: Any) -> str:
    return sse(
        {"type": "tool-input-available", "toolCallId": call_id, "toolName": name, "input": args, "dynamic": True}
    )


def tool_output(call_id: str, output: Any) -> str:
    return sse({"type": "tool-output-available", "toolCallId": call_id, "output": output, "dynamic": True})


def tool_error(call_id: str, message: str) -> str:
    return sse({"type": "tool-output-error", "toolCallId": call_id, "errorText": message, "dynamic": True})


def error(message: str) -> str:
    return sse({"type": "error", "errorText": message})


def finish(reason: str = "stop") -> str:
    return sse({"type": "finish", "finishReason": reason})
