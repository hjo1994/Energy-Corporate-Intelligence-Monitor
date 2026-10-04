// The 9 canonical status values of the source workbook, in pipeline order.
export const STATUS_ORDER = [
  "Idea",
  "Exploration",
  "PoC",
  "MVP",
  "Implementation",
  "Production",
  "On hold",
  "Cancelled",
  "Unknown",
] as const;

const STATUS_COLOR: Record<string, string> = {
  Idea: "#8a8378",
  Exploration: "#3b6fa0",
  PoC: "#b9792e",
  MVP: "#7a5c99",
  Implementation: "#0f6e6e",
  Production: "#2f6b3a",
  "On hold": "#5f6b7a",
  Cancelled: "#a8483e",
  Unknown: "#a39d93",
};

export function statusColor(status: string): string {
  return STATUS_COLOR[status] ?? STATUS_COLOR.Unknown;
}

export function statusRank(status: string): number {
  const i = (STATUS_ORDER as readonly string[]).indexOf(status);
  return i === -1 ? STATUS_ORDER.length : i;
}

// Statuses in which work is actually under way.
export const IN_PROGRESS_STATUSES = ["PoC", "MVP", "Implementation"];
