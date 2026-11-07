import pytest
from fastapi.testclient import TestClient

from app.api.plans import PlanStore, StoredPlan
from app.config import Settings, get_settings
from app.main import app
from app.sim import FareSimulator

TRIP = {
    "origin": "EDI",
    "destination": "LIM",
    "return_from": "LPB",
    "depart_earliest": "2027-05-21",
    "depart_latest": "2027-05-24",
    "return_earliest": "2027-06-05",
    "return_latest": "2027-06-08",
    "search_budget": 20,
}


@pytest.fixture
def client():
    app.dependency_overrides[get_settings] = lambda: Settings(fare_provider="simulator", llm_spend_ledger=None)
    yield TestClient(app)
    app.dependency_overrides.clear()


def plan(client, **prefs):
    r = client.post("/api/plan", json={"trip": TRIP, "preferences": prefs})
    assert r.status_code == 200, r.text
    return r.json()


def rerank(client, plan_id, **prefs):
    return client.post("/api/rerank", json={"plan_id": plan_id, "preferences": prefs})


def ids(body):
    return [s["itinerary"]["id"] for s in body["ranked"]]


def test_rerank_with_the_plans_own_preferences_reproduces_the_plan(client):
    body = plan(client, stopover_bonus=50)
    again = rerank(client, body["plan_id"]).json()
    assert again["ranked"] == body["ranked"]
    assert again["preferences"] == body["preferences"]
    assert (
        body["stats"]["candidates"] >= len(body["ranked"]) and body["stats"]["searches_used"] == body["searches_used"]
    )


def test_an_expensive_hotel_night_reprices_stays_and_reorders(client):
    body = plan(client)
    assert body["ranked"][0]["itinerary"]["structure"] == "stopover"
    dear = rerank(client, body["plan_id"], hotel_cost_per_night=600, stopover_bonus=0).json()
    assert dear["ranked"][0]["itinerary"]["structure"] == "through"
    stays = [s for s in dear["ranked"] if s["itinerary"]["structure"] == "stopover"]
    assert stays and all("~£600" in s["itinerary"]["extra_cost_note"] for s in stays)
    assert ids(dear) != ids(body)


def test_rerank_never_searches(client, monkeypatch):
    body = plan(client)

    async def boom(*a, **k):
        raise AssertionError("rerank searched")

    monkeypatch.setattr(FareSimulator, "search", boom)
    monkeypatch.setattr(FareSimulator, "lowest_price", boom)
    r = rerank(client, body["plan_id"], value_of_hour=40)
    assert r.status_code == 200 and r.json()["searches_used"] == body["searches_used"]


def test_partial_preferences_merge_over_the_plans_own(client):
    body = plan(client, stopover_bonus=120, value_of_hour=25)
    r = rerank(client, body["plan_id"], per_stop=99).json()
    assert r["preferences"]["stopover_bonus"] == 120
    assert r["preferences"]["value_of_hour"] == 25
    assert r["preferences"]["per_stop"] == 99


def test_unknown_plan_and_bad_preferences(client):
    assert rerank(client, "nope").status_code == 404
    body = plan(client)
    assert rerank(client, body["plan_id"], max_stops="lots").status_code == 422
    r = client.post("/api/plan", json={"trip": TRIP, "preferences": {"value_of_hour": "fast"}})
    assert r.status_code == 422


def test_store_keeps_the_most_recent_plans():
    store = PlanStore(capacity=2)
    a = store.put(StoredPlan(result=None))  # type: ignore[arg-type]
    b = store.put(StoredPlan(result=None))  # type: ignore[arg-type]
    store.get(a)  # touch a: b is now the oldest
    c = store.put(StoredPlan(result=None))  # type: ignore[arg-type]
    assert store.get(b) is None and store.get(a) and store.get(c)
