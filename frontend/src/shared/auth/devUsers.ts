import { serviceApi } from "../api/serviceApi";

/**
 * Demo personas for the local dev bypass: the backend's eg-auth stub knows them
 * (EG_AUTH_DEV_USERS) and picks one by the token "dev:<email>". The choice is kept per
 * browser tab (sessionStorage), so two windows can be two people side by side.
 * Only used with AUTH_DEV_BYPASS, which is off in every production build.
 */
export interface DevUser {
  name: string;
  email: string;
  role: string;
}

const KEY = "ai-cockpit.dev-user";

export function storedDevUser(): string | null {
  try {
    return window.sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/** Send the persona's dev token from now on (none: the backend's first persona). */
export function applyDevUser(email: string | null): void {
  if (email) serviceApi.setAuthHeader(`dev:${email}`);
  else serviceApi.removeAuthHeader();
}

export function chooseDevUser(email: string): void {
  try {
    window.sessionStorage.setItem(KEY, email);
  } catch {
    // no storage: the choice lasts until the page is reloaded
  }
  applyDevUser(email);
}

export async function fetchDevUsers(): Promise<DevUser[]> {
  try {
    const users = await serviceApi.get<DevUser[]>("/auth/dev-users");
    return Array.isArray(users) ? users : [];
  } catch {
    return [];
  }
}

export async function fetchSignedInName(): Promise<string | null> {
  try {
    return (await serviceApi.get<{ user?: string }>("/auth/rights"))?.user ?? null;
  } catch {
    return null;
  }
}
