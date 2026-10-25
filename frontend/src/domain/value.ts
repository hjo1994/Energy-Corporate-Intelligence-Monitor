import type { Initiative } from "../api/types";
import { businessUnitOf, businessUnitsIn } from "./filters";
import { formatEur, formatQuarter } from "./format";

// Aggregations behind the Value view (value bridge, break-even map, value roadmap). Like the
// KPI tiles they run in the browser on the filtered set; all inputs are heuristic estimates.

/** An initiative whose potential and annual cost are both estimated. */
export const isValued = (i: Initiative): boolean =>
  i.potential_value_eur !== null &&
  i.hypothetical_value_eur !== null &&
  i.confidence_score !== null &&
  i.delivery_score !== null &&
  i.annual_cost_eur !== null;

// The stored costs are expected costs (cost if delivered x DeliveryScore, input orchestration since
// 24.10.2026), so the annual cost is delivery-weighted; dividing by the DeliveryScore gives it back as if delivered.
export const costIfDelivered = (i: Initiative): number | null =>
  i.annual_cost_eur === null || !i.delivery_score ? null : i.annual_cost_eur / i.delivery_score;

export const netValue = (i: Initiative): number => (i.potential_value_eur as number) - (i.annual_cost_eur as number);

const sum = (values: number[]): number => values.reduce((a, b) => a + b, 0);

export const BUCKETS = [
  { key: "efficiency_score_eur", label: "Efficiency" },
  { key: "quality_score_eur", label: "Quality" },
  { key: "risk_reduction_score_eur", label: "Risk reduction" },
  { key: "strategic_value_score_eur", label: "Strategic" },
] as const;

export interface Bridge {
  /** initiatives passed in */
  total: number;
  /** of those, with potential and cost estimated; every figure below is over these */
  valued: number;
  hypothetical: number;
  /** hypothetical x (1 - confidence) */
  confidenceHaircut: number;
  /** hypothetical x confidence x (1 - delivery) */
  deliveryHaircut: number;
  potential: number;
  annualCost: number;
  net: number;
  positive: { count: number; net: number };
  negative: { count: number; net: number };
  /** the lowest confidence in the set and how many initiatives sit on it */
  lowestConfidence: { value: number; count: number } | null;
  /** potential per value bucket (bucket x confidence x delivery); adds up to `potential` */
  buckets: { label: string; potential: number }[];
}

// hypothetical → − confidence → − delivery → potential → − annual cost → net.
// The two haircuts are computed per initiative, so the steps add up exactly.
export function valueBridge(items: Initiative[]): Bridge {
  const valued = items.filter(isValued);
  const nets = valued.map(netValue);
  const confidences = valued.map((i) => i.confidence_score as number);
  const lowest = confidences.length ? Math.min(...confidences) : null;
  const hypothetical = sum(valued.map((i) => i.hypothetical_value_eur as number));
  const potential = sum(valued.map((i) => i.potential_value_eur as number));
  const annualCost = sum(valued.map((i) => i.annual_cost_eur as number));
  return {
    total: items.length,
    valued: valued.length,
    hypothetical,
    confidenceHaircut: sum(valued.map((i) => (i.hypothetical_value_eur as number) * (1 - (i.confidence_score as number)))),
    deliveryHaircut: sum(
      valued.map(
        (i) => (i.hypothetical_value_eur as number) * (i.confidence_score as number) * (1 - (i.delivery_score as number)),
      ),
    ),
    potential,
    annualCost,
    net: potential - annualCost,
    positive: { count: nets.filter((n) => n > 0).length, net: sum(nets.filter((n) => n > 0)) },
    negative: { count: nets.filter((n) => n <= 0).length, net: sum(nets.filter((n) => n <= 0)) },
    lowestConfidence: lowest === null ? null : { value: lowest, count: confidences.filter((c) => c === lowest).length },
    buckets: BUCKETS.map(({ key, label }) => ({
      label,
      potential: sum(
        valued.map((i) => (i[key] ?? 0) * (i.confidence_score as number) * (i.delivery_score as number)),
      ),
    })),
  };
}

export interface WaterfallStep {
  label: string;
  /** the bar spans from..to (EUR per year); totals start at 0 */
  from: number;
  to: number;
  kind: "hypothetical" | "haircut" | "potential" | "cost" | "net";
}

export function waterfallSteps(b: Bridge): WaterfallStep[] {
  const afterConfidence = b.hypothetical - b.confidenceHaircut;
  return [
    { label: "Hypothetical", from: 0, to: b.hypothetical, kind: "hypothetical" },
    { label: "Confidence", from: b.hypothetical, to: afterConfidence, kind: "haircut" },
    { label: "Delivery", from: afterConfidence, to: afterConfidence - b.deliveryHaircut, kind: "haircut" },
    { label: "Potential", from: 0, to: b.potential, kind: "potential" },
    { label: "Cost / year", from: b.potential, to: b.net, kind: "cost" },
    { label: "Net / year", from: 0, to: b.net, kind: "net" },
  ];
}

// ---------- break-even map ----------

export type StageGroup = "early" | "test" | "live" | "other";

