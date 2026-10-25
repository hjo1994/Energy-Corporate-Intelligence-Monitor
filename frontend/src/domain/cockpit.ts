import type { Initiative } from "../api/types";
import { businessUnitOf, NO_BUSINESS_UNIT, NO_BUSINESS_UNIT_LABEL } from "./filters";
import { isPlottable } from "./matrix";
import { formatMillions, isValued, netValue, quarterIndex, quarterLabel, stageGroupOf, valueBridge } from "./value";

// Aggregations behind the start page (value cockpit). Like the KPI tiles they run in the browser on
// the filtered set. Value figures are over the initiatives with potential and cost estimated (as in
// valueBridge), so potential − cost = net and the drivers add up to the potential.

const sum = (values: number[]): number => values.reduce((a, b) => a + b, 0);

export interface Cockpit {
  /** initiatives passed in */
  total: number;
  /** of those, with potential and cost estimated */
  valued: number;
  potential: number;
  net: number;
  /** potential of the initiatives in Implementation or Production */
  live: number;
  /** initiatives whose potential exceeds their annual cost */
  selfFunding: number;
  /** potential delivered up to the end of the quarter after today's */
  scheduled: { until: string; potential: number };
  /** potential per business unit, biggest first */
  byBusinessUnit: { label: string; potential: number }[];
  /** potential per value bucket */
  drivers: { label: string; potential: number }[];
}

export function cockpit(items: Initiative[], today: Date = new Date()): Cockpit {
  const bridge = valueBridge(items);
  const valued = items.filter(isValued);
  const pot = (i: Initiative) => i.potential_value_eur as number;
  const until = today.getFullYear() * 4 + Math.floor(today.getMonth() / 3) + 1;

  const units = new Map<string, number>();
  for (const i of valued) units.set(businessUnitOf(i), (units.get(businessUnitOf(i)) ?? 0) + pot(i));

  return {
    total: items.length,
    valued: valued.length,
    potential: bridge.potential,
    net: bridge.net,
    live: sum(valued.filter((i) => stageGroupOf(i.stage) === "live").map(pot)),
    selfFunding: valued.filter((i) => netValue(i) > 0).length,
    scheduled: {
      until: quarterLabel(until),
      potential: sum(
        valued
          .filter((i) => {
            const q = quarterIndex(i.date_delivery);
            return q !== null && q <= until;
          })
          .map(pot),
      ),
    },
    byBusinessUnit: [...units]
      .map(([bu, potential]) => ({ label: bu === NO_BUSINESS_UNIT ? NO_BUSINESS_UNIT_LABEL : bu, potential }))
      .sort((a, b) => b.potential - a.potential || a.label.localeCompare(b.label)),
    drivers: bridge.buckets,
  };
}

// ---------- matrix ----------

/** Effort (SolutionComplexityScore) axis of the matrix and where "low" turns into "high". */
export const EFFORT_MIN = 1;
export const EFFORT_MAX = 9;
export const EFFORT_SPLIT = 5;
/** Potential (EUR per year) where "low" turns into "high". */
export const VALUE_SPLIT = 100_000;

export interface MatrixPoint {
  initiative: Initiative;
  effort: number;
  potential: number;
  /** 1–10 for the most valuable plotted initiatives, otherwise null */
  rank: number | null;
}

export interface ValueMatrix {
  points: MatrixPoint[];
  /** the ranked points, rank 1 first */
  top: MatrixPoint[];
  /** log axis bounds in EUR per year: powers of ten around the data, always spanning VALUE_SPLIT */
  min: number;
  max: number;
  /** initiatives with an estimated potential, and how many of them have an effort estimate */
  estimated: number;
  plotted: number;
  /** share of the estimated potential the plotted initiatives cover, 0–1 (null without any potential) */
  coverage: number | null;
}

export function valueMatrix(items: Initiative[], topCount = 10): ValueMatrix {
  const estimated = items.filter((i) => i.potential_value_eur !== null);
  const ranked = estimated
    .filter(isPlottable)
    .sort((a, b) => (b.potential_value_eur as number) - (a.potential_value_eur as number) || a.id - b.id);
  const points = ranked.map((initiative, k) => ({
    initiative,
    effort: Math.min(EFFORT_MAX, Math.max(EFFORT_MIN, initiative.solution_complexity_score as number)),
    potential: initiative.potential_value_eur as number,
    rank: k < topCount ? k + 1 : null,
  }));

  const values = points.map((p) => Math.max(p.potential, 1));
  const decade = (v: number, round: (x: number) => number) => 10 ** round(Math.log10(v));
  const total = sum(estimated.map((i) => i.potential_value_eur as number));
  return {
    points,
    top: points.filter((p) => p.rank !== null),
    min: Math.min(VALUE_SPLIT / 10, ...values.map((v) => decade(v, Math.floor))),
    max: Math.max(VALUE_SPLIT * 10, ...values.map((v) => decade(v, Math.ceil))),
    estimated: estimated.length,
    plotted: points.length,
    coverage: total > 0 ? sum(points.map((p) => p.potential)) / total : null,
  };
}

/** Position 0 (bottom) … 1 (top) of a potential on the matrix's log axis. */
export const logPosition = (eur: number, min: number, max: number): number =>
  (Math.log10(Math.min(max, Math.max(min, eur))) - Math.log10(min)) / (Math.log10(max) - Math.log10(min));

// ---------- labels ----------

/** "9.8 M€" / "+2.7 M€" */
export const formatMEur = (eur: number, signed = false): string => `${formatMillions(eur, signed)} M€`;

/** "457 k€" / "1,061 k€" */
export const formatKEur = (eur: number): string => `${Math.round(eur / 1_000).toLocaleString("en-US")} k€`;

/** Axis tick: "100", "1k", "100k", "1M" */
export const formatTick = (eur: number): string =>
  eur >= 1_000_000 ? `${eur / 1_000_000}M` : eur >= 1_000 ? `${eur / 1_000}k` : String(eur);
