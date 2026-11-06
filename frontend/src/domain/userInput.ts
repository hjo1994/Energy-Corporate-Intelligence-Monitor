import type { InitiativeInput, RunningCostRange } from "../api/types";
import { STAGE_GATE_RULES, gateProblems, todayIso, type GateRules } from "./lifecycle";

// The input form's live preview. Binding are the values the pipeline computes
// (input orchestration, transforms/user_input_heuristic.py); these formulas mirror it and are
// checked against the same cases (backend/tests/fixtures/user_input_cases.json).

export const HOURLY_RATE_EUR = 60;
export const DEPRECIATION_YEARS = 5;
export const CONFIDENCE_SCORE = { rough: 0.35, benchmark: 0.6, measured: 0.8 } as const;
export const DELIVERY_SCORE = { low: 0.4, medium: 0.65, high: 0.9 } as const;

/** Running costs are asked as a range; the pipeline counts this amount per range (same as the backend). */
export const RUNNING_COST_RANGES: { value: RunningCostRange; label: string; amount: number }[] = [
  { value: "up_to_10k", label: "up to 10k € / year", amount: 5_000 },
  { value: "10k_to_50k", label: "10k–50k € / year", amount: 30_000 },
  { value: "50k_to_100k", label: "50k–100k € / year", amount: 75_000 },
  { value: "over_100k", label: "more than 100k € / year", amount: 150_000 },
];
export const runningCostAmount = (range: RunningCostRange | "" | null | undefined): number =>
  RUNNING_COST_RANGES.find((r) => r.value === range)?.amount ?? 0;
export const runningCostLabel = (range: string | null | undefined): string | undefined =>
  RUNNING_COST_RANGES.find((r) => r.value === range)?.label;

export const AI_LAYERS = [
  "AI for productivity and efficiency",
  "AI for business process optimization",
  "Operational and advanced AI",
];

/** Idea and Exploration are one stage since 11/2026: Ideation, the stage form 1 starts with. */
export const DEFAULT_STAGE = "Ideation";
export const STAGES = ["Ideation", "PoC", "MVP", "Implementation", "Production", "Retired", "On hold", "Cancelled", "Unknown"];

// ---------- value domains: every number of form 1 is chosen from a short list ----------

export interface DomainOption {
  /** the value that is stored (the range's representative value) */
  value: number;
  label: string;
}

export type DomainField =
  | "cases_per_year"
  | "hours_saved_per_case"
  | "error_rate_before"
  | "errors_avoided"
  | "cost_per_error"
  | "risk_events_per_year"
  | "events_avoided"
  | "cost_per_event"
  | "delay_events_per_year"
  | "cost_of_delay_per_event"
  | "lead_time_saved"
  | "one_time_costs";

const SHARES: DomainOption[] = [
  { value: 0.1, label: "about 10 %" },
  { value: 0.25, label: "about 25 %" },
  { value: 0.5, label: "about 50 %" },
  { value: 0.75, label: "about 75 %" },
  { value: 0.9, label: "about 90 %" },
];
const EVENT_COSTS: DomainOption[] = [
  { value: 5_000, label: "under 10k €" },
  { value: 30_000, label: "10k–50k €" },
  { value: 150_000, label: "50k–250k €" },
  { value: 500_000, label: "over 250k €" },
];

/** Same as the backend (app/lifecycle.py, served in /api/form-options as value_domains); used until that has loaded. */
export const VALUE_DOMAINS: Record<DomainField, DomainOption[]> = {
  cases_per_year: [
    { value: 50, label: "under 100" },
    { value: 500, label: "100–1,000" },
    { value: 5_000, label: "1,000–10,000" },
    { value: 50_000, label: "10,000–100,000" },
    { value: 150_000, label: "over 100,000" },
  ],
  hours_saved_per_case: [
    { value: 0.1, label: "under 15 min" },
    { value: 0.4, label: "15–30 min" },
    { value: 0.75, label: "30–60 min" },
    { value: 2.5, label: "1–4 h" },
    { value: 6, label: "over 4 h" },
  ],
  error_rate_before: [
    { value: 0.01, label: "under 2 %" },
    { value: 0.035, label: "2–5 %" },
    { value: 0.075, label: "5–10 %" },
    { value: 0.15, label: "10–20 %" },
    { value: 0.3, label: "over 20 %" },
  ],
  errors_avoided: SHARES,
  cost_per_error: [
    { value: 50, label: "under 100 €" },
    { value: 500, label: "100–1k €" },
    { value: 5_000, label: "1k–10k €" },
    { value: 25_000, label: "over 10k €" },
  ],
  risk_events_per_year: [
    { value: 0.5, label: "less than 1" },
    { value: 3, label: "1–5" },
    { value: 12, label: "5–20" },
    { value: 40, label: "more than 20" },
  ],
  events_avoided: SHARES,
  cost_per_event: EVENT_COSTS,
  delay_events_per_year: [
    { value: 3, label: "under 5" },
    { value: 12, label: "5–20" },
    { value: 60, label: "20–100" },
    { value: 150, label: "over 100" },
  ],
  cost_of_delay_per_event: EVENT_COSTS,
  lead_time_saved: SHARES,
  one_time_costs: [
    { value: 25_000, label: "under 50k €" },
    { value: 75_000, label: "50k–100k €" },
    { value: 175_000, label: "100k–250k €" },
    { value: 500_000, label: "250k €–1M €" },
    { value: 1_500_000, label: "over 1M €" },
  ],
};

