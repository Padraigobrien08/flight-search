import json
from datetime import date

import pytest

from app.agent.grounding import claims, unsupported_numbers
from app.engine.planner import plan
from app.models import Preferences, TripRequest
from app.providers.base import BudgetedProvider
from app.sim import FareSimulator


@pytest.fixture(scope="module")
def plan_json() -> tuple[str, dict]:
    import asyncio

    req = TripRequest(
        origin="EDI",
        destination="LIM",
        return_from="LPB",
        depart_earliest=date(2027, 5, 22),
        depart_latest=date(2027, 5, 22),
        return_earliest=date(2027, 6, 6),
        return_latest=date(2027, 6, 6),
    )
    sim = FareSimulator(seed=0)
    res = asyncio.run(plan(req, Preferences(), BudgetedProvider(sim, 20), sim))
    out = res.model_dump_json()
    return out, json.loads(out)


def test_sentences_built_from_real_planner_output_are_supported(plan_json):
    out, data = plan_json
    top, second = data["ranked"][0], data["ranked"][1]
    it = top["itinerary"]
    total, fares = it["total_cost"], it["fare_total"]
    leg = it["journeys"][0]["legs"][0]
    hours = it["journeys"][0]["travel_minutes"] / 60
    h, m = divmod(it["journeys"][0]["travel_minutes"], 60)
    text = (
        f"The top option costs £{total:,.2f} (about £{round(total):,}), of which £{fares:,.0f} is fares. "
        f"It is £{second['vs_cheapest']:,.0f} more than the cheapest shown. "
        f"Outbound takes {h}h{m:02d}, roughly {hours:.1f} hours, and the first flight is {leg['duration_min']} minutes. "
        f"Leave on 22 May 2027; it is option 1 of 5 with 2 stops and 1 night in a hub."
    )
    assert unsupported_numbers(text, [out]) == []


def test_nudged_numbers_are_caught(plan_json):
    out, data = plan_json
    it = data["ranked"][0]["itinerary"]
    total = it["total_cost"]
    hours = it["journeys"][0]["travel_minutes"] / 60
    bad = unsupported_numbers(f"It costs £{total + 5:,.0f} and takes {hours + 0.5:.1f} hours.", [out])
    assert len(bad) == 2


@pytest.mark.parametrize(
    ("text", "kind", "value"),
    [
        ("£1,060", "money", 1060),
        ("£1060.50", "money", 1060.5),
        ("£1.2k", "money", 1200),
        ("900 GBP", "money", 900),
        ("1,174 pounds", "money", 1174),
        ("12 hours", "hours", 12),
        ("a 12-hour flight", "hours", 12),
        ("15h25", "hours", 15 + 25 / 60),
        ("4 hours 15 minutes", "hours", 4.25),
        ("4h 15m", "hours", 4.25),
        ("45 min", "hours", 0.75),
        ("2.5 hrs", "hours", 2.5),
    ],
)
def test_claim_formats(text, kind, value):
    [c] = claims(text)
    assert c.kind == kind and c.value == pytest.approx(value)


@pytest.mark.parametrize(
    "text",
    [
        "Leave on 22 May; option 1 of 5 has 2 stops.",
        "Fly 2027-05-22, back 6 Jun.",
        "It departs at 23:45 and has 3 legs and 1 night in Madrid.",
        "5m people fly this route; it is the 2nd option.",
    ],
)
def test_dates_ranks_counts_and_times_are_not_claims(text):
    assert claims(text) == []


def test_a_price_cannot_be_vouched_for_by_a_duration_or_a_count():
    out = json.dumps({"travel_hours": 16, "searches_used": 16, "rank": 3})
    assert unsupported_numbers("It costs £16 and takes 16 hours.", [out]) == ["£16"]
    assert unsupported_numbers("Search budget used: 16 hours.", [json.dumps({"searches_used": 16})]) == ["16 hours"]


def test_minutes_fields_support_hour_claims_and_breakdowns_support_money():
    out = json.dumps({"duration_min": 705, "breakdown": {"stopover": 80.0, "fares": -911.0}})
    assert unsupported_numbers("A non-stop of 11h45 (11.75 hours); £80 for the stay, £911 in fares.", [out]) == []


def test_text_outputs_and_k_notation():
    assert unsupported_numbers("Madrid is £911 and 11h45.", ["Madrid: total £911, flight 11h45"]) == []
    assert unsupported_numbers("About £1.2k.", [json.dumps({"price": 1174})]) == []
    assert unsupported_numbers("About £1.3k.", [json.dumps({"price": 1174})]) == ["£1.3k"]


def test_each_bad_claim_is_reported_once_in_order():
    assert unsupported_numbers("£5, then 3 hours, then £5 again.", ["{}"]) == ["£5", "3 hours"]
