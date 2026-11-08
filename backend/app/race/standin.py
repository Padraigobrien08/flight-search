"""A scripted stand-in for the `llm` planner, used only to make clearly labelled placeholder recordings.

It is not a model and makes no decisions: it plays a fixed, simple search plan (a through
ticket, then Madrid, then London, positioning with a night each way) and stops. Recordings
made with it carry source="placeholder" and must be replaced by a real model's runs.
"""

from __future__ import annotations

from datetime import timedelta

from app.llm.base import TurnResult
from app.models import TripRequest


def _call(i: int, **args: object) -> dict:
    return {"type": "tool_use", "id": f"s{i}", "name": "search_route", "input": args}


def script(req: TripRequest) -> list[list[dict]]:
    d, r = req.depart_earliest + timedelta(days=1), req.return_earliest + timedelta(days=1)
    day = timedelta(days=1)
    turns = [
        [
            _call(
                0,
                origin=req.origin,
                destination=req.destination,
                date=str(d),
                return_date=str(r),
                return_origin=req.end_airport,
            )
        ]
    ]
    for i, (hub, arrival) in enumerate((("MAD", "MAD"), ("LHR", "STN")), start=1):
        turns.append(
            [
                _call(
                    10 * i,
                    origin=hub,
                    destination=req.destination,
                    date=str(d),
                    return_date=str(r),
                    return_origin=req.end_airport,
                    return_destination=hub,
                ),
                _call(
                    10 * i + 1, origin=req.origin, destination=arrival, date=str(d - day), return_date=str(r + 2 * day)
                ),
            ]
        )
    return turns


class ScriptedStandIn:
    model = "scripted-stand-in (placeholder, not a model)"

    def __init__(self, req: TripRequest):
        self.turns = script(req)

    async def stream_turn(self, system, tools, messages):  # noqa: ANN001, ANN201
        if self.turns:
            yield TurnResult(content=self.turns.pop(0), stop_reason="tool_use")
        else:
            yield TurnResult(content=[{"type": "text", "text": "done"}], stop_reason="end_turn")