/** The option a value belongs to: the exact one, else the nearest (for values entered before the domains). */
export function domainOption(domain: DomainOption[], value: number | null | undefined): DomainOption | undefined {
  if (value === null || value === undefined || domain.length === 0) return undefined;
  const exact = domain.find((o) => Math.abs(o.value - value) < 1e-9);
  if (exact) return exact;
  return domain.reduce((best, o) => (Math.abs(Math.log((o.value || 1e-9) / (value || 1e-9))) < Math.abs(Math.log((best.value || 1e-9) / (value || 1e-9))) ? o : best));
}

export const inDomain = (domain: DomainOption[], value: number | null) =>
  value !== null && domain.some((o) => Math.abs(o.value - value) < 1e-9);

export type LeverKey = "efficiency" | "quality" | "riskReduction" | "speed";

export const LEVERS: { key: LeverKey; label: string; fields: (keyof InitiativeInput)[] }[] = [
  { key: "efficiency", label: "Efficiency", fields: ["cases_per_year", "hours_saved_per_case"] },
  { key: "quality", label: "Quality", fields: ["cases_per_year", "error_rate_before", "errors_avoided", "cost_per_error"] },
  { key: "riskReduction", label: "Risk reduction", fields: ["risk_events_per_year", "events_avoided", "cost_per_event"] },
  { key: "speed", label: "Speed", fields: ["delay_events_per_year", "cost_of_delay_per_event", "lead_time_saved"] },
];

type Drivers = Pick<
  InitiativeInput,
  | "cases_per_year"
  | "hours_saved_per_case"
  | "error_rate_before"
  | "errors_avoided"
  | "cost_per_error"
  | "risk_events_per_year"
  | "events_avoided"
  | "cost_per_event"
  | "delay_events_per_year"
  | "cost_of_delay_per_event"
  | "lead_time_saved"
  | "estimate_basis"
  | "delivery_likelihood"
  | "one_time_costs"
> & {
  /** running costs per year as entered: the amount the pipeline counts for the chosen range */
  operating_costs: number;
};

const product = (values: (number | null)[], factor = 1): number =>
  values.some((v) => v === null) ? 0 : values.reduce<number>((a, v) => a * (v as number), factor);

export interface Preview {
  buckets: Record<LeverKey, number>;
  hypothetical: number;
  confidence: number;
  delivery: number;
  potential: number;
  oneTimeCosts: number;
  operatingCosts: number;
  annualCost: number;
  net: number;
}

export function previewValue(d: Drivers): Preview {
  const buckets = {
    efficiency: product([d.cases_per_year, d.hours_saved_per_case], HOURLY_RATE_EUR),
    quality: product([d.cases_per_year, d.error_rate_before, d.errors_avoided, d.cost_per_error]),
    riskReduction: product([d.risk_events_per_year, d.events_avoided, d.cost_per_event]),
    speed: product([d.delay_events_per_year, d.cost_of_delay_per_event, d.lead_time_saved]),
  };
  const hypothetical = buckets.efficiency + buckets.quality + buckets.riskReduction + buckets.speed;
  const confidence = CONFIDENCE_SCORE[d.estimate_basis];
  const delivery = DELIVERY_SCORE[d.delivery_likelihood];
  const potential = hypothetical * confidence * delivery;
  // expected costs, like the stored silver costs
  const oneTimeCosts = d.one_time_costs * delivery;
  const operatingCosts = d.operating_costs * delivery;
  const annualCost = oneTimeCosts / DEPRECIATION_YEARS + operatingCosts;
  return { buckets, hypothetical, confidence, delivery, potential, oneTimeCosts, operatingCosts, annualCost, net: potential - annualCost };
}

