export interface Owner {
  id: number;
  name: string;
  department: string | null;
  category: string | null; // business unit
  email?: string | null;
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
  /** expected running costs per year (weighted by delivery) */
  running_costs?: number | null;
  /** deprecated alias of running_costs */
  operating_costs: number | null;
  depreciation_years: number | null;
  /** sum of the four value buckets */
  hypothetical_value_eur: number | null;
  /** hypothetical value x confidence x delivery — the "value" used across the dashboard */
  potential_value_eur: number | null;
  /** one-time costs / depreciation years + operating costs */
  annual_cost_eur: number | null;
  /** gold RealizedValue: measured benefits − actual costs, or runtime-based after delivery */
  realized_value_eur?: number | null;
  owner: Owner | null;
  lead?: Owner | null;
  ai_layer?: string | null;
  /** null for use cases imported from the Excel sheet */
  approval_status?: ApprovalStatus | null;
  /** one date per stage gate: up to today = passed, later = planned */
  needs_gate_date?: string | null;
  scope_gate_date?: string | null;
  deploy_gate_date?: string | null;
  retire_gate_date?: string | null;
  /** the latest gate passed by today */
  last_gate?: Stagegate | null;
  use_case_id?: number | null;
  version_id?: number | null;
  /**
   * how far the pipeline has got: "pending" (new idea, not in silver yet), "changes_pending"
   * (edits not processed yet), "not_assessed" (in silver, not complete for gold), "assessed"
   */
  processing?: Processing;
  /** potential value and risk level are previews, not gold values yet */
  provisional?: boolean;
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

export type Processing = "pending" | "changes_pending" | "not_assessed" | "assessed";
export type ApprovalStatus = "pending" | "approved" | "rejected";
export type Stagegate = "Needs" | "Scope" | "Deploy" | "Retire";
export type RunningCostRange = "up_to_10k" | "10k_to_50k" | "50k_to_100k" | "over_100k";

/** Body of POST /api/initiatives — form 1, a new AI idea (shares as fractions 0–1). */
export interface InitiativeInput {
  name: string;
  description: string;
  owner_id: number;
  value_type_id: number;
  ai_layer: string;
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
  running_cost_range: RunningCostRange;
  employee_personal_data: "no" | "pseudonymised" | "yes";
  performance_or_behaviour_control: boolean;
  decisions_on_employees: "none" | "prepares" | "automated";
  profiling_of_individuals: boolean;
  changes_employee_workflows: boolean;
  prohibited_practice: boolean;
  /** YYYY-MM-DD; which ones are needed depends on the stage */
  needs_gate_date?: string | null;
  scope_gate_date?: string | null;
  deploy_gate_date?: string | null;
  retire_gate_date?: string | null;
}

export interface InitiativePage {
  items: Initiative[];
  total: number;
  limit: number;
  offset: number;
}

// ---------- lifecycle: my use cases, approvals, form 2 ----------

export interface Form2Progress {
  filled: number;
  total: number;
}

export type Todo = "revise_and_resubmit" | "complete_details";

/** GET /api/use-cases/{id}: forms 1 and 2, gold values and what the signed-in user may do. */
export interface UseCaseDetail extends Initiative {
  comment: string | null;
  measured_benefits: number | null;
  actual_costs: number | null;
  running_cost_range: RunningCostRange | null;
  employee_personal_data: string | null;
  performance_or_behaviour_control: boolean | null;
  decisions_on_employees: string | null;
  profiling_of_individuals: boolean | null;
  changes_employee_workflows: boolean | null;
  prohibited_practice: boolean | null;
  enabling_team: string | null;
  complexity_solidity: string | null;
  strategic_kpis: string | null;
  tactical_kpis: string | null;
  value_domain: string | null;
  autonomy_level: string | null;
  eu_ai_act_class: string | null;
  eu_ai_act_role: string | null;
  works_council_risk_class: string | null;
  target_user_groups: string | null;
  /** comma-separated */
  applicable_to: string | null;
  capability_direction: string | null;
  safety_component: boolean | null;
  works_council_approved_at: string | null;
  expected_users: number | null;
  drivers: Record<string, unknown>;
  submitted_by: string | null;
  submitted_at: string | null;
  changed_by: string | null;
  updated_at: string | null;
  assessed_version_id: number | null;
  assessed_at: string | null;
  pending_action_ids: number[];
  /** send back as base_revision when saving */
  revision: string;
  form2_progress: Form2Progress;
  /** what does not fit between stage and gate dates */
  stage_problems: string[];
  /** the stage given in form 1; the stage cannot go below it */
  stage_floor?: string | null;
  todos: Todo[];
  can_edit: boolean;
  can_decide: boolean;
}

export interface MyUseCase {
  id: number;
  name: string;
  approval_status: ApprovalStatus | null;
  stage: string | null;
  needs_gate_date: string | null;
  scope_gate_date: string | null;
  deploy_gate_date: string | null;
  retire_gate_date: string | null;
  last_gate: Stagegate | null;
  stage_problems?: string[];
  comment: string | null;
  potential_value_eur: number | null;
  risk_classification: RiskRef | null;
  processing: Processing;
  provisional: boolean;
  form2_progress: Form2Progress;
  roles: ("submitter" | "owner" | "lead")[];
  todos: Todo[];
  updated_at: string | null;
  can_edit: boolean;
}

export interface ApprovalItem {
  id: number;
  name: string;
  description: string | null;
  owner: Owner | null;
  value_type: TypeRef | null;
  ai_layer: string | null;
  submitted_by: string | null;
  submitted_at: string | null;
  potential_value_eur: number | null;
  hypothetical_value_eur: number | null;
  annual_cost_eur: number | null;
  solution_complexity_score: number | null;
  risk_classification: RiskRef | null;
  processing: Processing;
  can_decide: boolean;
}

export interface SimilarUseCase {
  id: number;
  name: string;
  stage: string | null;
  owner: Owner | null;
  score: number;
}

/** PATCH /api/use-cases/{id}: only the fields sent count. */
export type UseCasePatch = { base_revision: string; resubmit?: boolean } & Partial<Record<string, unknown>>;

export interface DecisionInput {
  decision: "approve" | "reject";
  lead_id?: number;
  comment?: string;
  base_revision?: string;
}

export interface Option {
  value: string;
  label: string;
}

/** GET /api/form-options */
export interface FormOptions {
  stages?: Option[];
  /** maturity order of the stages; On hold, Cancelled and Unknown stand outside it */
  stage_order?: string[];
  /** stage -> gates that must be passed / must not be passed yet */
  stage_gate_rules?: Record<string, { passed: Stagegate[]; not_passed: Stagegate[] }>;
  /** form 1: the values each number can take */
  value_domains?: Record<string, { value: number; label: string }[]>;
  ai_layers: Option[];
  running_cost_ranges: (Option & { amount: number })[];
  enabling_teams: Option[];
  complexity_solidities: Option[];
  eu_ai_act_classes: Option[];
  eu_ai_act_roles: Option[];
  works_council_risk_classes: Option[];
  capability_directions: Option[];
  applicable_to: Option[];
}

export interface Rights {
  canApprove: boolean;
  canAdmin: boolean;
  /** may switch to approver rights for a demo (AI_COCKPIT_DEMO_PRESENTERS) */
  demoPresenter?: boolean;
  /** this session runs with the demo approver rights */
  demoApprover?: boolean;
}
