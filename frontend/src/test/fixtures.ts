import type { Initiative } from "../api/types";

export function make(over: Partial<Initiative> & { id: number; name: string }): Initiative {
  return {
    description: null,
    status: "Idea",
    date_start: null,
    date_delivery: null,
    value_score: null,
    solution_complexity_score: null,
    owner: null,
    solution_type: null,
    value_type: null,
    ...over,
  };
}

const etb = { id: 1, name: "Owner A", department: "Assets", category: "ETB" };
const it = { id: 2, name: "Owner B", department: "Innovation", category: "IT" };
const capex = { id: 1, name: "CAPEX delivery", description: null };

export const SAMPLE: Initiative[] = [
  make({ id: 1, name: "Alpha", description: "Automatisierung", status: "Idea", value_score: 8, solution_complexity_score: 3, owner: etb, value_type: capex, date_delivery: "2026-07-01T00:00:00" }),
  make({ id: 2, name: "Beta", status: "PoC", value_score: 5, solution_complexity_score: 5, owner: etb }),
  make({ id: 3, name: "Gamma", status: "Idea", value_score: null, solution_complexity_score: 7, owner: it }),
  make({ id: 4, name: "Delta", status: "Cancelled", owner: null }),
];
