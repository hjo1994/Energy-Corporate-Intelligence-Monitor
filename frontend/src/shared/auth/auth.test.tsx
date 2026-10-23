import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useAuth } from "eg-auth-react";

import { OidcGate } from "./AuthGate";

vi.mock("eg-auth-react", () => ({ useAuth: vi.fn(), hasAuthParams: vi.fn(() => false) }));

const auth = vi.mocked(useAuth);
const setAuth = (state: Record<string, unknown>) =>
  auth.mockReturnValue({ isLoading: false, isAuthenticated: false, activeNavigator: undefined, error: undefined, ...state } as never);

function renderGate() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/login" element={<p>Login page</p>} />
        <Route path="/*" element={<OidcGate><p>Protected content</p></OidcGate>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("OidcGate", () => {
  it("shows the content only to signed-in users", () => {
    setAuth({ isAuthenticated: true });
    renderGate();
    expect(screen.getByText("Protected content")).toBeInTheDocument();
  });

  it("sends signed-out users to the login page without rendering the content", () => {
    setAuth({ isAuthenticated: false });
    renderGate();
    expect(screen.getByText("Login page")).toBeInTheDocument();
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
  });

  it("waits while the login is being checked, instead of redirecting too early", () => {
    setAuth({ isLoading: true });
    renderGate();
    expect(screen.getByRole("status")).toHaveTextContent("Checking sign-in");
    expect(screen.queryByText("Login page")).not.toBeInTheDocument();
  });

  it("shows an authentication error with a way back to the login", () => {
    setAuth({ error: new Error("kaputt") });
    renderGate();
    expect(screen.getByRole("alert")).toHaveTextContent("kaputt");
    expect(screen.getByRole("link", { name: "Go to sign-in" })).toHaveAttribute("href", "/login");
  });
});

describe("dev bypass", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("is off unless explicitly enabled", async () => {
    vi.stubEnv("VITE_AUTH_DEV_BYPASS", "");
    const { AUTH_DEV_BYPASS } = await import("./devBypass");
    expect(AUTH_DEV_BYPASS).toBe(false);
  });

  it("works in the dev server when enabled", async () => {
    vi.stubEnv("VITE_AUTH_DEV_BYPASS", "true");
    vi.stubEnv("DEV", true);
    const { AUTH_DEV_BYPASS } = await import("./devBypass");
    expect(AUTH_DEV_BYPASS).toBe(true);
  });

  it("can never be on in a production build, even if the variable leaks in", async () => {
    vi.stubEnv("VITE_AUTH_DEV_BYPASS", "true");
    vi.stubEnv("DEV", false);
    const { AUTH_DEV_BYPASS } = await import("./devBypass");
    expect(AUTH_DEV_BYPASS).toBe(false);
  });
});

import userEvent from "@testing-library/user-event";

import { LoginPage } from "./LoginPage";
import { authManager } from "./authManager";

vi.mock("./authManager", () => ({ authManager: { userManager: { signinRedirect: vi.fn() } } }));

describe("LoginPage", () => {
  it("starts the OIDC redirect", async () => {
    vi.mocked(authManager.userManager.signinRedirect).mockResolvedValue(undefined as never);
    render(<LoginPage />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(authManager.userManager.signinRedirect).toHaveBeenCalledWith({ nonce: expect.any(String) });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows why the login could not start instead of failing silently", async () => {
    vi.mocked(authManager.userManager.signinRedirect).mockRejectedValue(new Error("No authority or metadataUrl configured on settings"));
    render(<LoginPage />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No authority");
  });
});
