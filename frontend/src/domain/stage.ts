// The canonical stage values (Idea and Exploration are one stage since 11/2026: Ideation) (normalized from the workbook's Status), in pipeline order.
export const STAGE_ORDER = [
  "Ideation",
  "PoC",
  "MVP",
  "Implementation",
  "Production",
  "On hold",
  "Cancelled",
  "Unknown",
] as const;

const STAGE_COLOR: Record<string, string> = {
  Ideation: "#3b6fa0",
  PoC: "#b9792e",
  MVP: "#7a5c99",
  Implementation: "#0f6e6e",
  Production: "#2f6b3a",
  "On hold": "#5f6b7a",
  Cancelled: "#a8483e",
  Unknown: "#a39d93",
};

export function stageColor(stage: string): string {
  return STAGE_COLOR[stage] ?? STAGE_COLOR.Unknown;
}

export function stageRank(stage: string): number {
  const i = (STAGE_ORDER as readonly string[]).indexOf(stage);
  return i === -1 ? STAGE_ORDER.length : i;
}

// Stages in which work is actually under way.
export const IN_PROGRESS_STAGES = ["PoC", "MVP", "Implementation"];
