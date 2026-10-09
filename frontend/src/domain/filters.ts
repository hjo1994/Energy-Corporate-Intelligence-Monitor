import type { Initiative } from "../api/types";
import { IN_PROGRESS_STATUSES, statusRank } from "./status";

// Initiatives without an owner belong to no business unit.
export const NO_BUSINESS_UNIT = "__none__";
export const NO_BUSINESS_UNIT_LABEL = "No business unit";

export interface Filters {
  search: string;
  businessUnits: string[];
  statuses: string[];
  flagships: string[];
}

export const EMPTY_FILTERS: Filters = {
  search: "",
  businessUnits: [],
  statuses: [],
  flagships: [],
};

export const businessUnitOf = (i: Initiative): string =>
  i.owner?.category ?? NO_BUSINESS_UNIT;

export const flagshipOf = (i: Initiative): string | null =>
  i.value_type?.name ?? null;

export function applyFilters(items: Initiative[], f: Filters): Initiative[] {
  const q = f.search.trim().toLowerCase();

  return items.filter(
    (i) =>
      (f.businessUnits.length === 0 ||
        f.businessUnits.includes(businessUnitOf(i))) &&
      (f.statuses.length === 0 ||
        f.statuses.includes(i.status)) &&
      (f.flagships.length === 0 ||
        f.flagships.includes(flagshipOf(i) ?? "")) &&
      (q === "" ||
        i.name.toLowerCase().includes(q) ||
        (i.description ?? "").toLowerCase().includes(q)),
  );
}

export function toggle(list: string[], value: string): string[] {
  return list.includes(value)
    ? list.filter((v) => v !== value)
    : [...list, value];
}

export function countBy(
  items: Initiative[],
  key: (i: Initiative) => string | null,
): Map<string, number> {
  const out = new Map<string, number>();

  for (const i of items) {
    const k = key(i);
    if (k !== null) {
      out.set(k, (out.get(k) ?? 0) + 1);
    }
  }

  return out;
}

export function businessUnitsIn(items: Initiative[]): string[] {
  const units = [...countBy(items, businessUnitOf).keys()];

  return units.sort((a, b) =>
    a === NO_BUSINESS_UNIT
      ? 1
      : b === NO_BUSINESS_UNIT
        ? -1
        : a.localeCompare(b),
  );
}

export const statusesIn = (items: Initiative[]): string[] =>
  [...countBy(items, (i) => i.status).keys()].sort(
    (a, b) => statusRank(a) - statusRank(b),
  );

export const flagshipsIn = (items: Initiative[]): string[] =>
  [...countBy(items, flagshipOf).keys()].sort((a, b) =>
    a.localeCompare(b),
  );

export type SortKey =
  | "name"
  | "owner"
  | "status"
  | "effort"
  | "value"
  | "delivery";

const sortValue: Record<
  SortKey,
  (i: Initiative) => string | number | null
> = {
  name: (i) => i.name.toLowerCase(),
  owner: (i) => i.owner?.name.toLowerCase() ?? null,
  status: (i) => statusRank(i.status),
  effort: (i) => i.solution_complexity_score,
  value: (i) => i.value_score,
  delivery: (i) => i.date_delivery,
};

// Missing values always sort last, in both directions.
export function sortInitiatives(
  items: Initiative[],
  key: SortKey,
  dir: "asc" | "desc",
): Initiative[] {
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

export function summarize(items: Initiative[]) {
  const scored = items.filter((i) => i.value_score !== null);

  return {
    total: items.length,
    inProgress: items.filter((i) =>
      IN_PROGRESS_STATUSES.includes(i.status),
    ).length,
    withValue: scored.length,
    withoutValue: items.length - scored.length,
    averageValue: scored.length
      ? scored.reduce(
          (sum, i) => sum + (i.value_score as number),
          0,
        ) / scored.length
      : null,
  };
}