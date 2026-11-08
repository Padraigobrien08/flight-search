"""Free text to a partial Preferences update, via the "parse" model.

The model only maps what the person said onto preference fields; it never sees fares or
itineraries. Its reply is treated as untrusted: unknown fields and wrong types are dropped,
numbers are clamped to PREFERENCE_BOUNDS, and anything that isn't a JSON object changes
nothing. Real OpenAI models get strict structured output (every field nullable, null meaning
"not mentioned"); any other LLM is asked for plain JSON and parsed the same way.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.llm.base import LLM, TurnResult
from app.models import PREFERENCE_BOUNDS, Preferences

MAX_TEXT_CHARS = 1000
BOOL_FIELDS = ("allow_same_day_self_transfer", "allow_airport_overnight")
INT_FIELDS = ("max_stops",)


def _field_lines() -> str:
    lines = []
    for name, info in Preferences.model_fields.items():
        if name in PREFERENCE_BOUNDS:
            lo, hi = PREFERENCE_BOUNDS[name]
            lines.append(f"- {name}: {info.description or ''} (default {info.default}, allowed {lo:g} to {hi:g})")
        else:
            lines.append(f"- {name}: true/false (default {info.default})")
    return "\n".join(lines)


SYSTEM = f"""You turn what a traveller says about their preferences into settings for a flight-ranking tool.
Money is in GBP. Fields:
{_field_lines()}

Rules:
- Set only fields the text clearly expresses a view on; leave every other field null (or omit it).
- Use the person's own numbers when they give them ("I'd pay £150 for a night in Madrid" -> stopover_bonus 150).
  Without a number, move the default in the direction they mean by a sensible amount.
- If the text says nothing about travel preferences, set nothing.
Reply with a single JSON object and nothing else."""


def json_schema() -> dict:
    """Strict structured-output schema: every field present, null when not mentioned."""
    props: dict[str, Any] = {}
    for name in Preferences.model_fields:
        if name in BOOL_FIELDS:
            props[name] = {"type": ["boolean", "null"]}
        else:
            lo, hi = PREFERENCE_BOUNDS[name]
            kind = "integer" if name in INT_FIELDS else "number"
            props[name] = {"type": [kind, "null"], "description": f"{lo:g} to {hi:g}"}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


@dataclass
class ParseResult:
    update: dict[str, Any] = field(default_factory=dict)
    clamped: dict[str, dict[str, float]] = field(default_factory=dict)  # field -> {"asked": x, "used": y}
    ignored: dict[str, str] = field(default_factory=dict)  # field -> why
    note: str | None = None


def _json_object(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    for candidate in (text, *(m.group(0) for m in re.finditer(r"\{.*\}", text, re.S))):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def clean(raw: dict[str, Any]) -> ParseResult:
    """Keep known fields with sensible types, clamped to their bounds."""
    out = ParseResult()
    for name, value in raw.items():
        if value is None:
            continue
        if name not in Preferences.model_fields:
            out.ignored[name] = "not a preference"
            continue
        if name in BOOL_FIELDS:
            if isinstance(value, bool):
                out.update[name] = value
            else:
                out.ignored[name] = "expected true/false"
            continue
        if isinstance(value, bool) or not isinstance(value, int | float) or value != value:  # NaN
            out.ignored[name] = "expected a number"
            continue
        lo, hi = PREFERENCE_BOUNDS[name]
        used = min(max(float(value), lo), hi)
        if name in INT_FIELDS:
            used = int(round(used))
        elif used == int(used):
            used = int(used)
        if used != value:
            out.clamped[name] = {"asked": value, "used": used}
        out.update[name] = used
    return out


async def parse_preferences(text: str, llm: LLM, current: Preferences | None = None) -> ParseResult:
    schema_llm = getattr(llm, "with_json_schema", None)
    if callable(schema_llm):
        llm = schema_llm("preferences_update", json_schema())
    prompt = text if current is None else f"Current settings: {current.model_dump_json()}\n\nTraveller: {text}"
    reply: TurnResult | None = None
    async for item in llm.stream_turn(SYSTEM, [], [{"role": "user", "content": [{"type": "text", "text": prompt}]}]):
        if isinstance(item, TurnResult):
            reply = item
    said = "".join(b.get("text", "") for b in (reply.content if reply else []) if b.get("type") == "text")
    raw = _json_object(said)
    if raw is None:
        return ParseResult(note="the model's reply wasn't a JSON object, so nothing changed")
    return clean(raw)
