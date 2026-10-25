import type { RiskRef } from "../api/types";

// The five levels of the Rahmenbetriebsvereinbarung KI. The data carries their German names
// (seeded by input orchestration, transforms/risk_heuristic.RISK_LEVELS); the UI shows English
// labels by level, falling back to the stored name for an unknown level.
const RISK_LABELS: Record<number, string> = {
  1: "Very low risk", // Sehr geringes Risiko
  2: "Low risk", // Geringes Risiko
  3: "Medium risk", // Mittleres Risiko
  4: "High risk", // Hohes Risiko
  5: "Very high (unacceptable) risk", // Sehr hohes (nicht vertretbares) Risiko
};

export const riskLabel = (risk: RiskRef): string => RISK_LABELS[risk.id] ?? risk.name;

// What each level requires (RiskClassification.DerivedAction, stored in German), in English.
const RISK_ACTIONS: Record<number, string> = {
  1: "Inform the works council; document it in the AI register and the overview list.",
  2: "As level 1, plus: inform the works council early; simplified hazard assessment; training; AI fact sheet; monitoring.",
  3: "As level 2, plus: hazard, human-rights and impact assessments; trial run with evaluation; works council involvement; model tests; fundamental-rights impact assessment for the group works council.",
  4: "As level 3, plus: full risk analysis incl. EU AI Act classification; supervised trial run; works council consent; a works agreement is required.",
  5: "Not acceptable: introduction is prohibited; document the rejection with reasons; notify the authorities if required.",
};

export const riskLevelLabel = (level: number): string => RISK_LABELS[level] ?? `Risk level ${level}`;
export const riskActions = (level: number): string => RISK_ACTIONS[level] ?? "";
