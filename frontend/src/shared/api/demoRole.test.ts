import { serviceApi } from "./serviceApi";
import { chooseDemoApprover, storedDemoApprover } from "./demoRole";

vi.mock("./serviceApi", () => ({ serviceApi: { connection: { defaults: { headers: { common: {} } } } } }));

const headers = (serviceApi as unknown as { connection: { defaults: { headers: { common: Record<string, string> } } } })
  .connection.defaults.headers.common;

describe("demo role", () => {
  beforeEach(() => window.sessionStorage.clear());

  it("sends the demo role header and keeps the choice per tab", () => {
    expect(storedDemoApprover()).toBe(false);
    chooseDemoApprover(true);
    expect(headers["X-Demo-Role"]).toBe("approver");
    expect(storedDemoApprover()).toBe(true);
    chooseDemoApprover(false);
    expect(headers["X-Demo-Role"]).toBeUndefined();
    expect(storedDemoApprover()).toBe(false);
  });
});
