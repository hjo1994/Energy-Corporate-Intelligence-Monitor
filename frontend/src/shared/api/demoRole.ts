import { serviceApi } from "./serviceApi";

/**
 * Demo presenters (AI_COCKPIT_DEMO_PRESENTERS on the backend) can switch their session to admin
 * rights for a demo: the frontend sends "X-Demo-Role: admin" and the backend honours it only for
 * them. The choice is kept per browser tab.
 */
const KEY = "ai-cockpit.demo-admin";
const HEADER = "X-Demo-Role";

export function storedDemoAdmin(): boolean {
  try {
    return window.sessionStorage.getItem(KEY) === "true";
  } catch {
    return false;
  }
}

/** The axios headers of serviceApi (eg-auth-react keeps its axios instance in `connection`). */
function commonHeaders(): Record<string, string> | null {
  const connection = (serviceApi as unknown as { connection?: { defaults?: { headers?: { common?: Record<string, string> } } } })
    .connection;
  return connection?.defaults?.headers?.common ?? null;
}

export function applyDemoAdmin(on: boolean): void {
  const headers = commonHeaders();
  if (!headers) return;
  if (on) headers[HEADER] = "admin";
  else delete headers[HEADER];
}

export function chooseDemoAdmin(on: boolean): void {
  try {
    window.sessionStorage.setItem(KEY, String(on));
  } catch {
    // no storage: the choice lasts until the page is reloaded
  }
  applyDemoAdmin(on);
}
