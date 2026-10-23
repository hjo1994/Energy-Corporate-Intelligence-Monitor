import type { Initiative } from "../api/types";
import { IN_PROGRESS_STAGES, stageRank } from "./stage";

// Initiatives without an owner belong to no business unit.
export const NO_BUSINESS_UNIT = "__none__";
export const NO_BUSINESS_UNIT_LABEL = "No business unit";

export interface Filters {
  search: string;
  businessUnits: string[];
  stages: string[];
  flagships: string[];
}

export const EMPTY_FILTERS: Filters = { search: "", businessUnits: [], stages: [], flagships: [] };

export const businessUnitOf = (i: Initiative): string => i.owner?.category ?? NO_BUSINESS_UNIT;
export const flagshipOf = (i: Initiative): string | null => i.value_type?.name ?? null;

export function applyFilters(items: Initiative[], f: Filters): Initiative[] {
  const q = f.search.trim().toLowerCase();
  return items.filter(
    (i) =>
      (f.businessUnits.length === 0 || f.businessUnits.includes(businessUnitOf(i))) &&
      (f.stages.length === 0 || f.stages.includes(i.stage)) &&
      (f.flagships.length === 0 || f.flagships.includes(flagshipOf(i) ?? "")) &&
      (q === "" ||
        i.name.toLowerCase().includes(q) ||
        (i.description ?? "").toLowerCase().includes(q)),
  );
}

export function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

export function countBy(items: Initiative[], key: (i: Initiative) => string | null): Map<string, number> {
  const out = new Map<string, number>();
  for (const i of items) {
    const k = key(i);
    if (k !== null) out.set(k, (out.get(k) ?? 0) + 1);
  }
  return out;
}

export function businessUnitsIn(items: Initiative[]): string[] {
  const units = [...countBy(items, businessUnitOf).keys()];
  return units.sort((a, b) =>
    a === NO_BUSINESS_UNIT ? 1 : b === NO_BUSINESS_UNIT ? -1 : a.localeCompare(b),
  );
}

export const stagesIn = (items: Initiative[]): string[] =>
  [...countBy(items, (i) => i.stage).keys()].sort((a, b) => stageRank(a) - stageRank(b));

export const flagshipsIn = (items: Initiative[]): string[] =>
  [...countBy(items, flagshipOf).keys()].sort((a, b) => a.localeCompare(b));

export type SortKey = "name" | "owner" | "stage" | "effort" | "potential" | "risk" | "delivery";

const sortValue: Record<SortKey, (i: Initiative) => string | number | null> = {
  name: (i) => i.name.toLowerCase(),
  owner: (i) => i.owner?.name.toLowerCase() ?? null,
  stage: (i) => stageRank(i.stage),
  effort: (i) => i.solution_complexity_score,
  potential: (i) => i.potential_value_eur,
  risk: (i) => i.risk_classification?.id ?? null,
  delivery: (i) => i.date_delivery,
};

// Missing values always sort last, in both directions.
export function sortInitiatives(items: Initiative[], key: SortKey, dir: "asc" | "desc"): Initiative[] {
  const get = sortValue[key];
  const sign = dir === "asc" ? 1 : -1;
  return [...items].sort((a, b) => {
    const va = get(a);
    const vb = get(b);
    if (va === null && vb === null) return a.id - b.id;
    if (va === null) return 1;
    if (vb === null) return -1;
    if (va < vb) return -sign;
    if (va > vb) return sign;
    return a.id - b.id;
  });
}

// Risk levels from which the Rahmenbetriebsvereinbarung KI requires the works council's involvement.
export const ELEVATED_RISK_FROM = 3;

export function summarize(items: Initiative[]) {
  const estimated = items.filter((i) => i.potential_value_eur !== null);
  const costed = items.filter((i) => i.annual_cost_eur !== null);
  return {
    total: items.length,
    inProgress: items.filter((i) => IN_PROGRESS_STAGES.includes(i.stage)).length,
    withPotential: estimated.length,
    totalPotential: estimated.length
      ? estimated.reduce((sum, i) => sum + (i.potential_value_eur as number), 0)
      : null,
    totalAnnualCost: costed.length
      ? costed.reduce((sum, i) => sum + (i.annual_cost_eur as number), 0)
      : null,
    elevatedRisk: items.filter((i) => (i.risk_classification?.id ?? 0) >= ELEVATED_RISK_FROM).length,
  };
}
