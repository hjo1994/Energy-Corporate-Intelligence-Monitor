import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import type { ApprovalItem, MyUseCase, UseCaseDetail } from "../api/types";
import { gateProblems, lastPassedGate, nextGate, savedGateDates } from "../domain/lifecycle";
import { serviceApi } from "../shared/api/serviceApi";
import { SAMPLE, make } from "../test/fixtures";
import { toPatch } from "./UseCaseView";

vi.mock("../shared/api/serviceApi", () => ({ serviceApi: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }));

const get = vi.mocked(serviceApi.get);
const post = vi.mocked(serviceApi.post);
const patch = vi.mocked(serviceApi.patch);

const owner = { id: 1, name: "Owner A", department: "Assets", category: "ETB" };
const lead = { id: 3, name: "Lead C", department: null, category: "ETB" };
const opt = (...values: string[]) => values.map((value) => ({ value, label: value }));
const formOptions = {
  ai_layers: opt("AI for productivity and efficiency"),
  running_cost_ranges: [{ value: "up_to_10k", label: "up to 10k € / year", amount: 5000 }],
  enabling_teams: opt("DiY", "EL.AI"),
  complexity_solidities: opt("rough", "benchmark", "measured"),
  eu_ai_act_classes: opt("banned", "high-risk", "transparency", "minimal"),
  eu_ai_act_roles: opt("provider", "deployer", "consumer"),
  works_council_risk_classes: opt("hi", "med", "lo"),
  capability_directions: opt("providing", "consuming"),
  applicable_to: opt("ETB", "50Hertz", "Group"),
};

function mine(over: Partial<MyUseCase> & { id: number; name: string }): MyUseCase {
  return {
    approval_status: "approved", stage: "Idea", needs_gate_date: "2026-01-15T00:00:00", scope_gate_date: null,
    deploy_gate_date: null, retire_gate_date: null, last_gate: "Needs", comment: null,
    potential_value_eur: 145000, risk_classification: { id: 3, name: "Mittleres Risiko" }, processing: "assessed",
    provisional: false, form2_progress: { filled: 2, total: 18 }, roles: ["owner"], todos: [], updated_at: null, can_edit: true,
    ...over,
  };
}

function detail(over: Partial<UseCaseDetail> = {}): UseCaseDetail {
  return {
    ...make({ id: 7, name: "Grid check", owner, potential_value_eur: 145000 }),
    lead, approval_status: "approved", stage: "Idea", needs_gate_date: "2026-01-15T00:00:00", scope_gate_date: null,
    deploy_gate_date: null, retire_gate_date: null, last_gate: "Needs", stage_problems: [], processing: "assessed",
    provisional: false, comment: null, measured_benefits: null, actual_costs: null, running_cost_range: "up_to_10k",
    employee_personal_data: "no", performance_or_behaviour_control: false, decisions_on_employees: "none",
    profiling_of_individuals: false, changes_employee_workflows: false, prohibited_practice: false,
    enabling_team: null, complexity_solidity: null, strategic_kpis: null, tactical_kpis: null, value_domain: null,
    autonomy_level: null, eu_ai_act_class: null, eu_ai_act_role: null, works_council_risk_class: null,
    target_user_groups: null, applicable_to: null, capability_direction: null, safety_component: null,
    works_council_approved_at: null, expected_users: null, drivers: {}, submitted_by: "Dev User",
    submitted_at: "2026-10-30T10:00:00", changed_by: null, updated_at: null, assessed_version_id: 1, assessed_at: null,
    pending_action_ids: [], revision: "11-0", form2_progress: { filled: 2, total: 18 }, todos: ["complete_details"],
    can_edit: true, can_decide: false,
    ...over,
  };
}

const inboxItem: ApprovalItem = {
  id: 9, name: "Vegetation risk", description: "Satellite images", owner, value_type: null,
  ai_layer: "Operational and advanced AI", submitted_by: "Dev User", submitted_at: "2026-10-29T10:00:00",
  potential_value_eur: 390000, hypothetical_value_eur: 1000000, annual_cost_eur: 60000, solution_complexity_score: 7,
  risk_classification: { id: 1, name: "Sehr geringes Risiko" }, processing: "assessed", can_decide: true,
};