type Indicators = Pick<
  InitiativeInput,
  | "employee_personal_data"
  | "performance_or_behaviour_control"
  | "decisions_on_employees"
  | "profiling_of_individuals"
  | "changes_employee_workflows"
  | "prohibited_practice"
>;

/** Risk level 1–5 (Rahmenbetriebsvereinbarung KI), first matching rule wins. */
export function previewRiskLevel(r: Indicators): number {
  if (r.prohibited_practice) return 5;
  if (r.decisions_on_employees === "automated" || r.profiling_of_individuals) return 4;
  if (r.employee_personal_data === "yes" || r.performance_or_behaviour_control || r.decisions_on_employees === "prepares") return 3;
  if (r.employee_personal_data === "pseudonymised" || r.changes_employee_workflows) return 2;
  return 1;
}

// ---------- form state ----------

/** Numbers are chosen from their domain and kept as the option's value in text ("" = not chosen). */
export interface FormState {
  name: string;
  description: string;
  /** the AppUser ID of the user chosen as owner; "" = the signed-in user (not sent) */
  ownerUserId: string;
  /** asked only while the owner's user has no owner row yet; else the owner's (shown, not sent) */
  businessUnit: string;
  valueTypeId: string;
  aiLayer: string;
  stage: string;
  dateStart: string;
  dateDelivery: string;
  /** stage gate dates as YYYY-MM-DD; asked depending on the stage */
  gateDates: Record<"Needs" | "Scope" | "Deploy" | "Retire", string>;
  levers: Record<LeverKey, boolean>;
  casesPerYear: string;
  hoursSavedPerCase: string;
  errorRateBefore: string;
  errorsAvoided: string;
  costPerError: string;
  riskEventsPerYear: string;
  eventsAvoided: string;
  costPerEvent: string;
  delayEventsPerYear: string;
  costOfDelayPerEvent: string;
  leadTimeSaved: string;
  estimateBasis: InitiativeInput["estimate_basis"];
  deliveryLikelihood: InitiativeInput["delivery_likelihood"];
  complexity: string;
  oneTimeCosts: string;
  runningCostRange: RunningCostRange | "";
  employeePersonalData: InitiativeInput["employee_personal_data"];
  performanceOrBehaviourControl: boolean;
  decisionsOnEmployees: InitiativeInput["decisions_on_employees"];
  profilingOfIndividuals: boolean;
  changesEmployeeWorkflows: boolean;
  prohibitedPractice: boolean;
}

export const EMPTY_FORM: FormState = {
  name: "",
  description: "",
  ownerUserId: "",
  businessUnit: "",
  valueTypeId: "",
  aiLayer: "",
  stage: DEFAULT_STAGE,
  dateStart: "",
  dateDelivery: "",
  gateDates: { Needs: "", Scope: "", Deploy: "", Retire: "" },
  levers: { efficiency: true, quality: false, riskReduction: false, speed: false },
  casesPerYear: "",
  hoursSavedPerCase: "",
  errorRateBefore: "",
  errorsAvoided: "",
  costPerError: "",
  riskEventsPerYear: "",
  eventsAvoided: "",
  costPerEvent: "",
  delayEventsPerYear: "",
  costOfDelayPerEvent: "",
  leadTimeSaved: "",
  estimateBasis: "rough",
  deliveryLikelihood: "medium",
  complexity: "",
  oneTimeCosts: "",
  runningCostRange: "",
  employeePersonalData: "no",
  performanceOrBehaviourControl: false,
  decisionsOnEmployees: "none",
  profilingOfIndividuals: false,
  changesEmployeeWorkflows: false,
  prohibitedPractice: false,
};

/** "3,000" / "3000" / "0.5" -> number; empty or invalid -> null. */
export function parseNumber(text: string): number | null {
  const t = text.replace(/[,\s]/g, "");
  if (t === "" || !/^\d+(\.\d+)?$/.test(t)) return null;
  return Number(t);
}

/** The preview's inputs: the body plus the amount counted for the running cost range. */
export const previewInput = (body: InitiativeInput) => ({ ...body, operating_costs: runningCostAmount(body.running_cost_range) });

