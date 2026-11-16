import type { Initiative } from "../api/types";

export const NO_DEPARTMENT_LABEL = "No department";

// The sheet spells departments freely ("Infra" / "INFRA", "GO‑C" with a non-breaking hyphen):
// they count as one when they only differ in case, hyphens or spaces.
export const departmentKey = (name: string): string =>
  name.trim().toLowerCase().replace(/[‐-―]/g, "-").replace(/\s+/g, " ");

export interface DepartmentGroup {
  /** "" for use cases without a department */
  key: string;
  /** the most frequent spelling */
  label: string;
  items: Initiative[];
}

/** Use cases grouped by their owner's department, biggest first; those without one come last. */
export function groupByDepartment(items: Initiative[]): DepartmentGroup[] {
  const groups = new Map<string, { items: Initiative[]; spellings: Map<string, number> }>();
  for (const i of items) {
    const name = i.owner?.department?.trim() ?? "";
    const key = name ? departmentKey(name) : "";
    let g = groups.get(key);
    if (!g) groups.set(key, (g = { items: [], spellings: new Map() }));
    g.items.push(i);
    if (name) g.spellings.set(name, (g.spellings.get(name) ?? 0) + 1);
  }
  const out = [...groups].map(([key, g]) => ({
    key,
    label: key === "" ? NO_DEPARTMENT_LABEL : [...g.spellings].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0][0],
    items: g.items,
  }));
  return out.sort((a, b) => {
    if ((a.key === "") !== (b.key === "")) return a.key === "" ? 1 : -1;
    return b.items.length - a.items.length || a.label.localeCompare(b.label);
  });
}

export const departmentCount = (items: Initiative[]): number => groupByDepartment(items).filter((g) => g.key !== "").length;
