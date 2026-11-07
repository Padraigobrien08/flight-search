# The simulated network

Written on 2026-11-07, before the price model (F2) and before either fare model (F9a, F9b) exists.
The network is fixed data in `network.py`. A seed changes prices, never which routes exist,
when they fly, or what they are anchored to.

## What it covers

Edinburgh to Lima, home from Lima or from La Paz, through the six hubs in `app/engine/hubs.py`.

| Part | Routes |
| --- | --- |
| Positioning | EDI to MAD, STN, LTN, LHR, CDG, AMS, LIS, BCN, and back |
| Long-haul | MAD, LHR, CDG, AMS, LIS, BCN to LIM, and back |
| Through tickets | EDI to LIM via AMS (KLM), CDG (Air France), CDG + BOG (Air France / Avianca), MAD (Iberia), YYZ + YUL (Air Canada) |
| La Paz end | LPB to LIM; LPB to MAD, LHR, CDG, AMS, BCN; LPB to EDI |

Out of scope: rail positioning (the planner has no rail arrival point yet), other origins, other destinations.

## Anchors and their sources

Every service carries one anchor: an observed fare with the dates it was seen for and where it came from.
The price model divides out the weekday effects of those dates, so on the anchor dates the
seed-average simulated fare reproduces the anchor.

| Source tag | Meaning |
| --- | --- |
| `spec` | The spec's worked example and pruning section (Google Flights, searched 6 Nov 2026, out Sat 22 May, back Sun 6 Jun 2027) |
| `fixture` | `app/providers/fixture.py`, whose docstring says Google Flights on 6 Nov 2026; not in the spec, not re-checked |
| `design` | Chosen for this network, inside a range the spec gives; the reason is in the table below |

Where the fixture and the spec disagree, the spec wins:
- AMS to LIM: the fixture has £950 return; the spec says Europe to Lima returns were £700–850 from every hub. Set to £850.
- The La Paz end: the fixture's La Paz one-ways imply an open-jaw premium of about £40; the spec says the La Paz end added
  £150–230 whichever way it was solved. The La Paz anchors are set as premiums inside that range.

## Why each part is there

These are the features that make the search hard. Each is stated with the behaviour it should produce, so the F3
exhaustive optimum can check it and nobody can later say the network was tuned to a fare model. Until F3 lands, they
are intentions, not results.

1. **Madrid is the stopover hub, so its value depends on preferences.** EDI to MAD (easyJet, £168) plus a non-stop
   MAD to LIM (£743) is £911, the same money as Air Canada's 21-hour through ticket (£915). With a night in Madrid each
   way, Madrid's utility moves by 2 x (stopover bonus - hotel) against every other option, so it should rank first for
   someone who values the stay and drop well down for someone who doesn't. This is the spec's headline trade-off.
2. **London is the cheapest route on paper and the worst journey.** EDI to STN (£52) plus Avianca LHR to LIM via Bogotá
   (£710) is the cheapest complete price (£762), but it needs an airport change (STN to LHR) and a 4h15 stop in Bogotá.
   A planner that ranks by price finds it first; one that ranks by utility has to look past it.
3. **Barcelona looks cheap in the cache and isn't.** LEVEL's low-cost long-haul has the most volatile price history in
   the network (log-sd 0.25 against 0.05 for legacy carriers). The cache keeps the lowest of several stale observations,
   so its Barcelona bound is far below what a live search returns. A planner that trusts cached bounds spends searches
   on Barcelona first. The bias comes out of the cache process; nothing on Barcelona is hard-coded as optimistic.
4. **The La Paz end changes the answer by date.** Madrid has the best La Paz link: BoA to Santa Cruz, then Air Europa's
   non-stop to Madrid (premium £150). It flies Monday, Thursday and Saturday only, like thin long-haul routes do. On
   other days Madrid's La Paz end goes via Bogotá (premium £230), the same as London's. So the best hub for an
   open-jaw depends on the return date, and the interaction only shows up if a planner searches hub and date together.
5. **Lisbon has no La Paz link.** It is a cheap Lima gateway (£728, via Madrid on Air Europa) but nothing flies La Paz
   to Lisbon, so on an open-jaw it only works as a Lima return plus La Paz to Lima (£226–234). It tests whether a
   planner handles a hub whose open-jaw search returns nothing.
6. **Through tickets span the price range.** Air Canada (£915, 21 h, 2 stops) is the cheapest protected option and the
   slowest; KLM via Amsterdam (£1,174, 15h25, 1 stop) is the fastest and dearest. They set the baseline any split
   ticket must beat.
7. **Amsterdam and Paris are plausible but rarely best.** KLM AMS to LIM non-stop (£850) and Air France / Avianca CDG to
   LIM via Bogotá (£774) are realistic gateways that should usually be pruned. They exist so pruning has something to
   prune.

## La Paz premiums (design)

A premium is how much more an open-jaw costs than the same hub's Lima return. The La Paz one-way anchor is derived from
it: `hub return / 1.6 + premium / 0.8` (a return is 0.8 x two one-ways).

| La Paz to | Routing | Days | Premium |
| --- | --- | --- | --- |
| MAD | BoA LPB-VVI, Air Europa VVI-MAD non-stop | Mon, Thu, Sat | £150 |
| MAD | Avianca via BOG | daily | £230 |
| LHR | Avianca via BOG | daily | £230 |
| CDG | Avianca LPB-BOG, Air France BOG-CDG | daily | £200 |
| BCN | Avianca via BOG | daily | £210 |
| AMS | Avianca LPB-BOG, KLM BOG-AMS | daily | £220 |
| EDI | Avianca LPB-BOG, KLM BOG-AMS-EDI | daily | £200 over the cheapest through return |
| LIM | BoA via VVI (`fixture`, £226) and Avianca via BOG (`fixture`, £234) | daily | one-way fix |

## Schedules

Times are local. Durations are plausible, not looked up, except where the spec gives one: EDI to MAD 3h, MAD to LIM
11h45, LHR to LIM 18h30 with 4h15 in Bogotá, KLM 15h25, Air Canada about 21h. Return schedules are written out, not
mirrored.
