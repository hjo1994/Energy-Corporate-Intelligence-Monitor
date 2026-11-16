import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import App from "./App";
import { atlasItems, departmentKeyOf, tokens } from "./domain/atlas";
import { FALLBACK_STATS, pathStats } from "./domain/path";
import { make, SAMPLE } from "./test/fixtures";

import { serviceApi } from "./shared/api/serviceApi";

vi.mock("./shared/api/serviceApi", () => ({ serviceApi: { get: vi.fn(), post: vi.fn() } }));

const get = vi.mocked(serviceApi.get);
const opt = (...values: string[]) => values.map((value) => ({ value, label: value }));

function mockApi({ rights = { canApprove: true, canAdmin: true }, approvals = [] as unknown[], items = SAMPLE } = {}) {
  get.mockReset();
  get.mockImplementation((async (path: string) => {
    if (path === "/auth/rights") return { user: "Jonas", rights };
    if (path === "/features") return { initiative_input: true };
    if (path === "/approvals") return approvals;
    if (path === "/me/use-cases") return [];
    if (path === "/owners" || path === "/users/directory" || path === "/value-types" || path === "/solution-types") return [];
    if (path === "/form-options") return { ai_layers: opt("AI for productivity and efficiency"), running_cost_ranges: [] };
    return { items, total: items.length, limit: 500, offset: 0 };
  }) as never);
}

// departments as the sheets spell them (the atlas maps them to its areas)
const owner = (id: number, department: string, category: string) => ({ id, name: `Owner ${id}`, department, category });
const ATLAS = [
  make({ id: 1, name: "Alpha", description: "Automatisierung", stage: "Ideation", owner: owner(1, "ASSETS", "ETB"), topic: "automation" }),
  make({ id: 2, name: "Beta", stage: "PoC", owner: owner(2, "Asset Management", "50 Hertz"), topic: "forecast" }),
  make({ id: 3, name: "Gamma", stage: "Ideation", owner: owner(3, "Innovation", "IT"), topic: "code" }),
  make({ id: 4, name: "Delta", stage: "Cancelled", owner: null }),
];

function Where() {
  return <output data-testid="where">{useLocation().pathname}</output>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <Where />
    </MemoryRouter>,
  );
}

const tabNames = () =>
  within(screen.getByRole("navigation", { name: "Views" }))
    .getAllByRole("link")
    .map((a) => a.textContent?.trim());
const where = () => screen.getByTestId("where").textContent;

describe("role navigation", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("opens as innovator on the start page; each role has its own tabs", async () => {
    mockApi();
    renderAt("/");
    await screen.findByRole("heading", { name: "The path from an idea to AI in production" });
    expect(where()).toBe("/innovate/start");
    expect(tabNames()).toEqual(["Start", "Exploration", "My use cases"]);
    expect(screen.getByRole("button", { name: "+ New AI idea" })).toBeInTheDocument();

    const roles = screen.getByRole("group", { name: "Role" });
    await userEvent.click(within(roles).getByRole("button", { name: "Approver" }));
    await vi.waitFor(() => expect(where()).toBe("/approve/overview/list"));
    expect(tabNames()).toEqual(["Use cases", "Approvals"]);
    expect(within(roles).getByRole("button", { name: "Approver" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: "+ New AI idea" })).not.toBeInTheDocument();
    // the overview has the list and the board; the value dashboard is Management's only
    const sub = screen.getByRole("navigation", { name: "Overview" });
    expect(within(sub).getAllByRole("link").map((a) => a.textContent)).toEqual(["List", "Board"]);
    expect(screen.queryByRole("region", { name: "Estimated value" })).not.toBeInTheDocument();
    await userEvent.click(within(sub).getByRole("link", { name: "Board" }));
    expect(where()).toBe("/approve/overview/board");
    expect(screen.getByRole("link", { name: "Use cases" })).toHaveClass("active");

    await userEvent.click(within(roles).getByRole("button", { name: "Management" }));
    expect(where()).toBe("/steer/value");
    expect(tabNames()).toEqual(["Value dashboard"]);
    expect(await screen.findByRole("region", { name: "Estimated value" })).toBeInTheDocument();
  });

  it.each([
    ["/list", "/approve/overview/list"],
    ["/board", "/approve/overview/board"],
    ["/approve", "/approve/overview/list"],
    ["/approve/overview", "/approve/overview/list"],
    ["/my", "/innovate/my"],
    ["/approvals", "/approve/approvals"],
    ["/value", "/steer/value"],
    ["/new", "/innovate/start"],
  ])("redirects the former route %s to %s", async (from, to) => {
    mockApi();
    renderAt(from);
    await screen.findByRole("navigation", { name: "Views" });
    await vi.waitFor(() => expect(where()).toBe(to));
  });

  it("remembers the last role and opens with it", async () => {
    mockApi();
    const first = renderAt("/approve/approvals");
    await screen.findByRole("link", { name: /Approvals/ });
    expect(window.localStorage.getItem("ai-cockpit.role")).toBe("approve");
    first.unmount();

    renderAt("/");
    await vi.waitFor(() => expect(where()).toBe("/approve/overview/list"));
  });

  it("shows the waiting ideas on the approver segment while another role is active", async () => {
    mockApi({ approvals: [{ id: 9 }, { id: 10 }] });
    renderAt("/innovate/start");
    const approver = within(await screen.findByRole("group", { name: "Role" })).getByRole("button", { name: /Approver/ });
    expect(await within(approver).findByLabelText("2 waiting")).toBeInTheDocument();
  });

  it("gives every signed-in user all three views, whatever their rights (no role gating)", async () => {
    mockApi({ rights: { canApprove: false, canAdmin: false } });
    renderAt("/steer/value");
    const roles = await screen.findByRole("group", { name: "Role" });
    expect(within(roles).getAllByRole("button").map((b) => b.textContent)).toEqual(["Innovator", "Approver", "Management"]);
    expect(where()).toBe("/steer/value");
    expect(tabNames()).toEqual(["Value dashboard"]); // Users stays for those who manage users
    await userEvent.click(within(roles).getByRole("button", { name: "Approver" }));
    await vi.waitFor(() => expect(where()).toBe("/approve/overview/list"));
    expect(tabNames()).toEqual(["Use cases", "Approvals"]);
  });

  it("with role gating: hides the switch for users with one role and keeps them out of the other roles' pages", async () => {
    vi.stubEnv("VITE_ROLE_GATING", "true");
    mockApi({ rights: { canApprove: false, canAdmin: false } });
    renderAt("/steer/value");
    await vi.waitFor(() => expect(where()).toBe("/innovate/start"));
    expect(screen.queryByRole("group", { name: "Role" })).not.toBeInTheDocument();
    expect(tabNames()).toEqual(["Start", "Exploration", "My use cases"]);
  });

  it("with role gating: offers only the roles the user has", async () => {
    vi.stubEnv("VITE_ROLE_GATING", "true");
    mockApi({ rights: { canApprove: true, canAdmin: false } });
    renderAt("/");
    const roles = await screen.findByRole("group", { name: "Role" });
    expect(within(roles).getAllByRole("button").map((b) => b.textContent)).toEqual(["Innovator", "Approver"]);
  });
});

