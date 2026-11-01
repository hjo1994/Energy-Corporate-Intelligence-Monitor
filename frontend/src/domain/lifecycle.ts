import type { MyUseCase, Processing, Stagegate, Todo, UseCaseDetail } from "../api/types";

// The lifecycle of a use case: form 1 (idea) -> approval at the needs gate -> form 2,
// filled in step by step per stage gate (Scope, Deploy) -> values while live -> retire.

export const GATES: Stagegate[] = ["Needs", "Scope", "Deploy", "Retire"];

/** The gate a use case works towards next; null once retired. */
export function nextGate(passed: Stagegate | null | undefined): Stagegate | null {
  if (!passed) return "Needs";
  const i = GATES.indexOf(passed);
  return i < 0 || i === GATES.length - 1 ? null : GATES[i + 1];
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

export interface GateGroup {
  key: "scope" | "deploy" | "live";
  title: string;
  subtitle: string;
  /** the gate this group leads to; its date moves the use case on */
  gate: Stagegate | null;
  /** the gate that must have been passed for this group to open */
  opensAfter: Stagegate;
  fields: Form2Field[];
}

/** Form 2, variant B: only what the next gate needs is open, the rest waits. */
export const GATE_GROUPS: GateGroup[] = [
  {
    key: "scope",
    title: "To pass the scope gate",
    subtitle: "Who builds it, how, and under which rules",
    gate: "Scope",
    opensAfter: "Needs",
    fields: [
      { key: "lead_id", label: "Use case lead", kind: "owner" },
      { key: "enabling_team", label: "Which team enables the tech?", kind: "select", options: "enabling_teams" },
      { key: "value_domain", label: "Value domain", kind: "text" },
      { key: "solution_type_id", label: "Solution type", kind: "solutionType" },
      { key: "capability_direction", label: "Consuming or providing a capability?", kind: "segmented", options: "capability_directions" },
      { key: "applicable_to", label: "Applicable to", kind: "multi", options: "applicable_to" },
      { key: "complexity_solidity", label: "How solid is the complexity estimate?", kind: "segmented", options: "complexity_solidities" },
      { key: "strategic_kpis", label: "Strategic KPIs", kind: "text" },
      { key: "tactical_kpis", label: "Tactical KPIs", kind: "text" },
      { key: "autonomy_level", label: "Level of autonomy granted to the AI", kind: "text", hint: "e.g. information analysis, decision support, autonomous action" },
      { key: "eu_ai_act_role", label: "Our role under the EU AI Act", kind: "segmented", options: "eu_ai_act_roles" },
      { key: "eu_ai_act_class", label: "EU AI Act risk class", kind: "segmented", options: "eu_ai_act_classes" },
      { key: "works_council_risk_class", label: "Risk class for the 50Hertz works council", kind: "segmented", options: "works_council_risk_classes" },
    ],
  },
  {
    key: "deploy",
    title: "To pass the deploy gate",
    subtitle: "Works council approval, safety, users",
    gate: "Deploy",
    opensAfter: "Scope",
    fields: [
      { key: "works_council_approved_at", label: "Works council approval on", kind: "date" },
      { key: "safety_component", label: "Is it a safety component?", kind: "bool" },
      { key: "target_user_groups", label: "Target user groups", kind: "text" },
      { key: "expected_users", label: "Expected users", kind: "int" },
    ],
  },
  {
    key: "live",
    title: "While live",
    subtitle: "Measured benefits, actual capex and opex – update yearly",
    gate: "Retire",
    opensAfter: "Deploy",
    fields: [
      { key: "measured_benefits", label: "Measured benefits to date", kind: "eur" },
      { key: "actual_capex", label: "Actual capex to date", kind: "eur" },
      { key: "actual_opex", label: "Actual opex to date", kind: "eur" },
    ],
  },
];

/** Whether a group is open for editing, given the last passed gate. */
export function groupOpen(group: GateGroup, passed: Stagegate | null | undefined): boolean {
  if (!passed) return false;
  return GATES.indexOf(passed) >= GATES.indexOf(group.opensAfter) && passed !== "Retire";
}

/** The current value of a form 2 field in the detail (ids from the nested refs, capex/opex from the drivers). */
export function fieldValue(d: UseCaseDetail, key: string): unknown {
  if (key === "lead_id") return d.lead?.id ?? null;
  if (key === "solution_type_id") return d.solution_type?.id ?? null;
  if (key === "actual_capex" || key === "actual_opex") return (d.drivers?.[key] as number | undefined) ?? null;
  return (d as unknown as Record<string, unknown>)[key] ?? null;
}

export const isFilled = (v: unknown) => v !== null && v !== undefined && v !== "";

export function filledCount(d: UseCaseDetail, group: GateGroup): number {
  return group.fields.filter((f) => isFilled(fieldValue(d, f.key))).length;
}

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
