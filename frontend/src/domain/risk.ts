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
