import type { Initiative } from "../api/types";

export function make(over: Partial<Initiative> & { id: number; name: string }): Initiative {
  return {
    description: null,
    stage: "Idea",
    date_start: null,
    date_delivery: null,
    efficiency_score_eur: null,
    quality_score_eur: null,
    risk_reduction_score_eur: null,
    strategic_value_score_eur: null,
    confidence_score: null,
    delivery_score: null,
    solution_complexity_score: null,
    one_time_costs: null,
    operating_costs: null,
    depreciation_years: null,
    hypothetical_value_eur: null,
    potential_value_eur: null,
    annual_cost_eur: null,
    owner: null,
    solution_type: null,
    value_type: null,
    risk_classification: null,
    ...over,
  };
}

const etb = { id: 1, name: "Owner A", department: "Assets", category: "ETB" };
const it = { id: 2, name: "Owner B", department: "Innovation", category: "IT" };
const capex = { id: 1, name: "CAPEX delivery", description: null };
const low = { id: 1, name: "Sehr geringes Risiko" };
const medium = { id: 3, name: "Mittleres Risiko" };

export const SAMPLE: Initiative[] = [
  make({
    id: 1, name: "Alpha", description: "Automatisierung", stage: "Idea",
    efficiency_score_eur: 40000, quality_score_eur: 30000, risk_reduction_score_eur: 20000, strategic_value_score_eur: 10000,
    confidence_score: 0.6, delivery_score: 0.9, hypothetical_value_eur: 100000, potential_value_eur: 54000,
    one_time_costs: 75000, operating_costs: 19000, depreciation_years: 3, annual_cost_eur: 44000,
    solution_complexity_score: 3, owner: etb, value_type: capex, risk_classification: medium,
    date_delivery: "2026-07-01T00:00:00",
  }),
  make({ id: 2, name: "Beta", stage: "PoC", potential_value_eur: 4550, annual_cost_eur: 17500, solution_complexity_score: 5, owner: etb, risk_classification: low }),
  make({ id: 3, name: "Gamma", stage: "Idea", potential_value_eur: 20000, solution_complexity_score: null, owner: it, risk_classification: low }),
  make({ id: 4, name: "Delta", stage: "Cancelled", owner: null, risk_classification: low }),
];
