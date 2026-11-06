from app.agent.llm import TurnResult

PLAN_ARGS = {
    "origin": "EDI", "destination": "LIM", "return_from": "LPB",
    "depart_earliest": "2027-05-21", "depart_latest": "2027-05-24",
    "return_earliest": "2027-06-05", "return_latest": "2027-06-08",
}


class ScriptedLLM:
    """Calls plan_trip on the first turn, then writes a short answer."""

    def __init__(self):
        self.calls: list[list[dict]] = []

    async def stream_turn(self, system, tools, messages):
        self.calls.append(list(messages))
        if len(self.calls) == 1:
            yield ""
            yield "Searching hubs and dates."
            yield TurnResult(content=[
                {"type": "text", "text": "Searching hubs and dates."},
                {"type": "tool_use", "id": "toolu_1", "name": "plan_trip", "input": PLAN_ARGS},
            ], stop_reason="tool_use")
        else:
            yield ""
            yield "Madrid with a night each way is the best value."
            yield TurnResult(content=[{"type": "text", "text": "Madrid with a night each way is the best value."}],
                             stop_reason="end_turn")
