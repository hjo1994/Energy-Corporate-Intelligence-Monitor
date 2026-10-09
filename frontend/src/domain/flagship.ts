import type { Initiative } from "../api/types";
import { flagshipLabel } from "./format";

export const NOT_ASSIGNED_LABEL = "Not assigned";

export interface FlagshipStat {
  /** the value used by the flagship filter; "" = initiatives without any flagship */
  key: string;
  label: string;
  count: number;
  /** initiatives of this flagship that have a value score */
  rated: number;
  averageValue: number | null;
}

// One row per strategic pillar, biggest first; initiatives without a flagship come last so
// that the counts add up to the total instead of silently dropping them.
export function flagshipStats(items: Initiative[]): FlagshipStat[] {
  const groups = new Map<string, Initiative[]>();
  for (const i of items) {
    const key = i.value_type?.name ?? "";
    const group = groups.get(key);
    if (group) group.push(i);
    else groups.set(key, [i]);
  }

  const stats = [...groups].map(([key, group]) => {
    const scores = group.map((i) => i.value_score).filter((s): s is number => s !== null);
    return {
      key,
      label: key === "" ? NOT_ASSIGNED_LABEL : flagshipLabel(key),
      count: group.length,
      rated: scores.length,
      averageValue: scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null,
    };
  });

  return stats.sort((a, b) => {
    if ((a.key === "") !== (b.key === "")) return a.key === "" ? 1 : -1;
    return b.count - a.count || a.label.localeCompare(b.label);
  });
}
