import type { MyUseCase, Processing, Stagegate, Todo, UseCaseDetail } from "../api/types";

// The lifecycle of a use case: form 1 (idea) -> approval (passes the needs gate) -> form 2,
// which can be filled in and changed at any time. Stage and stage gates belong together: each
// gate has a date (up to today = passed, later = planned), and the stage decides which gates
// must already lie in the past. The rule comes from the form 2 Excel ("scope gate must be passed
// before PoC, deploy gate must be passed before production"); the backend checks the same
// (app/lifecycle.py) and serves it as stage_gate_rules in /api/form-options.

export const GATES: Stagegate[] = ["Needs", "Scope", "Deploy", "Retire"];

/** The gate a use case works towards next; null once retired. */
export function nextGate(passed: Stagegate | null | undefined): Stagegate | null {
  if (!passed) return "Needs";
  const i = GATES.indexOf(passed);
  return i < 0 || i === GATES.length - 1 ? null : GATES[i + 1];
}

export type GateRules = Record<string, { passed: Stagegate[]; not_passed: Stagegate[] }>;

const EARLY = { passed: [] as Stagegate[], not_passed: ["Scope", "Deploy"] as Stagegate[] };
const BUILDING = { passed: ["Scope"] as Stagegate[], not_passed: ["Deploy"] as Stagegate[] };
const LIVE = { passed: ["Scope", "Deploy"] as Stagegate[], not_passed: [] as Stagegate[] };
/** Used until /api/form-options has loaded. On hold, Cancelled and Unknown have no rule. */
export const STAGE_GATE_RULES: GateRules = {
  Idea: EARLY,
  Exploration: EARLY,
  PoC: BUILDING,
  MVP: BUILDING,
  Implementation: BUILDING,
  Production: LIVE,
  Retired: LIVE,
};

export type GateDates = Record<Stagegate, string>;

export const GATE_FIELD: Record<Stagegate, "needs_gate_date" | "scope_gate_date" | "deploy_gate_date" | "retire_gate_date"> = {
  Needs: "needs_gate_date",
  Scope: "scope_gate_date",
  Deploy: "deploy_gate_date",
  Retire: "retire_gate_date",
};

/** The saved gate dates of a use case as YYYY-MM-DD ("" = not set). */
export function savedGateDates(d: Partial<Record<(typeof GATE_FIELD)[Stagegate], string | null | undefined>>): GateDates {
  return Object.fromEntries(GATES.map((g) => [g, (d[GATE_FIELD[g]] ?? "").slice(0, 10)])) as GateDates;
}

export type GateState = "passed" | "planned" | "open";

export const gateState = (date: string, today: string = todayIso()): GateState =>
  !date ? "open" : date <= today ? "passed" : "planned";

/** What a stage asks of a gate: "passed" (date in the past), "not_passed" (empty or in the future) or nothing. */
export function gateRequirement(stage: string, gate: Stagegate, rules: GateRules = STAGE_GATE_RULES): "passed" | "not_passed" | null {
  const rule = rules[stage];
  if (!rule) return null;
  if (rule.passed.includes(gate)) return "passed";
  if (rule.not_passed.includes(gate)) return "not_passed";
  return null;
}

/** What does not fit between stage and gate dates, per gate (same rules as the API). */
export function gateProblems(
  stage: string,
  dates: GateDates,
  today: string = todayIso(),
  rules: GateRules = STAGE_GATE_RULES,
): { gate: Stagegate; message: string }[] {
  const out: { gate: Stagegate; message: string }[] = [];
  for (const gate of GATES) {
    const need = gateRequirement(stage, gate, rules);
    const date = dates[gate];
    if (need === "passed" && !date) out.push({ gate, message: `${stage} needs the date the ${gate.toLowerCase()} gate was passed.` });
    else if (need === "passed" && date > today) out.push({ gate, message: `In ${stage} the ${gate.toLowerCase()} gate is passed: the date cannot be in the future.` });
    else if (need === "not_passed" && date && date <= today) out.push({ gate, message: `In ${stage} the ${gate.toLowerCase()} gate is not passed yet: move the date to the future.` });
  }
  const set = GATES.filter((g) => dates[g]);
  for (let i = 1; i < set.length; i++) {
    const [a, b] = [set[i - 1]!, set[i]!];
    if (dates[b] < dates[a]) out.push({ gate: b, message: `The ${b.toLowerCase()} gate cannot come before the ${a.toLowerCase()} gate.` });
  }
  return out;
}

/** The latest gate whose date is up to today. */
export function lastPassedGate(dates: GateDates, today: string = todayIso()): Stagegate | null {
  return [...GATES].reverse().find((g) => gateState(dates[g], today) === "passed") ?? null;
}

/** The day after today, the earliest date of a planned gate. */
export function tomorrowIso(now: Date = new Date()): string {
  const t = new Date(now);
  t.setDate(t.getDate() + 1);
  return todayIso(t);
}