describe("innovator start page (from idea to production)", () => {
  it("shows the 12 stops with figures from the data", async () => {
    mockApi();
    renderAt("/innovate/start");
    expect(await screen.findByRole("heading", { name: "The path from an idea to AI in production" })).toBeInTheDocument();
    const stops = screen.getAllByRole("region").filter((r) => r.classList.contains("step"));
    expect(stops.map((s) => s.getAttribute("aria-label"))).toEqual([
      "Form 1", "Needs gate", "Ideation", "Form 2", "Scope gate", "PoC", "MVP", "Implementation", "Deploy gate", "Production", "Retire gate", "Retired",
    ]);
    // SAMPLE: 2 in Ideation, 1 in PoC, 1 cancelled -> 1 of 3 moved on from Ideation
    expect(within(stops[2]).getByRole("heading", { name: "Shape the use case" })).toBeInTheDocument();
    expect(stops[2]).toHaveTextContent("≈ 3 months");
    expect(stops[2]).toHaveTextContent("33 %moved on to PoC or later1 of 3");
    expect(stops[9]).toHaveTextContent("0solutions live today0 % of all use cases");
    expect(screen.getByText("Stop 1 of 12")).toBeInTheDocument();
  });

  it("ends with two doors; the explore door leads to the exploration", async () => {
    mockApi({ items: ATLAS });
    renderAt("/innovate/start");
    const next = await screen.findByRole("region", { name: "Where do you go from here?" });
    expect(within(next).getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["See what others are building", "Submit your idea"]);
    expect(within(next).getAllByRole("article")[0]).toHaveTextContent("4 use cases from 2 departments.");
    await userEvent.click(within(next).getByRole("button", { name: "Explore the map →" }));
    expect(where()).toBe("/innovate/explore");
    expect(screen.getByRole("heading", { name: "Find use cases related to your idea" })).toBeInTheDocument();
  });

  it("the submit door opens form 1 in a drawer over the page; Escape closes it", async () => {
    mockApi();
    renderAt("/innovate/start");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Start Form 1 →" }));
    const drawer = screen.getByRole("dialog", { name: "New AI idea" });
    expect(await within(drawer).findByRole("heading", { name: "Add a new AI idea" })).toBeInTheDocument();
    // the path stays behind it
    expect(screen.getByRole("heading", { name: "The path from an idea to AI in production" })).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Close" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(where()).toBe("/innovate/start");
  });

  it("the top bar button opens the same drawer from any innovator tab; × closes it", async () => {
    mockApi();
    renderAt("/innovate/explore");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "+ New AI idea" }));
    const drawer = screen.getByRole("dialog", { name: "New AI idea" });
    await user.click(within(drawer).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(where()).toBe("/innovate/explore");
  });

  it("keeps Tab inside the drawer", async () => {
    mockApi();
    renderAt("/innovate/start");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Start Form 1 →" }));
    const drawer = screen.getByRole("dialog", { name: "New AI idea" });
    await within(drawer).findByRole("heading", { name: "Add a new AI idea" });
    for (let k = 0; k < 60; k++) {
      await user.tab();
      expect(drawer).toContainElement(document.activeElement as HTMLElement);
    }
  });
});

