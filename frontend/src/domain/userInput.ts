import type { InitiativeInput, RunningCostRange } from "../api/types";
import { STAGE_REQUIRES_GATE, stageGateError } from "./lifecycle";

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

export const STAGES = ["Idea", "Exploration", "PoC", "MVP", "Implementation", "Production", "On hold", "Cancelled", "Unknown"];
/** Stages a new idea can start in: the later ones need a gate passed first. */
export const NEW_IDEA_STAGES = STAGES.filter((s) => !STAGE_REQUIRES_GATE[s]);

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

/** Number inputs are kept as typed text; percentages are entered in % and sent as fractions. */
export interface FormState {
  name: string;
  description: string;
  businessUnit: string;
  ownerId: string;
  valueTypeId: string;
  aiLayer: string;
  stage: string;
  dateStart: string;
  dateDelivery: string;
  levers: Record<LeverKey, boolean>;
  casesPerYear: string;
  hoursSavedPerCase: string;
  errorRatePct: string;
  errorsAvoidedPct: string;
  costPerError: string;
  riskEventsPerYear: string;
  eventsAvoidedPct: string;
  costPerEvent: string;
  delayEventsPerYear: string;
  costOfDelayPerEvent: string;
  leadTimeSavedPct: string;
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
  businessUnit: "",
  ownerId: "",
  valueTypeId: "",
  aiLayer: "",
  stage: "",
  dateStart: "",
  dateDelivery: "",
  levers: { efficiency: true, quality: false, riskReduction: false, speed: false },
  casesPerYear: "",
  hoursSavedPerCase: "",
  errorRatePct: "",
  errorsAvoidedPct: "",
  costPerError: "",
  riskEventsPerYear: "",
  eventsAvoidedPct: "",
  costPerEvent: "",
  delayEventsPerYear: "",
  costOfDelayPerEvent: "",
  leadTimeSavedPct: "",
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

const pct = (text: string) => {
  const n = parseNumber(text);
  return n === null ? null : n / 100;
};

/** The preview's inputs: the body plus the amount counted for the running cost range. */
export const previewInput = (body: InitiativeInput) => ({ ...body, operating_costs: runningCostAmount(body.running_cost_range) });

/** The request body; drivers of switched-off levers are left out (null). */
export function toInput(f: FormState): InitiativeInput {
  const on = f.levers;
  const when = (cond: boolean, v: number | null) => (cond ? v : null);
  return {
    name: f.name.trim(),
    description: f.description.trim(),
    owner_id: Number(f.ownerId),
    value_type_id: Number(f.valueTypeId),
    ai_layer: f.aiLayer,
    stage: f.stage,
    date_start: f.dateStart || null,
    date_delivery: f.dateDelivery || null,
    cases_per_year: when(on.efficiency || on.quality, parseNumber(f.casesPerYear)),
    hours_saved_per_case: when(on.efficiency, parseNumber(f.hoursSavedPerCase)),
    error_rate_before: when(on.quality, pct(f.errorRatePct)),
    errors_avoided: when(on.quality, pct(f.errorsAvoidedPct)),
    cost_per_error: when(on.quality, parseNumber(f.costPerError)),
    risk_events_per_year: when(on.riskReduction, parseNumber(f.riskEventsPerYear)),
    events_avoided: when(on.riskReduction, pct(f.eventsAvoidedPct)),
    cost_per_event: when(on.riskReduction, parseNumber(f.costPerEvent)),
    delay_events_per_year: when(on.speed, parseNumber(f.delayEventsPerYear)),
    cost_of_delay_per_event: when(on.speed, parseNumber(f.costOfDelayPerEvent)),
    lead_time_saved: when(on.speed, pct(f.leadTimeSavedPct)),
    estimate_basis: f.estimateBasis,
    delivery_likelihood: f.deliveryLikelihood,
    solution_complexity_score: Number(f.complexity),
    one_time_costs: parseNumber(f.oneTimeCosts) ?? 0,
    running_cost_range: f.runningCostRange as RunningCostRange,
    employee_personal_data: f.employeePersonalData,
    performance_or_behaviour_control: f.performanceOrBehaviourControl,
    decisions_on_employees: f.decisionsOnEmployees,
    profiling_of_individuals: f.profilingOfIndividuals,
    changes_employee_workflows: f.changesEmployeeWorkflows,
    prohibited_practice: f.prohibitedPractice,
  };
}

const NUMBER_FIELDS: Record<string, keyof FormState> = {
  cases_per_year: "casesPerYear",
  hours_saved_per_case: "hoursSavedPerCase",
  cost_per_error: "costPerError",
  risk_events_per_year: "riskEventsPerYear",
  cost_per_event: "costPerEvent",
  delay_events_per_year: "delayEventsPerYear",
  cost_of_delay_per_event: "costOfDelayPerEvent",
};

/** Field -> message; empty when the form can be submitted. Same rules as the API. */
export function validate(f: FormState): Partial<Record<keyof FormState | "levers", string>> {
  const errors: Partial<Record<keyof FormState | "levers", string>> = {};
  const required: [keyof FormState, string][] = [
    ["name", "Enter a name."],
    ["description", "Describe the idea."],
    ["businessUnit", "Choose a business unit."],
    ["ownerId", "Choose an owner."],
    ["valueTypeId", "Choose a flagship."],
    ["aiLayer", "Choose the AI layer."],
    ["runningCostRange", "Choose a range."],
    ["stage", "Choose a stage."],
    ["complexity", "Choose the complexity."],
  ];
  for (const [field, message] of required) if (!String(f[field]).trim()) errors[field] = message;
  // a new idea has passed no gate yet
  const stageError = f.stage ? stageGateError(f.stage, null) : null;
  if (stageError) errors.stage = stageError;

  const input = toInput(f);
  for (const [field, key] of Object.entries(NUMBER_FIELDS)) {
    if (String(f[key]).trim() && input[field as keyof InitiativeInput] === null && isLeverFieldOn(f, field)) {
      errors[key] = "Enter a number ≥ 0.";
    }
  }
  for (const key of ["errorRatePct", "errorsAvoidedPct", "eventsAvoidedPct", "leadTimeSavedPct"] as const) {
    const n = parseNumber(f[key]);
    if (f[key].trim() && (n === null || n > 100)) errors[key] = "Enter a percentage between 0 and 100.";
  }
  if (!f.oneTimeCosts.trim()) errors.oneTimeCosts = "Enter an amount (0 if none).";
  else if (parseNumber(f.oneTimeCosts) === null) errors.oneTimeCosts = "Enter an amount ≥ 0.";
  const complete = LEVERS.some((l) => f.levers[l.key] && l.fields.every((field) => input[field] !== null));
  if (!complete) errors.levers = "Fill in all drivers of at least one value lever.";
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
  errorRatePct: number;
  errorsAvoidedPct?: number;
  costPerError: number;
  eventsAvoidedPct?: number;
  costPerEvent: number;
  costOfDelayPerEvent: number;
  leadTimeSavedPct?: number;
}

/** Typical values for the chosen solution type (or AI layer) and flagship, shown as hints (never filled in). */
export function typicalValues(solutionTypeOrLayer: string | undefined, flagship: string | undefined): Typical {
  const family = solutionTypeOrLayer
    ? FAMILY_BY_SOLUTION_TYPE[solutionTypeOrLayer] ?? FAMILY_BY_AI_LAYER[solutionTypeOrLayer]
    : undefined;
  const fl = flagship ?? "";
  return {
    hoursSavedPerCase: family && HOURS_SAVED[family],
    errorRatePct: 8,
    errorsAvoidedPct: family && ERROR_CUT[family],
    costPerError: COST_ERROR[fl] ?? 500,
    eventsAvoidedPct: family && P_EVENT_CUT[family],
    costPerEvent: COST_EVENT[fl] ?? 20_000,
    costOfDelayPerEvent: COST_DELAY[fl] ?? 20_000,
    leadTimeSavedPct: family && SPEEDUP[family],
  };
}