export type FieldKind = "text" | "select" | "segmented" | "multi" | "bool" | "date" | "int" | "eur" | "owner" | "solutionType";

export interface Form2Field {
  key: string;
  label: string;
  kind: FieldKind;
  /** key of the choice list in /api/form-options */
  options?: string;
  hint?: string;
}

/** Form 2: the details of a use case, all open at any time. */
export const FORM2_FIELDS: Form2Field[] = [
  { key: "lead_id", label: "Use case lead", kind: "owner" },
  { key: "enabling_team", label: "Which team enables the tech?", kind: "select", options: "enabling_teams" },
  { key: "solution_type_id", label: "Solution type", kind: "solutionType" },
  { key: "value_domain", label: "Value domain", kind: "text" },
  { key: "capability_direction", label: "Consuming or providing a capability?", kind: "segmented", options: "capability_directions" },
  { key: "applicable_to", label: "Applicable to", kind: "multi", options: "applicable_to" },
  { key: "complexity_solidity", label: "How solid is the complexity estimate?", kind: "segmented", options: "complexity_solidities" },
  { key: "strategic_kpis", label: "Strategic KPIs", kind: "text" },
  { key: "tactical_kpis", label: "Tactical KPIs", kind: "text" },
  { key: "autonomy_level", label: "Level of autonomy granted to the AI", kind: "text", hint: "e.g. information analysis, decision support, autonomous action" },
  { key: "eu_ai_act_role", label: "Our role under the EU AI Act", kind: "segmented", options: "eu_ai_act_roles" },
  { key: "eu_ai_act_class", label: "EU AI Act risk class", kind: "segmented", options: "eu_ai_act_classes" },
  { key: "works_council_risk_class", label: "Risk class for the 50Hertz works council", kind: "segmented", options: "works_council_risk_classes" },
  { key: "works_council_approved_at", label: "Works council approval on", kind: "date" },
  { key: "safety_component", label: "Is it a safety component?", kind: "bool" },
  { key: "target_user_groups", label: "Target user groups", kind: "text" },
  { key: "expected_users", label: "Expected users", kind: "int" },
  { key: "measured_benefits", label: "Measured benefits to date", kind: "eur" },
  { key: "actual_capex", label: "Actual capex to date", kind: "eur" },
  { key: "actual_opex", label: "Actual opex to date", kind: "eur" },
];

/** The current value of an editable field in the detail (ids from the nested refs, capex/opex from the drivers). */
export function fieldValue(d: UseCaseDetail, key: string): unknown {
  if (key === "lead_id") return d.lead?.id ?? null;
  if ((Object.values(GATE_FIELD) as string[]).includes(key)) return ((d as unknown as Record<string, string | null>)[key] ?? "").slice(0, 10) || null;
  // the entered one-time costs (the detail's one_time_costs are the expected costs)
  if (key === "one_time_costs") return (d.drivers?.one_time_costs as number | undefined) ?? null;
  if (key === "solution_type_id") return d.solution_type?.id ?? null;
  if (key === "actual_capex" || key === "actual_opex") return (d.drivers?.[key] as number | undefined) ?? null;
  return (d as unknown as Record<string, unknown>)[key] ?? null;
}

export const isFilled = (v: unknown) => v !== null && v !== undefined && v !== "";

export const TODO_LABEL: Record<Todo, string> = {
  revise_and_resubmit: "Revise",
  complete_details: "Fill in the details",
};

/** Short text for the user on how far the pipeline has got. */
export const PROCESSING_LABEL: Record<Processing, string> = {
  pending: "Not processed yet",
  changes_pending: "Changes not processed yet",
  not_assessed: "Not assessed yet",
  assessed: "Assessed",
};

export const PROCESSING_HINT: Record<Processing, string> = {
  pending: "Saved — the pipeline has not picked it up yet. Values shown are a preview.",
  changes_pending: "Your latest changes are saved but not processed yet. Values shown include them as a preview.",
  not_assessed: "Processed, but some inputs needed for the value assessment are still missing.",
  assessed: "Values are assessed by the pipeline.",
};

export const APPROVAL_LABEL = { pending: "Pending", approved: "Approved", rejected: "Rejected" } as const;

export function approvalLabel(status: MyUseCase["approval_status"]): string {
  return status ? APPROVAL_LABEL[status] : "From Excel";
}

export const ROLE_LABEL = { submitter: "Submitted", owner: "Owner", lead: "Lead" } as const;

/** "2026-11-14T00:00:00" -> "14.11.26" */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "–";
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getFullYear()).slice(2)}`;
}

/** Today as YYYY-MM-DD in local time, for date inputs. */
export function todayIso(now: Date = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

/** Days since an ISO timestamp, as "today" / "1 day" / "3 days". */
export function age(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "";
  const days = Math.floor((now.getTime() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "today";
  return days === 1 ? "1 day" : `${days} days`;
}

export const keur = (eur: number | null | undefined): string =>
  eur === null || eur === undefined ? "–" : `€ ${Math.round(eur / 1000).toLocaleString("en-US")}k`;
