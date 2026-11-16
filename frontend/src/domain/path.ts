import type { Initiative } from "../api/types";

// The main track an idea walks along; On hold, Cancelled and Unknown stand outside it.
export const MAIN_TRACK = ["Ideation", "PoC", "MVP", "Implementation", "Production"] as const;
export type TrackStage = (typeof MAIN_TRACK)[number];

// Idea and Exploration became one stage (Ideation) in 11/2026; older data may still use them.
const ALIASES: Record<string, string> = { Idea: "Ideation", Exploration: "Ideation" };
export const canonicalStage = (stage: string): string => ALIASES[stage] ?? stage;

/** Position on the main track, -1 outside it. */
export const trackIndex = (stage: string): number => (MAIN_TRACK as readonly string[]).indexOf(canonicalStage(stage));

export interface PathStats {
  /** all use cases, inside and outside the main track */
  total: number;
  /** per main-track stage: use cases at or beyond it */
  reached: number[];
  /** per stage: share (0–1) of those that reached it that are at or beyond the next one; null for the last or without data */
  moveOn: (number | null)[];
  /** use cases in Production */
  live: number;
  /** live / total */
  liveShare: number | null;
}

/** From the cockpit at the time the landing page was designed (11/2026), when no data is there. */
export const FALLBACK_STATS: PathStats = {
  total: 166,
  reached: [143, 52, 36, 32, 22],
  moveOn: [0.36, 0.69, 0.89, 0.69, null],
  live: 22,
  liveShare: 0.13,
};

export function pathStats(items: Initiative[]): PathStats {
  const at = MAIN_TRACK.map(() => 0);
  for (const i of items) {
    const k = trackIndex(i.stage);
    if (k >= 0) at[k] += 1;
  }
  if (at.every((n) => n === 0)) return FALLBACK_STATS;
  const reached = at.map((_, k) => at.slice(k).reduce((a, b) => a + b, 0));
  const moveOn = reached.map((n, k) => (k < reached.length - 1 && n > 0 ? reached[k + 1] / n : null));
  const live = at[at.length - 1];
  return { total: items.length, reached, moveOn, live, liveShare: items.length ? live / items.length : null };
}

export const percent = (share: number | null): string => (share === null ? "–" : `${Math.round(share * 100)} %`);
