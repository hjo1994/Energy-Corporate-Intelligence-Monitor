import type { Rights } from "../api/types";

/**
 * The cockpit is used in three roles, each with its own tabs: innovators bring in ideas, approvers
 * decide on them and keep the overview, management steers by value. The URL prefix says the role.
 */
export type Role = "innovate" | "approve" | "steer";

export const ROLES: { id: Role; label: string; home: string }[] = [
  { id: "innovate", label: "Innovator", home: "/innovate/start" },
  { id: "approve", label: "Approver", home: "/approve/overview/list" },
  { id: "steer", label: "Management", home: "/steer/value" },
];

export const roleHome = (role: Role): string => ROLES.find((r) => r.id === role)!.home;

export function roleOfPath(pathname: string): Role | null {
  const first = pathname.split("/")[1];
  return ROLES.some((r) => r.id === first) ? (first as Role) : null;
}

/**
 * The roles the user may switch to. Everyone is an innovator; the approver role needs the approver
 * rights, management the admin rights. The local dev bypass shows all three.
 */
export function allowedRoles(rights: Rights, devBypass: boolean): Role[] {
  if (devBypass) return ROLES.map((r) => r.id);
  const out: Role[] = ["innovate"];
  if (rights.canApprove) out.push("approve");
  if (rights.canAdmin || rights.canManageUsers) out.push("steer");
  return out;
}

const KEY = "ai-cockpit.role";

export function storedRole(): Role | null {
  try {
    const v = window.localStorage.getItem(KEY);
    return ROLES.some((r) => r.id === v) ? (v as Role) : null;
  } catch {
    return null;
  }
}

export function storeRole(role: Role): void {
  try {
    window.localStorage.setItem(KEY, role);
  } catch {
    // no storage: the role is not remembered across visits
  }
}