export const STAGE_GROUPS: { id: StageGroup; label: string }[] = [
  { id: "early", label: "Idea & Exploration" },
  { id: "test", label: "PoC & MVP" },
  { id: "live", label: "Implementation & Production" },
  { id: "other", label: "Unclear / paused" },
];

export function stageGroupOf(stage: string): StageGroup {
  if (stage === "Idea" || stage === "Exploration") return "early";
  if (stage === "PoC" || stage === "MVP") return "test";
  if (stage === "Implementation" || stage === "Production") return "live";
  return "other"; // On hold, Cancelled, Unknown
}

export interface BreakEvenPoint {
  initiative: Initiative;
  /** annual cost / potential in EUR per year */
  cost: number;
  potential: number;
  group: StageGroup;
  /** deterministic pixel nudge: the cost heuristic works in steps, so many dots share an x */
  jitter: number;
}

export const breakEvenPoints = (items: Initiative[]): BreakEvenPoint[] =>
  items.filter(isValued).map((i) => ({
    initiative: i,
    cost: i.annual_cost_eur as number,
    potential: i.potential_value_eur as number,
    group: stageGroupOf(i.stage),
    jitter: (((i.id * 7) % 9) - 4) * 2,
  }));

export function breakEvenStats(points: BreakEvenPoint[]) {
  return {
    total: points.length,
    above: points.filter((p) => p.potential > p.cost).length,
    net: sum(points.map((p) => p.potential - p.cost)),
  };
}

/** Round an axis maximum up to a whole step (100k € by default), never below one step. */
export const niceMax = (value: number, step = 100_000): number => Math.max(step, Math.ceil(value / step) * step);

// ---------- value roadmap ----------

export interface QuarterValue {
  /** "Q3 2026" */
  label: string;
  potential: number;
  count: number;
  cumulative: number;
}

export interface Roadmap {
  quarters: QuarterValue[];
  undated: { potential: number; count: number };
  /** share of the estimated potential without a delivery date, 0–1 (null without any potential) */
  undatedShare: number | null;
  /** business units (NO_BUSINESS_UNIT included) none of whose initiatives has a delivery date */
  undatedBusinessUnits: string[];
}

// Potential per delivery quarter, consecutive from the first to the last one (empty quarters stay
// visible as gaps), plus everything without a delivery date. Initiatives without potential are left out.
export function valueRoadmap(items: Initiative[]): Roadmap {
  const estimated = items.filter((i) => i.potential_value_eur !== null);
  const byQuarter = new Map<number, { potential: number; count: number }>();
  const undated = { potential: 0, count: 0 };
  for (const i of estimated) {
    const q = quarterIndex(i.date_delivery);
    if (q === null) {
      undated.potential += i.potential_value_eur as number;
      undated.count += 1;
      continue;
    }
    const entry = byQuarter.get(q) ?? { potential: 0, count: 0 };
    entry.potential += i.potential_value_eur as number;
    entry.count += 1;
    byQuarter.set(q, entry);
  }

  const quarters: QuarterValue[] = [];
  if (byQuarter.size) {
    const keys = [...byQuarter.keys()];
    let cumulative = 0;
    for (let q = Math.min(...keys); q <= Math.max(...keys); q++) {
      const entry = byQuarter.get(q) ?? { potential: 0, count: 0 };
      cumulative += entry.potential;
      quarters.push({ label: quarterLabel(q), ...entry, cumulative });
    }
  }
  const total = sum(estimated.map((i) => i.potential_value_eur as number));
  const dated = new Set(estimated.filter((i) => quarterIndex(i.date_delivery) !== null).map(businessUnitOf));
  return {
    quarters,
    undated,
    undatedShare: total > 0 ? undated.potential / total : null,
    undatedBusinessUnits: businessUnitsIn(estimated).filter((bu) => !dated.has(bu)),
  };
}

// Quarters as consecutive integers (year x 4 + quarter - 1), parsed from the string like formatQuarter.
export function quarterIndex(iso: string | null): number | null {
  const m = iso ? /^(\d{4})-(\d{2})/.exec(iso) : null;
  return m ? Number(m[1]) * 4 + Math.floor((Number(m[2]) - 1) / 3) : null;
}

export const quarterLabel = (q: number): string =>
  formatQuarter(`${Math.floor(q / 4)}-${String((q % 4) * 3 + 1).padStart(2, "0")}`);

// ---------- labels ----------

const MINUS = "−";

/** "39.8" / "−5.8" — millions of EUR with one decimal, for chart labels. */
export function formatMillions(eur: number, signed = false): string {
  const text = (Math.abs(eur) / 1_000_000).toFixed(1);
  if (eur < 0 && text !== "0.0") return `${MINUS}${text}`;
  return signed && eur > 0 ? `+${text}` : text;
}

/** "1,061" — thousands of EUR, for chart labels. */
export const formatThousands = (eur: number): string => Math.round(eur / 1_000).toLocaleString("en-US");

/** formatEur with a real minus sign and an explicit plus, for net values. */
export function formatSignedEur(eur: number): string {
  const text = formatEur(Math.abs(eur));
  return eur < 0 ? text.replace("≈ ", `≈ ${MINUS}`) : eur > 0 ? text.replace("≈ ", "≈ +") : text;
}
