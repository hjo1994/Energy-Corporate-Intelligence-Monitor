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
  /** always true here: the backend hides initiatives no longer in their source sheet */
  is_active: boolean;
  /**
   * "pending": entered through the input form, not yet processed by the pipeline — the values are
   * provisional and `id` is negative (−user_input_id)
   */
  status?: "active" | "inactive" | "pending";
  user_input_id?: number | null;
  /** lineage: BusinessTransaction pointing to the bronze record this initiative was last built from (null while pending) */
  business_transaction_id: number | null;
}

/** Body of POST /api/initiatives (shares as fractions 0–1). */
export interface InitiativeInput {
  name: string;
  description: string;
  owner_id: number;
  value_type_id: number;
  solution_type_id: number;
  stage: string;
  date_start: string | null;
  date_delivery: string | null;
  cases_per_year: number | null;
  hours_saved_per_case: number | null;
  error_rate_before: number | null;
  errors_avoided: number | null;
  cost_per_error: number | null;
  risk_events_per_year: number | null;
  events_avoided: number | null;
  cost_per_event: number | null;
  delay_events_per_year: number | null;
  cost_of_delay_per_event: number | null;
  lead_time_saved: number | null;
  estimate_basis: "rough" | "benchmark" | "measured";
  delivery_likelihood: "low" | "medium" | "high";
  solution_complexity_score: number;
  one_time_costs: number;
  operating_costs: number;
  employee_personal_data: "no" | "pseudonymised" | "yes";
  performance_or_behaviour_control: boolean;
  decisions_on_employees: "none" | "prepares" | "automated";
  profiling_of_individuals: boolean;
  changes_employee_workflows: boolean;
  prohibited_practice: boolean;
}

export interface InitiativePage {
  items: Initiative[];
  total: number;
  limit: number;
  offset: number;
}