/** The request body; drivers of switched-off levers are left out (null). */
export function toInput(f: FormState): InitiativeInput {
  const on = f.levers;
  const when = (cond: boolean, v: number | null) => (cond ? v : null);
  return {
    name: f.name.trim(),
    description: f.description.trim(),
    owner_user_id: f.ownerUserId ? Number(f.ownerUserId) : null,
    business_unit: f.businessUnit || null,
    value_type_id: Number(f.valueTypeId),
    ai_layer: f.aiLayer,
    stage: f.stage,
    date_start: f.dateStart || null,
    date_delivery: f.dateDelivery || null,
    cases_per_year: when(on.efficiency || on.quality, parseNumber(f.casesPerYear)),
    hours_saved_per_case: when(on.efficiency, parseNumber(f.hoursSavedPerCase)),
    error_rate_before: when(on.quality, parseNumber(f.errorRateBefore)),
    errors_avoided: when(on.quality, parseNumber(f.errorsAvoided)),
    cost_per_error: when(on.quality, parseNumber(f.costPerError)),
    risk_events_per_year: when(on.riskReduction, parseNumber(f.riskEventsPerYear)),
    events_avoided: when(on.riskReduction, parseNumber(f.eventsAvoided)),
    cost_per_event: when(on.riskReduction, parseNumber(f.costPerEvent)),
    delay_events_per_year: when(on.speed, parseNumber(f.delayEventsPerYear)),
    cost_of_delay_per_event: when(on.speed, parseNumber(f.costOfDelayPerEvent)),
    lead_time_saved: when(on.speed, parseNumber(f.leadTimeSaved)),
    estimate_basis: f.estimateBasis,
    delivery_likelihood: f.deliveryLikelihood,
    solution_complexity_score: Number(f.complexity),
    one_time_costs: parseNumber(f.oneTimeCosts) ?? 0,
    needs_gate_date: f.gateDates.Needs || null,
    scope_gate_date: f.gateDates.Scope || null,
    deploy_gate_date: f.gateDates.Deploy || null,
    retire_gate_date: f.gateDates.Retire || null,
    running_cost_range: f.runningCostRange as RunningCostRange,
    employee_personal_data: f.employeePersonalData,
    performance_or_behaviour_control: f.performanceOrBehaviourControl,
    decisions_on_employees: f.decisionsOnEmployees,
    profiling_of_individuals: f.profilingOfIndividuals,
    changes_employee_workflows: f.changesEmployeeWorkflows,
    prohibited_practice: f.prohibitedPractice,
  };
}

/** Form field of each number of form 1. */
export const DOMAIN_FORM_FIELDS: Record<DomainField, keyof FormState> = {
  cases_per_year: "casesPerYear",
  hours_saved_per_case: "hoursSavedPerCase",
  error_rate_before: "errorRateBefore",
  errors_avoided: "errorsAvoided",
  cost_per_error: "costPerError",
  risk_events_per_year: "riskEventsPerYear",
  events_avoided: "eventsAvoided",
  cost_per_event: "costPerEvent",
  delay_events_per_year: "delayEventsPerYear",
  cost_of_delay_per_event: "costOfDelayPerEvent",
  lead_time_saved: "leadTimeSaved",
  one_time_costs: "oneTimeCosts",
};

export type FormErrors = Partial<Record<keyof FormState | "levers" | `gate${"Needs" | "Scope" | "Deploy" | "Retire"}`, string>>;

/** Field -> message; empty when the form can be submitted. Same rules as the API. */
export function validate(
  f: FormState,
  domains: Record<DomainField, DomainOption[]> = VALUE_DOMAINS,
  today: string = todayIso(),
  rules: GateRules = STAGE_GATE_RULES,
): FormErrors {
  const errors: FormErrors = {};
  const required: [keyof FormState, string][] = [
    ["name", "Enter a name."],
    ["description", "Describe the idea."],
    ["businessUnit", "Choose a business unit."],
    ["valueTypeId", "Choose a topic."],
    ["aiLayer", "Choose the AI layer."],
    ["runningCostRange", "Choose a range."],
    ["stage", "Choose a stage."],
    ["complexity", "Choose the complexity."],
  ];
  for (const [field, message] of required) if (!String(f[field]).trim()) errors[field] = message;

  const input = toInput(f);
  for (const [field, key] of Object.entries(DOMAIN_FORM_FIELDS) as [DomainField, keyof FormState][]) {
    const value = input[field as keyof InitiativeInput] as number | null;
    const used = field === "one_time_costs" || isLeverFieldOn(f, field);
    if (used && String(f[key]).trim() && !inDomain(domains[field] ?? [], value)) errors[key] = "Choose one of the ranges.";
  }
  if (!f.oneTimeCosts.trim()) errors.oneTimeCosts = "Choose a range.";
  const complete = LEVERS.some((l) => f.levers[l.key] && l.fields.every((field) => input[field] !== null));
  if (!complete) errors.levers = "Fill in all drivers of at least one value lever.";

  // form 1 asks when the needs gate was passed: the idea starts between the needs and the scope gate
  if (!f.gateDates.Needs) errors.gateNeeds = "Enter the date the needs gate was passed.";
  else if (f.gateDates.Needs > today) errors.gateNeeds = "The needs gate date cannot be in the future.";
  for (const p of gateProblems(f.stage, f.gateDates, today, rules)) errors[`gate${p.gate}`] ??= p.message;
  return errors;
}

