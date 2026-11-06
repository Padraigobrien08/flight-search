// Mirrors backend/app/models.py (PlanResult and friends).

export type Leg = {
  carrier: string;
  flight_number: string | null;
  origin: string;
  destination: string;
  depart: string;
  arrive: string;
  duration_min: number;
};

export type Connection = {
  airport: string;
  minutes: number;
  night_minutes: number;
  between_tickets: boolean;
  hub_night: boolean;
  nights: number;
};

export type Journey = {
  legs: Leg[];
  connections: Connection[];
  travel_minutes: number;
  stops: number;
};

export type Itinerary = {
  id: string;
  structure: "through" | "split" | "stopover";
  hub: string | null;
  tickets: { provider: string; price: number; currency: string }[];
  journeys: Journey[];
  extra_cost: number;
  extra_cost_note: string | null;
  fare_total: number;
  total_cost: number;
};

export type ScoredItinerary = {
  itinerary: Itinerary;
  utility: number;
  rank: number;
  vs_cheapest: number;
  breakdown: Record<string, number>;
  flags: string[];
};

export type PlanResult = {
  ranked: ScoredItinerary[];
  pruned: { hub: string; reason: string; bound: number | null }[];
  searches_used: number;
  search_budget: number;
  date_pairs: [string, string][];
  notes: string[];
};

export type ToolOutput =
  | { kind: "plan"; result: PlanResult; modelView: string }
  | { kind: "route"; tickets: unknown[]; modelView: string }
  | { kind: "preferences"; changed: Record<string, unknown>; modelView: string }
  | { kind: "error"; message: string; modelView: string };
