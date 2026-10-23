import type { Initiative } from "../api/types";
import { valueFraction } from "./format";

export interface PlacedDot {
  initiative: Initiative;
  /** percent of the plot width/height */
  x: number;
  y: number;
  /** pixel nudge so initiatives with identical scores stay visible */
  dx: number;
  dy: number;
}

// Effort runs 1–10 -> 5%–95% of the axis. Potential uses the log scale of
// valueFraction (1k–1M €/year) -> 5%–95%. High potential is at the top.
const effortPercent = (score: number) => ((score - 0.5) / 10) * 100;
const valuePercent = (eur: number) => 5 + valueFraction(eur) * 90;
const GOLDEN_ANGLE = 2.399963;
const SPIRAL_STEP_PX = 9;

export const isPlottable = (i: Initiative): boolean =>
  i.potential_value_eur !== null && i.solution_complexity_score !== null;

// The heuristic produces coarse values (many initiatives share the exact same
// pair), so each group sharing a spot is spread on a small deterministic spiral.
export function layoutDots(items: Initiative[]): PlacedDot[] {
  const seen = new Map<string, number>();
  return items.filter(isPlottable).map((initiative) => {
    const effort = initiative.solution_complexity_score as number;
    const value = initiative.potential_value_eur as number;
    const key = `${effort}|${value}`;
    const k = seen.get(key) ?? 0;
    seen.set(key, k + 1);
    const r = SPIRAL_STEP_PX * Math.sqrt(k);
    return {
      initiative,
      x: effortPercent(effort),
      y: 100 - valuePercent(value),
      dx: Math.round(r * Math.cos(k * GOLDEN_ANGLE)),
      dy: Math.round(r * Math.sin(k * GOLDEN_ANGLE)),
    };
  });
}