describe("innovator exploration (use case atlas)", () => {
  const territories = (c: HTMLElement) => [...c.querySelectorAll("text.buname")].map((t) => t.textContent);
  const also = () => screen.getByTestId("atlas-also").textContent;

  it("draws the departments as territories with one hexagon per use case", async () => {
    mockApi({ items: ATLAS });
    const { container } = renderAt("/innovate/explore");
    await screen.findByRole("heading", { name: "Find use cases related to your idea" });
    // ASSETS and Asset Management are one area (Alpha, Beta), Innovation is Data & AI (Gamma), No owner yet (Delta) last
    expect(territories(container)).toEqual(["Assets", "Data & AI", "No owner yet"]);
    expect(container.querySelectorAll("path.hex")).toHaveLength(4);
    expect(screen.getByRole("heading", { name: "Topics by department" })).toBeInTheDocument();
  });

  it("search narrows the results, also by department name; a row opens the use case", async () => {
    mockApi({ items: ATLAS });
    const { container } = renderAt("/innovate/explore");
    const user = userEvent.setup();
    const q = await screen.findByRole("textbox", { name: "Search use cases by keyword" });

    await user.type(q, "automatisierung");
    expect(also()).toBe("1 of 4 use cases");
    expect(container.querySelectorAll("path.hex.dim")).toHaveLength(3);
    const rail = screen.getByRole("complementary", { name: "Use cases" });
    expect(within(rail).getByRole("heading", { name: "1 use case in Assets" })).toBeInTheDocument();

    await user.clear(q);
    await user.type(q, "data");
    expect(also()).toBe("1 of 4 use cases");
    expect(within(rail).getByText(/names the Data & AI department/)).toBeInTheDocument();
    expect(within(rail).getByText("In the department")).toBeInTheDocument();

    await user.click(within(rail).getByRole("button", { name: /Gamma/ }));
    const detail = within(rail).getByText("Selected use case").parentElement!;
    expect(detail).toHaveTextContent("TopicCode & developer toolsDepartmentData & AITeamInnovation · IT");

    await user.click(screen.getByRole("button", { name: "Clear search" }));
    expect(also()).toBe("");
  });
});

describe("atlas items", () => {
  it("maps departments, tokens and topics as the agreed page did", () => {
    const owner = (department: string | null) => ({ id: 1, name: "x", department, category: "ETB" });
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    expect(departmentKeyOf(make({ id: 1, name: "a", owner: owner("INFRA") }))).toBe("infra");
    expect(departmentKeyOf(make({ id: 2, name: "b", owner: owner("GO‑C") }))).toBe("finance");
    expect(departmentKeyOf(make({ id: 3, name: "c" }))).toBe("unassigned");
    expect(warn).not.toHaveBeenCalled();
    expect(departmentKeyOf(make({ id: 4, name: "d", owner: owner("Somewhere new") }))).toBe("unassigned");
    expect(warn).toHaveBeenCalledOnce();
    warn.mockRestore();
    expect(tokens("LLM API", "Make an LLM API available to developers and products in the group")).toEqual([
      "api", "available", "developers", "group", "llm", "make", "products",
    ]);
    const items = atlasItems([
      make({ id: 1, name: "a", topic: "forecast" }),
      make({ id: 2, name: "b", topic: null }),
      make({ id: 3, name: "c", is_active: false }),
    ]);
    expect(items.map((i) => i.t)).toEqual(["forecast", "other"]);
  });
});

describe("path figures", () => {
  it("counts Idea and Exploration as Ideation and computes how many move on", () => {
    const items = [
      make({ id: 1, name: "a", stage: "Idea" }),
      make({ id: 2, name: "b", stage: "Exploration" }),
      make({ id: 3, name: "c", stage: "PoC" }),
      make({ id: 4, name: "d", stage: "Production" }),
      make({ id: 5, name: "e", stage: "Unknown" }),
    ];
    const s = pathStats(items);
    expect(s.reached).toEqual([4, 2, 1, 1, 1]);
    expect(s.moveOn).toEqual([0.5, 0.5, 1, 1, null]);
    expect(s.live).toBe(1);
    expect(s.liveShare).toBeCloseTo(0.2);
    expect(pathStats([])).toBe(FALLBACK_STATS);
  });
});