function mockApi(routes: Record<string, unknown>) {
  get.mockReset();
  get.mockImplementation((async (path: string) => {
    if (path in routes) return routes[path];
    if (path === "/owners") return [owner, lead];
    if (path === "/value-types" || path === "/solution-types") return [];
    if (path === "/form-options") return formOptions;
    if (path === "/features") return { initiative_input: true };
    if (path === "/auth/rights") return { user: "Dev User", rights: { canApprove: false, canAdmin: false } };
    if (path === "/me/use-cases") return [];
    if (path.endsWith("/similar")) return [];
    return { items: SAMPLE, total: SAMPLE.length, limit: 500, offset: 0 };
  }) as never);
}

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );

describe("stage and stage gates", () => {
  const today = "2026-11-01";
  const dates = (over: Partial<Record<"Needs" | "Scope" | "Deploy" | "Retire", string>> = {}) => ({ Needs: "", Scope: "", Deploy: "", Retire: "", ...over });

  it("follows the form 2 Excel: scope gate before PoC, deploy gate before Production", () => {
    expect(gateProblems("Idea", dates(), today)).toEqual([]);
    expect(gateProblems("Idea", dates({ Scope: "2026-02-01" }), today).map((p) => p.gate)).toEqual(["Scope"]);
    expect(gateProblems("PoC", dates(), today).map((p) => p.gate)).toEqual(["Scope"]);
    expect(gateProblems("PoC", dates({ Scope: "2026-02-01", Deploy: "2027-03-01" }), today)).toEqual([]);
    expect(gateProblems("PoC", dates({ Scope: "2026-02-01", Deploy: "2026-03-01" }), today).map((p) => p.gate)).toEqual(["Deploy"]);
    expect(gateProblems("Production", dates({ Scope: "2026-02-01" }), today).map((p) => p.gate)).toEqual(["Deploy"]);
    expect(gateProblems("On hold", dates({ Scope: "2026-02-01" }), today)).toEqual([]);
    // in gate order
    expect(gateProblems("MVP", dates({ Needs: "2026-03-01", Scope: "2026-02-01" }), today)[0]!.message).toMatch(/before the needs gate/);
  });

  it("derives the last passed gate from the dates", () => {
    const d = savedGateDates({ needs_gate_date: "2026-01-15T00:00:00", scope_gate_date: "2026-12-01T00:00:00" });
    expect(d).toEqual(dates({ Needs: "2026-01-15", Scope: "2026-12-01" }));
    expect(lastPassedGate(d, today)).toBe("Needs"); // the scope gate is only planned
    expect([nextGate(null), nextGate("Needs"), nextGate("Deploy"), nextGate("Retire")]).toEqual(["Needs", "Scope", "Retire", null]);
  });

  it("sends only changed fields, in the API's types", () => {
    const d = detail({ enabling_team: "DiY", applicable_to: "ETB" });
    expect(toPatch({ enabling_team: "DiY", applicable_to: ["ETB"], value_domain: "  Grid  ", expected_users: "1,200", strategic_kpis: "" }, d))
      .toEqual({ value_domain: "Grid", expected_users: 1200 });
    expect(toPatch({ applicable_to: ["ETB", "Group"], lead_id: 3 }, d)).toEqual({ applicable_to: ["ETB", "Group"] });
  });
});

describe("my use cases", () => {
  it("lists my use cases with their to-dos and marks what is not processed yet", async () => {
    mockApi({
      "/me/use-cases": [
        mine({ id: 7, name: "Grid check", todos: ["complete_details"] }),
        mine({ id: 8, name: "Shift planner", approval_status: "rejected", comment: "Align with HR first.", todos: ["revise_and_resubmit"] }),
        mine({ id: -3, name: "Fresh idea", approval_status: "pending", processing: "pending", provisional: true, roles: ["submitter"] }),
      ],
    });
    renderAt("/my");
    const attention = await screen.findByRole("region", { name: "Needs your attention" });
    expect(attention).toHaveTextContent("Rejected – revise and resubmit");
    expect(attention).toHaveTextContent("Approved – add the details");
    expect(within(attention).getByRole("link", { name: "Fill in Form 2" })).toHaveAttribute("href", "/use-cases/7");

    const table = screen.getByRole("table");
    expect(within(table).getByRole("link", { name: "Revise: Shift planner" })).toHaveAttribute("href", "/use-cases/8");
    const fresh = within(table).getByText("Fresh idea").closest("tr")!;
    expect(fresh).toHaveTextContent("Estimate pending");
    expect(fresh).toHaveTextContent("Pending");
    // the badge in the tab counts the open to-dos
    expect(screen.getByLabelText("2 to-dos")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Submitted by me 1" }));
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2); // header + Fresh idea
  });
});

