---
name: e2e-check
description: Run the real chat UI end to end with the scripted LLM and fixture fares, and capture desktop and mobile screenshots. Use after any change to the frontend, the stream protocol, or tool outputs.
---

# End-to-end UI check

No API key needed: `FAKE_LLM=1` serves the backend with scripted LLMs. `scripts/e2e.mjs` drives the page; when the UI changes shape (e.g. F16 replaces the chat with a form), update the script's steps to match. It isn't locked; the acceptance specs are.

1. Start the stack in the background: `FAKE_LLM=1 scripts/dev.sh` (wait until `curl -s localhost:8000/api/health` and `curl -s localhost:3000` both respond).
2. Run `node scripts/e2e.mjs reports/screens` (set `CHROME_PATH` if Playwright's own browser isn't installed). Exit code 2 means page errors; they're printed as JSON.
3. **Look at every screenshot** with the Read tool before saying anything about the UI. Check: cards render, prices and journeys readable, nothing overflows on mobile, no error banner.
4. Stop the stack.

If the stream changed, also confirm the AI SDK still parses it: the scripted run reaching results proves it, a blank assistant message means the client rejected a chunk.