function isLeverFieldOn(f: FormState, field: string): boolean {
  return LEVERS.some((l) => f.levers[l.key] && (l.fields as string[]).includes(field));
}

/** Quarters offered for start and delivery: from two years back to four years ahead. */
export function quarterOptions(today: Date = new Date()): string[] {
  const out: string[] = [];
  for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 4; y++) for (let q = 1; q <= 4; q++) out.push(`Q${q} ${y}`);
  return out;
}

// ---------- hints: the defaults the free-text heuristic uses ----------

/** Form 1 asks for the AI layer; the solution type follows in form 2. Its typical family for the hints: */
const FAMILY_BY_AI_LAYER: Record<string, "assistant" | "genai_process" | "ml"> = {
  "AI for productivity and efficiency": "assistant",
  "AI for business process optimization": "genai_process",
  "Operational and advanced AI": "ml",
};

const FAMILY_BY_SOLUTION_TYPE: Record<string, "assistant" | "rpa" | "genai_process" | "ml"> = {
  Copilot: "assistant",
  "General chatbot": "assistant",
  "Github co-pilot": "assistant",
  "Custom chatbot": "assistant",
  "Rule based automation on cloud": "rpa",
  "Rule based automation on prem": "rpa",
  "Custom LLM integration": "genai_process",
  "Custom agent": "genai_process",
  "Copilot agent": "genai_process",
  "Custom AI/ML integration": "ml",
  "Custom AI/ML model": "ml",
};
const HOURS_SAVED = { assistant: 0.25, rpa: 0.5, genai_process: 1, ml: 0.5 };
const ERROR_CUT = { assistant: 25, rpa: 60, genai_process: 40, ml: 50 };
const P_EVENT_CUT = { assistant: 10, rpa: 40, genai_process: 20, ml: 30 };
const SPEEDUP = { assistant: 5, rpa: 10, genai_process: 15, ml: 10 };
const COST_ERROR: Record<string, number> = {
  "CAPEX delivery": 2000, "Grid planning process": 2000, "System Operations process": 1500,
  "Connection lifecycle": 1000, "Corporate processes": 300, "Software Development lifecycle": 500,
};
const COST_EVENT: Record<string, number> = {
  "System Operations process": 100_000, "CAPEX delivery": 50_000, "Grid planning process": 50_000,
  "Connection lifecycle": 20_000, "Corporate processes": 20_000, "Software Development lifecycle": 10_000,
};
const COST_DELAY: Record<string, number> = {
  "CAPEX delivery": 100_000, "Grid planning process": 100_000, "Connection lifecycle": 50_000,
  "System Operations process": 50_000, "Corporate processes": 20_000, "Software Development lifecycle": 20_000,
};

export interface Typical {
  hoursSavedPerCase?: number;
  /** shares as fractions 0–1 */
  errorRateBefore: number;
  errorsAvoided?: number;
  costPerError: number;
  eventsAvoided?: number;
  costPerEvent: number;
  costOfDelayPerEvent: number;
  leadTimeSaved?: number;
}

const share = (pct: number | undefined) => (pct === undefined ? undefined : pct / 100);

/** Typical values for the chosen solution type (or AI layer) and flagship, shown as hints (never filled in). */
export function typicalValues(solutionTypeOrLayer: string | undefined, flagship: string | undefined): Typical {
  const family = solutionTypeOrLayer
    ? FAMILY_BY_SOLUTION_TYPE[solutionTypeOrLayer] ?? FAMILY_BY_AI_LAYER[solutionTypeOrLayer]
    : undefined;
  const fl = flagship ?? "";
  return {
    hoursSavedPerCase: family && HOURS_SAVED[family],
    errorRateBefore: 0.08,
    errorsAvoided: share(family && ERROR_CUT[family]),
    costPerError: COST_ERROR[fl] ?? 500,
    eventsAvoided: share(family && P_EVENT_CUT[family]),
    costPerEvent: COST_EVENT[fl] ?? 20_000,
    costOfDelayPerEvent: COST_DELAY[fl] ?? 20_000,
    leadTimeSaved: share(family && SPEEDUP[family]),
  };
}
