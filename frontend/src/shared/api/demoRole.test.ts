import { serviceApi } from "./serviceApi";
import { chooseDemoAdmin, storedDemoAdmin } from "./demoRole";

vi.mock("./serviceApi", () => ({ serviceApi: { connection: { defaults: { headers: { common: {} } } } } }));

const headers = (serviceApi as unknown as { connection: { defaults: { headers: { common: Record<string, string> } } } })
  .connection.defaults.headers.common;

describe("demo role", () => {
  beforeEach(() => window.sessionStorage.clear());

  it("sends the demo role header and keeps the choice per tab", () => {
    expect(storedDemoAdmin()).toBe(false);
    chooseDemoAdmin(true);
    expect(headers["X-Demo-Role"]).toBe("admin");
    expect(storedDemoAdmin()).toBe(true);
    chooseDemoAdmin(false);
    expect(headers["X-Demo-Role"]).toBeUndefined();
    expect(storedDemoAdmin()).toBe(false);
  });
});
