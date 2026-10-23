export interface Owner {
  id: number;
  name: string;
  department: string | null;
  category: string | null; // business unit
}

export interface TypeRef {
  id: number;
  name: string;
  description: string | null;
}

export interface RiskRef {
  id: number; // level 1-5 of the Rahmenbetriebsvereinbarung KI
  name: string;
}

// All money values are heuristic estimates in EUR (value and operating costs per year).
export interface Initiative {
  id: number;
  name: string;
  description: string | null;
  stage: string;
  date_start: string | null;
  date_delivery: string | null;
  efficiency_score_eur: number | null;
  quality_score_eur: number | null;
  risk_reduction_score_eur: number | null;
  strategic_value_score_eur: number | null;
  confidence_score: number | null;
  delivery_score: number | null;
  solution_complexity_score: number | null;
  one_time_costs: number | null;
  operating_costs: number | null;
  depreciation_years: number | null;
  /** sum of the four value buckets */
  hypothetical_value_eur: number | null;
  /** hypothetical value x confidence x delivery — the "value" used across the dashboard */
  potential_value_eur: number | null;
  /** one-time costs / depreciation years + operating costs */
  annual_cost_eur: number | null;
  owner: Owner | null;
  solution_type: TypeRef | null;
  value_type: TypeRef | null;
  risk_classification: RiskRef | null;
}

export interface InitiativePage {
  items: Initiative[];
  total: number;
  limit: number;
  offset: number;
}
