import type { Initiative } from "../api/types";

export interface PlacedDot {
  initiative: Initiative;
  /** percent of the plot width/height */
  x: number;
  y: number;
  /** pixel nudge so initiatives with identical scores stay visible */
  dx: number;
  dy: number;
}

// Scores run 1–10 -> 5%–95% of the axis. High value is at the top.
const toPercent = (score: number) => ((score - 0.5) / 10) * 100;
const GOLDEN_ANGLE = 2.399963;
const SPIRAL_STEP_PX = 9;

export const isPlottable = (i: Initiative): boolean =>
  i.value_score !== null && i.solution_complexity_score !== null;

// Both scores are coarse (many initiatives share the exact same pair), so
// each group sharing a cell is spread on a small deterministic spiral.
export function layoutDots(items: Initiative[]): PlacedDot[] {
  const seen = new Map<string, number>();
  return items.filter(isPlottable).map((initiative) => {
    const effort = initiative.solution_complexity_score as number;
    const value = initiative.value_score as number;
    const key = `${effort}|${value}`;
    const k = seen.get(key) ?? 0;
    seen.set(key, k + 1);
    const r = SPIRAL_STEP_PX * Math.sqrt(k);
    return {
      initiative,
      x: toPercent(effort),
      y: 100 - toPercent(value),
      dx: Math.round(r * Math.cos(k * GOLDEN_ANGLE)),
      dy: Math.round(r * Math.sin(k * GOLDEN_ANGLE)),
    };
  });
}
