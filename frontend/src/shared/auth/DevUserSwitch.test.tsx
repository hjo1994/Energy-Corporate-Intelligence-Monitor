import { fireEvent, render, screen } from "@testing-library/react";

import { serviceApi } from "../api/serviceApi";
import { DevUserSwitch } from "./DevUserSwitch";

vi.mock("../api/serviceApi", () => ({
  serviceApi: { get: vi.fn(), setAuthHeader: vi.fn(), removeAuthHeader: vi.fn() },
}));

const api = vi.mocked(serviceApi);
const USERS = [
  { name: "Jonas", email: "jonas@demo.local", role: "Submitter" },
  { name: "Demo Approver", email: "approver@demo.local", role: "Admin" },
];

function answer(users: unknown[], signedIn: string) {
  api.get.mockImplementation(async (path: string) => (path === "/auth/dev-users" ? users : { user: signedIn }) as never);
}

describe("DevUserSwitch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
  });

  it("shows the signed-in persona and switches with the dev token, kept per tab", async () => {
    answer(USERS, "Jonas");
    const onSwitch = vi.fn();
    render(<DevUserSwitch onSwitch={onSwitch} />);
    const select = (await screen.findByLabelText("Demo user")) as HTMLSelectElement;
    expect(select.value).toBe("jonas@demo.local");
    expect(screen.getByRole("option", { name: "Demo Approver (Admin)" })).toBeInTheDocument();

    fireEvent.change(select, { target: { value: "approver@demo.local" } });
    expect(api.setAuthHeader).toHaveBeenCalledWith("dev:approver@demo.local");
    expect(window.sessionStorage.getItem("ai-cockpit.dev-user")).toBe("approver@demo.local");
    expect(onSwitch).toHaveBeenCalled();
  });

  it("stays hidden when the backend has no personas", async () => {
    answer([], "Dev User");
    const { container } = render(<DevUserSwitch />);
    await new Promise((r) => setTimeout(r, 0));
    expect(container).toBeEmptyDOMElement();
  });
});
