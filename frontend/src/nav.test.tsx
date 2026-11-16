import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import App from "./App";
import { departmentCount, groupByDepartment } from "./domain/departments";
import { FALLBACK_STATS, pathStats } from "./domain/path";
import { make, SAMPLE } from "./test/fixtures";

import { serviceApi } from "./shared/api/serviceApi";

vi.mock("./shared/api/serviceApi", () => ({ serviceApi: { get: vi.fn(), post: vi.fn() } }));

const get = vi.mocked(serviceApi.get);
const opt = (...values: string[]) => values.map((value) => ({ value, label: value }));

function mockApi({ rights = { canApprove: true, canAdmin: true }, approvals = [] as unknown[] } = {}) {
  get.mockReset();
  get.mockImplementation((async (path: string) => {
    if (path === "/auth/rights") return { user: "Jonas", rights };
    if (path === "/features") return { initiative_input: true };
    if (path === "/approvals") return approvals;
    if (path === "/me/use-cases") return [];
    if (path === "/owners" || path === "/users/directory" || path === "/value-types" || path === "/solution-types") return [];
    if (path === "/form-options") return { ai_layers: opt("AI for productivity and efficiency"), running_cost_ranges: [] };
    return { items: SAMPLE, total: SAMPLE.length, limit: 500, offset: 0 };
  }) as never);
}

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
  it("opens as innovator on the start page; each role has its own tabs", async () => {
    mockApi();
    renderAt("/");
    await screen.findByRole("region", { name: "The path of an idea" });
    expect(where()).toBe("/innovate/start");
    expect(tabNames()).toEqual(["Start", "Exploration", "My use cases"]);
    expect(screen.getByRole("button", { name: "+ New AI idea" })).toBeInTheDocument();

    const roles = screen.getByRole("group", { name: "Role" });
    await userEvent.click(within(roles).getByRole("button", { name: "Approver" }));
    expect(where()).toBe("/approve/overview");
    expect(tabNames()).toEqual(["Use cases", "Approvals"]);
    expect(within(roles).getByRole("button", { name: "Approver" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: "+ New AI idea" })).not.toBeInTheDocument();
    // the overview keeps its cockpit, list and board
    const sub = screen.getByRole("navigation", { name: "Overview" });
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
    await vi.waitFor(() => expect(where()).toBe("/approve/overview"));
  });

  it("shows the waiting ideas on the approver segment while another role is active", async () => {
    mockApi({ approvals: [{ id: 9 }, { id: 10 }] });
    renderAt("/innovate/start");
    const approver = within(await screen.findByRole("group", { name: "Role" })).getByRole("button", { name: /Approver/ });
    expect(await within(approver).findByLabelText("2 waiting")).toBeInTheDocument();
  });

  it("hides the switch for users with one role and keeps them out of the other roles' pages", async () => {
    mockApi({ rights: { canApprove: false, canAdmin: false } });
    renderAt("/steer/value");
    await vi.waitFor(() => expect(where()).toBe("/innovate/start"));
    expect(screen.queryByRole("group", { name: "Role" })).not.toBeInTheDocument();
    expect(tabNames()).toEqual(["Start", "Exploration", "My use cases"]);
  });

  it("offers only the roles the user has", async () => {
    mockApi({ rights: { canApprove: true, canAdmin: false } });
    renderAt("/");
    const roles = await screen.findByRole("group", { name: "Role" });
    expect(within(roles).getAllByRole("button").map((b) => b.textContent)).toEqual(["Innovator", "Approver"]);
  });
});

describe("innovator start page", () => {
  it("shows the path from form 1 to production with figures from the data", async () => {
    mockApi();
    renderAt("/innovate/start");
    expect(await screen.findByRole("heading", { name: "Every AI use case here started as a few sentences." })).toBeInTheDocument();
    const path = screen.getByRole("region", { name: "The path of an idea" });
    const stops = within(path).getAllByRole("listitem");
    expect(stops.map((s) => within(s).getByRole("heading").textContent)).toEqual([
      "Form 1", "Needs gate (decision)", "Ideation", "Form 2", "Scope gate (decision)", "PoC", "MVP", "Implementation", "Deploy gate (decision)", "Production",
    ]);
    // SAMPLE: 2 in Ideation, 1 in PoC, 1 cancelled -> 1 of 3 moved on from Ideation
    expect(stops[2]).toHaveTextContent("≈ 3 months");
    expect(stops[2]).toHaveTextContent("move on33 %");
    expect(stops[9]).toHaveTextContent("live0of all0 %");
  });

  it("the explore door leads to the exploration", async () => {
    mockApi();
    renderAt("/innovate/start");
    const door = await screen.findByRole("button", { name: "Explore the map →" });
    expect(screen.getByText(/4 use cases from 2 departments/)).toBeInTheDocument();
    await userEvent.click(door);
    expect(where()).toBe("/innovate/explore");
    expect(screen.getByRole("heading", { name: "Exploration" })).toBeInTheDocument();
  });

  it("the submit door opens form 1 in a drawer over the page; Escape closes it", async () => {
    mockApi();
    renderAt("/innovate/start");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Start Form 1 →" }));
    const drawer = screen.getByRole("dialog", { name: "New AI idea" });
    expect(await within(drawer).findByRole("heading", { name: "Add a new AI idea" })).toBeInTheDocument();
    // the path stays behind it
    expect(screen.getByRole("region", { name: "The path of an idea" })).toBeInTheDocument();
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

describe("innovator exploration", () => {
  it("groups the use cases by department, filters by search and shows a use case's details", async () => {
    mockApi();
    renderAt("/innovate/explore");
    await screen.findByRole("heading", { name: "Exploration" });
    expect(screen.getAllByRole("region").map((r) => r.getAttribute("aria-label"))).toEqual(["Assets", "Innovation", "No department"]);
    expect(within(screen.getByRole("region", { name: "Assets" })).getAllByRole("button")).toHaveLength(2);

    const user = userEvent.setup();
    await user.type(screen.getByRole("searchbox", { name: "Search use cases" }), "capex");
    expect(screen.getAllByRole("region").map((r) => r.getAttribute("aria-label"))).toEqual(["Assets"]);

    await user.click(screen.getByRole("button", { name: "Alpha · Ideation" }));
    const detail = screen.getByRole("complementary", { name: "Use case details" });
    expect(detail).toHaveTextContent("Alpha");
    expect(detail).toHaveTextContent("DepartmentAssets");
    expect(detail).toHaveTextContent("TopicCAPEX delivery");
    expect(detail).toHaveTextContent("Automatisierung");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("complementary", { name: "Use case details" })).not.toBeInTheDocument();
  });
});

describe("path figures and departments", () => {
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

  it("treats departments differing only in case or hyphens as one", () => {
    const owner = (department: string) => ({ id: 1, name: "x", department, category: null });
    const items = [
      make({ id: 1, name: "a", owner: owner("Infra") }),
      make({ id: 2, name: "b", owner: owner("INFRA") }),
      make({ id: 3, name: "c", owner: owner("Infra") }),
      make({ id: 4, name: "d", owner: owner("GO‑C") }),
      make({ id: 5, name: "e", owner: owner("go-c") }),
      make({ id: 6, name: "f" }),
    ];
    expect(groupByDepartment(items).map((g) => [g.label, g.items.length])).toEqual([["Infra", 3], ["go-c", 2], ["No department", 1]]);
    expect(departmentCount(items)).toBe(2);
  });
});
