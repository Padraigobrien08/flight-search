# Session report: F10-openai-layer (2026-11-07)

## Tests
- Unit tests: 73 passed, 0 failed (64 before; `tests/test_llm.py` adds 9, all using a fake OpenAI client).
- Acceptance: F1-F6 and F10 pass (`test_llm_layer.py`, 4 tests).
- Features passing: 7/22.
- What the new tests check:
  - streaming deltas and text-block markers;
  - the request shape (`store=False`, instructions, function tools, reasoning effort, encrypted reasoning included);
  - cost recorded at list price, with cached input billed at the cached rate;
  - reasoning items going back to the API verbatim on the next turn;
  - no request sent once the cap is reached;
  - a model with no price refused before any request;
  - monthly reset and ledger persistence across a restart;
  - conversion edge cases;
  - per-role routing;
  - no vendor SDK imported outside `app/llm/`.
- Manual check:
  - `/api/health` reports models per role, spend this month and `spend_cap_reached`;
  - `/api/chat` without a key returns 500 "OPENAI_API_KEY is not set";
  - the `FAKE_LLM` override still streams.

## Metrics
Not run: the LLM layer doesn't change the planner or the simulator. No real OpenAI call was made: `openai.com` and
`api.openai.com` are not reachable from this environment, and the tests use fakes by design.

## UI
Not run: nothing under `frontend/` changed. The legacy chat endpoint keeps its stream format.

## What changed
- `app/llm/` is the only place that imports the OpenAI SDK:
  - `base.py`: the `LLM` protocol and `TurnResult`, which now also carries usage.
  - `openai_llm.py`: the Responses API adapter.
  - `routing.py`: one model and one reasoning effort per role.
  - `spend.py`: `SpendGuard`, monthly in UTC, with an optional JSON ledger.
- Reasoning items are kept as an opaque `openai_reasoning` block and sent back encrypted (`store=False`). The
  `llm` baseline (F8) therefore keeps its chain of thought across tool calls instead of losing it each turn.
- `main.py`: `get_llm_factory` (role to LLM), which the F11-F15 tests override. The legacy chat uses the narrate
  model. `/api/health` reports spend.
- The Anthropic SDK and settings are removed. `app/agent/llm.py` re-exports the protocol, because the locked F8 and
  F11 tests import `TurnResult` from there.

## Open problems
- **Question for Padraig: models and prices.** OpenAI's pages couldn't be fetched (the network blocks openai.com).
  Search results disagree on the current line-up and prices. The one near-official fact is a search snippet of
  OpenAI's models page: `gpt-6-astra`, "our flagship model for complex reasoning", $10 input / $50 output per 1M
  tokens. So every role defaults to `gpt-6-astra`, at $10 / $1 cached / $50, and the guard refuses any model without
  a price.
  - Parse and narrate could use a cheaper model. Name the IDs and prices and they go in `PRICES`.
  - The cached-input price ($1) is from a third-party page; confirm it.
- **Reasoning effort values are unverified.** The defaults are `low` / `low` / `high`. If `gpt-6-astra` uses
  different effort names, the first real call will fail with an API error.
- **Your spend cap.** The default is $20/month, taken from your `.env.example`. A call is only checked before it
  starts, so concurrent calls can overshoot the cap by their own cost.
- **The ledger disappears on Fly.** It lives at `var/llm_spend.json`, which won't survive a scale-to-zero restart
  without a volume. F21 should mount one or move the ledger.
- **F8 will need a change to `BenchTrip`.** F8's locked test reads `trip.origin` and `trip.depart_earliest` from a
  `BenchTrip`, which keeps them under `.request`. F8 should add the pass-through properties.
- **CLAUDE.md is out of date.** It still describes the chat loop as Anthropic-based. I didn't edit it.