describe("use case page", () => {
  it("asks for the scope gate date when the stage moves to PoC, then saves", async () => {
    mockApi({ "/use-cases/7": detail() });
    patch.mockReset();
    patch.mockImplementation((async () => detail({ stage: "PoC", scope_gate_date: "2026-02-10T00:00:00", last_gate: "Scope", processing: "changes_pending" })) as never);
    renderAt("/use-cases/7");
    const gates = await screen.findByRole("group", { name: "Stage gates" });
    // the needs gate is passed and stays fixed; the others can be dated
    expect(within(gates).getByText(/passed, fixed/)).toBeInTheDocument();
    expect(within(gates).queryByLabelText("Needs gate date")).not.toBeInTheDocument();

    const user = userEvent.setup();
    const track = screen.getByRole("radiogroup", { name: "Stage / maturity" });
    expect(within(track).getAllByRole("radio").map((r) => (r as HTMLInputElement).value)).toEqual(
      ["Idea", "Exploration", "PoC", "MVP", "Implementation", "Production", "Retired"]);
    await user.click(within(track).getByRole("radio", { name: "PoC" }));
    expect(within(gates).getByText("PoC needs the date the scope gate was passed.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();

    fireEvent.change(within(gates).getByLabelText("Scope gate date"), { target: { value: "2026-02-10" } });
    fireEvent.change(within(gates).getByLabelText("Deploy gate date"), { target: { value: "2030-06-01" } });
    await user.selectOptions(screen.getByRole("combobox", { name: "Which team enables the tech?" }), "EL.AI");
    await user.click(screen.getByRole("checkbox", { name: "50Hertz" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(patch).toHaveBeenCalledWith("/use-cases/7", {
      base_revision: "11-0", stage: "PoC", scope_gate_date: "2026-02-10", deploy_gate_date: "2030-06-01",
      enabling_team: "EL.AI", applicable_to: ["50Hertz"],
    });
    expect(await screen.findByText(/Saved\. The pipeline processes the changes/)).toBeInTheDocument();
    expect(screen.getByText(/latest changes are saved but not processed yet/)).toBeInTheDocument();
  });

  it("asks to move passed gates to the future when the stage goes back", async () => {
    mockApi({ "/use-cases/7": detail({ stage: "PoC", scope_gate_date: "2026-02-10T00:00:00", last_gate: "Scope" }) });
    renderAt("/use-cases/7");
    const gates = await screen.findByRole("group", { name: "Stage gates" });
    expect(within(gates).queryByLabelText("Scope gate date")).not.toBeInTheDocument(); // passed: fixed
    await userEvent.click(screen.getByRole("radio", { name: "Exploration" }));
    expect(within(gates).getByText(/the scope gate is not passed yet: move the date to the future/)).toBeInTheDocument();
    expect(within(gates).getByLabelText("Scope gate date")).toHaveValue("2026-02-10");
  });

  it("keeps the stage from form 1 as the lowest one", async () => {
    mockApi({ "/use-cases/7": detail({ stage: "MVP", stage_floor: "MVP", scope_gate_date: "2026-02-10T00:00:00", last_gate: "Scope" }) });
    renderAt("/use-cases/7");
    const track = await screen.findByRole("radiogroup", { name: "Stage / maturity" });
    expect(within(track).getByRole("radio", { name: /^PoC/ })).toBeDisabled();
    expect(within(track).getByRole("radio", { name: /^Exploration/ })).toBeDisabled();
    expect(within(track).getByRole("radio", { name: "Implementation" })).toBeEnabled();
    expect(screen.getByRole("radio", { name: "On hold" })).toBeEnabled();
  });

  it("shows a summary instead of editable idea fields, and fills in form 2 before the approval", async () => {
    mockApi({ "/use-cases/7": detail({ approval_status: "pending", description: "Checks the grid", drivers: { one_time_costs: 175000 }, todos: [] }) });
    patch.mockReset();
    patch.mockImplementation((async () => detail({ approval_status: "pending" })) as never);
    renderAt("/use-cases/7");
    const summary = await screen.findByRole("complementary", { name: "Summary" });
    expect(summary).toHaveTextContent("Checks the grid");
    expect(summary).toHaveTextContent("Potential per year");
    expect(screen.queryByRole("region", { name: /idea/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Description" })).not.toBeInTheDocument();
    await userEvent.type(screen.getByRole("textbox", { name: "Value domain" }), "Grid");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(patch).toHaveBeenCalledWith("/use-cases/7", { base_revision: "11-0", value_domain: "Grid" });
  });

  it("shows the server's message when someone else saved first", async () => {
    mockApi({ "/use-cases/7": detail() });
    patch.mockReset();
    patch.mockImplementation((async () => {
      throw { response: { status: 409, data: { detail: "The use case was changed in the meantime. Reload and try again." } } };
    }) as never);
    renderAt("/use-cases/7");
    await userEvent.type(await screen.findByRole("textbox", { name: "Value domain" }), "Grid");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("changed in the meantime");
  });

  it("lets the submitter revise and resubmit a rejected idea", async () => {
    mockApi({ "/use-cases/8": detail({ id: 8, name: "Shift planner", approval_status: "rejected", comment: "Align with HR first.", revision: "12-4", drivers: { one_time_costs: 200000 } }) });
    patch.mockReset();
    patch.mockImplementation((async () => detail({ id: 8, approval_status: "pending" })) as never);
    renderAt("/use-cases/8");
    expect(await screen.findByRole("note")).toHaveTextContent("Align with HR first.");
    const cost = screen.getByRole("combobox", { name: "One-time cost (estimate)" });
    expect(cost).toHaveDisplayValue("€ 200k entered – choose a range");
    await userEvent.selectOptions(cost, "250k €–1M €");
    await userEvent.click(screen.getByRole("button", { name: "Resubmit idea" }));
    expect(patch).toHaveBeenCalledWith("/use-cases/8", { base_revision: "12-4", one_time_costs: 500000, resubmit: true });
  });
});

describe("approvals", () => {
  it("is only in the tabs for approvers", async () => {
    mockApi({});
    renderAt("/my");
    await screen.findByRole("heading", { name: "My use cases" });
    expect(screen.queryByRole("link", { name: /Approvals/ })).not.toBeInTheDocument();
  });

  it("approves with a lead, or asks for a comment before rejecting", async () => {
    mockApi({
      "/auth/rights": { user: "Dev User", rights: { canApprove: true, canAdmin: false } },
      "/approvals": [inboxItem],
      "/use-cases/9": detail({ id: 9, name: "Vegetation risk", approval_status: "pending", needs_gate_date: null, last_gate: null, lead: null, can_decide: true, revision: "0-5", hypothetical_value_eur: 1000000, confidence_score: 0.6, delivery_score: 0.65, potential_value_eur: 390000 }),
    });
    post.mockReset();
    post.mockImplementation((async () => detail({ id: 9, approval_status: "approved" })) as never);
    renderAt("/approvals");
    expect(await screen.findByLabelText("1 waiting")).toBeInTheDocument();
    const panel = await screen.findByRole("region", { name: "Selected idea" });
    expect(await within(panel).findByText("€ 1,000k × 0.60 × 0.65", { exact: false })).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(within(panel).getByRole("button", { name: "Reject" }));
    expect(within(panel).getByText("Tell the submitter why it goes back.")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();

    // no date to enter: approving passes the needs gate today
    expect(within(panel).queryByLabelText(/Needs gate date/)).not.toBeInTheDocument();
    expect(within(panel).getByText("Approving passes the needs gate today.")).toBeInTheDocument();
    await user.selectOptions(within(panel).getByRole("combobox", { name: /Assign use case lead/ }), "3");
    await user.click(within(panel).getByRole("button", { name: "Approve & assign lead" }));
    expect(post).toHaveBeenCalledWith("/use-cases/9/decision", { decision: "approve", lead_id: 3, base_revision: "0-5" });
    expect(await screen.findByText(/was approved/)).toBeInTheDocument();
  });
});
