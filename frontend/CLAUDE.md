# Frontend

- Form-first demo for one scenario (EDI -> Lima / La Paz). Chat components from the original Vercel template are legacy; keep only what the narration needs (`MessageResponse` for streamed markdown).
- `/api/*` is rewritten to FastAPI (`next.config.ts`). No API routes in Next, no ranking logic in TypeScript.
- The acceptance specs in `tests/acceptance/` address the page by `data-testid`: trip-form, depart-date, flex-days, search-budget, pref-slider-<name>, pref-text, run-search, itinerary-card (with data-itinerary-id and data-utility), card-total, card-vs-cheapest, trace-panel, trace-event-<kind>, race-panel, race-replay, race-live, race-line, ablation-table, regret-chart.
- Types mirror the backend in `lib/types.ts`; change both together.
- Fonts are bundled (`geist` package); don't reintroduce `next/font/google`.
