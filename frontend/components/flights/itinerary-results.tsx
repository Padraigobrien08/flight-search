"use client";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Journey, PlanResult, ScoredItinerary } from "@/lib/types";

const HUB_NAMES: Record<string, string> = {
  MAD: "Madrid",
  LON: "London",
  PAR: "Paris",
  AMS: "Amsterdam",
  LIS: "Lisbon",
  BCN: "Barcelona",
  LIM: "Lima",
};

const gbp = (n: number) =>
  new Intl.NumberFormat("en-GB", { currency: "GBP", maximumFractionDigits: 0, style: "currency" }).format(n);

// Times are local to each airport, so format the wall-clock string as-is.
const when = (iso: string) => {
  const d = new Date(`${iso.slice(0, 16)}Z`);
  return d.toLocaleString("en-GB", { day: "numeric", hour: "2-digit", minute: "2-digit", month: "short", timeZone: "UTC", weekday: "short" });
};

const hours = (min: number) => `${Math.floor(min / 60)}h${String(min % 60).padStart(2, "0")}`;

function structureLabel(s: ScoredItinerary) {
  const it = s.itinerary;
  const hub = it.hub ? (HUB_NAMES[it.hub] ?? it.hub) : null;
  if (it.structure === "stopover") return `Stopover in ${hub}`;
  if (it.structure === "split") return `Split tickets via ${hub}`;
  return "One ticket";
}

function JourneyRow({ label, journey, hub }: { label: string; journey: Journey; hub: string | null }) {
  const route = [journey.legs[0].origin, ...journey.legs.map((l) => l.destination)].join(" → ");
  const carriers = [...new Set(journey.legs.map((l) => l.carrier))].join(", ");
  const stays = journey.connections.filter((c) => c.hub_night);
  return (
    <div className="grid grid-cols-[4.5rem_1fr] gap-x-3 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <div className="min-w-0">
        <div className="font-medium">{route}</div>
        <div className="text-muted-foreground">
          {when(journey.legs[0].depart)} → {when(journey.legs.at(-1)?.arrive ?? "")} · {hours(journey.travel_minutes)} travelling
          · {journey.stops === 0 ? "non-stop" : `${journey.stops} stop${journey.stops > 1 ? "s" : ""}`}
          {stays.length > 0 && ` · ${stays.map((c) => `${c.nights} night${c.nights > 1 ? "s" : ""} in ${hub ? (HUB_NAMES[hub] ?? hub) : c.airport}`).join(", ")}`}
        </div>
        <div className="text-muted-foreground text-xs">{carriers}</div>
      </div>
    </div>
  );
}

function ItineraryCard({ s }: { s: ScoredItinerary }) {
  const it = s.itinerary;
  const warnings = s.flags.filter((f) => !f.includes("planned stay"));
  return (
    <div className={cn("rounded-xl border bg-card p-4 shadow-xs", s.rank === 1 && "border-primary/50 ring-1 ring-primary/20")}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-muted-foreground text-sm">#{s.rank}</span>
          <Badge variant={it.structure === "stopover" ? "default" : "secondary"}>{structureLabel(s)}</Badge>
          {it.tickets.length > 1 && <Badge variant="outline">{it.tickets.length} tickets</Badge>}
        </div>
        <div className="text-right">
          <div className="font-semibold text-lg">{gbp(it.total_cost)}</div>
          <div className="text-muted-foreground text-xs">
            {s.vs_cheapest === 0 ? "cheapest shown" : `+${gbp(s.vs_cheapest)} vs cheapest`}
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-2">
        {it.journeys.map((j, i) => (
          <JourneyRow hub={it.hub} journey={j} key={j.legs[0].depart + j.legs[0].origin} label={i === 0 ? "Out" : "Back"} />
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5 text-xs">
        <span className="text-muted-foreground">
          Fares {gbp(it.fare_total)}
          {it.extra_cost > 0 && ` + ${gbp(it.extra_cost)} est. (${it.extra_cost_note})`}
        </span>
      </div>
      {warnings.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {warnings.map((f) => (
            <Badge className="font-normal" key={f} variant="outline">
              {f.replace("->", "→")}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

export function ItineraryResults({ result }: { result: PlanResult }) {
  if (result.ranked.length === 0) {
    return <div className="rounded-xl border p-4 text-muted-foreground text-sm">No itineraries passed your limits.</div>;
  }
  return (
    <div className="flex w-full flex-col gap-3">
      {result.ranked.map((s) => (
        <ItineraryCard key={s.itinerary.id} s={s} />
      ))}
      <p className="text-muted-foreground text-xs">
        {result.searches_used} of {result.search_budget} live searches ·{" "}
        {result.date_pairs.length} date pair{result.date_pairs.length > 1 ? "s" : ""} sampled
        {result.pruned.length > 0 && ` · skipped ${result.pruned.map((p) => p.hub).join(", ")}`}
      </p>
    </div>
  );
}
