import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import { SAMPLE } from "./test/fixtures";

import { serviceApi } from "./shared/api/serviceApi";

// ServiceApi (axios) is replaced: tests must not depend on the internal package's behaviour.
vi.mock("./shared/api/serviceApi", () => ({ serviceApi: { get: vi.fn(), post: vi.fn() } }));

const get = vi.mocked(serviceApi.get);
const post = vi.mocked(serviceApi.post);
const ok = async () => ({ items: SAMPLE, total: SAMPLE.length, limit: 500, offset: 0 });
const failWith = (status?: number) => async () => {
  throw status === undefined ? new Error("Network Error") : { response: { status } };
};
function mockApi(impl: () => Promise<unknown>) {
  get.mockReset();
  get.mockImplementation(impl as never);
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}


describe("app", () => {
  it("opens on the value cockpit with the estimated value and the top initiatives", async () => {
    mockApi(ok);
    renderAt("/");
    const hero = await screen.findByRole("region", { name: "Estimated value" });
    expect(hero).toHaveTextContent("Our 4 AI initiatives are estimated to create");
    // only Alpha has potential and cost estimated: 54k potential - 44k cost
    expect(hero).toHaveTextContent("0.1 M€per year, net +0.0 M€ after costs");
    expect(hero).toHaveTextContent("1 / 1cover their own costs");

    const matrix = screen.getByRole("region", { name: "Where the value lies" });
    expect(matrix).toHaveTextContent("2 of 3 initiatives have an effort estimate, covering 75 % of the potential.");
    const top = within(matrix).getByRole("list", { name: "Top 10 by potential" });
    expect(within(top).getByLabelText("Risk level 3: Medium risk (estimated)")).toHaveTextContent("3");
    expect(within(top).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "1AlphaETB · Idea354 k€",
      "2BetaETB · PoC15 k€",
    ]);
  });

  it("a click on a row or a dot highlights the initiative in both", async () => {
    mockApi(ok);
    renderAt("/");
    const matrix = await screen.findByRole("region", { name: "Where the value lies" });
    const row = within(matrix).getByRole("button", { name: /^2Beta/ });
    const dot = within(matrix).getByRole("button", { name: "#2 Beta" });
    await userEvent.click(row);
    expect(row).toHaveAttribute("aria-pressed", "true");
    expect(dot).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(dot);
    expect(row).toHaveAttribute("aria-pressed", "false");
  });

  it("shows value by business unit and by value driver", async () => {
    mockApi(ok);
    renderAt("/");
    expect(await screen.findByRole("region", { name: "Value by business unit" })).toHaveTextContent("ETB0.1 M€");
    expect(screen.getByRole("region", { name: "What drives the value" })).toHaveTextContent(
      "Efficiency0.0 M€Quality0.0 M€Risk reduction0.0 M€Strategic0.0 M€",
    );
  });

  it("keeps the filter chips and key figures on the start page; the cockpit follows the filters", async () => {
    mockApi(ok);
    renderAt("/");
    const kpis = await screen.findByRole("region", { name: "Key figures" });
    expect(kpis).toHaveTextContent("4matching the filters");
    await userEvent.click(screen.getByRole("button", { name: "IT" }));
    expect(kpis).toHaveTextContent("1matching the filters");
    expect(screen.getByRole("region", { name: "Estimated value" })).toHaveTextContent("Our 1 AI initiatives");
    expect(screen.getByRole("region", { name: "Where the value lies" })).toHaveTextContent("0 of 1 initiatives have an effort estimate");
  });

  it("redirects the former value tab to the start page", async () => {
    mockApi(ok);
    renderAt("/value");
    expect(await screen.findByRole("region", { name: "Estimated value" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Value" })).not.toBeInTheDocument();
  });

  it("filters by business unit across views and keeps them in sync", async () => {
    mockApi(ok);
    renderAt("/board");
    await screen.findByRole("region", { name: "Idea" });
    await userEvent.click(screen.getByRole("button", { name: "No business unit" }));
    expect(screen.getByRole("region", { name: "Cancelled" })).toHaveTextContent("Delta");
    expect(screen.queryByText("Alpha")).not.toBeInTheDocument();
  });

  it("list sorts and opens a detail dialog that closes on Escape", async () => {
    mockApi(ok);
    renderAt("/list");
    await userEvent.click(await screen.findByRole("button", { name: "Beta" }));
    expect(screen.getByRole("dialog", { name: "Beta" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("explains a 503 and can retry", async () => {
    let calls = 0;
    get.mockReset();
    get.mockImplementation(((path: string) =>
      path === "/features" ? Promise.resolve({ initiative_input: false }) : ++calls === 1 ? failWith(503)() : ok()) as never);
    renderAt("/");
    expect(await screen.findByRole("alert")).toHaveTextContent("unavailable");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("region", { name: "Estimated value" })).toBeInTheDocument();
  });
});

describe("api errors", () => {
  it.each([
    [401, "not signed in"],
    [403, "permission"],
    [500, "HTTP 500"],
    [undefined, "cannot be reached"],
  ])("explains status %s", async (status, text) => {
    mockApi(failWith(status));
    renderAt("/");
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
  });

  it("asks the backend for the whole data set page by page", async () => {
    mockApi(ok);
    renderAt("/");
    await screen.findByRole("region", { name: "Estimated value" });
    expect(get).toHaveBeenCalledWith("/initiatives", { limit: 500, offset: 0, sort: "name" });
  });
});

describe("new initiative form", () => {
  const owners = [
    { id: 1, name: "Owner A", department: "Assets", category: "ETB" },
    { id: 2, name: "Owner B", department: "Innovation", category: "IT" },
  ];
  const valueTypes = [{ id: 1, name: "CAPEX delivery", description: null }];
  const solutionTypes = [{ id: 1, name: "Custom agent", description: null }];

  function mockWithReference() {
    get.mockReset();
    get.mockImplementation((async (path: string) => {
      if (path === "/owners") return owners;
      if (path === "/value-types") return valueTypes;
      if (path === "/solution-types") return solutionTypes;
      if (path === "/features") return { initiative_input: true };
      return { items: SAMPLE, total: SAMPLE.length, limit: 500, offset: 0 };
    }) as never);
  }

  async function fillRequired() {
    const user = userEvent.setup();
    await user.type(await screen.findByRole("textbox", { name: /^Name/ }), "Smart Invoice Check");
    await user.type(screen.getByRole("textbox", { name: /^Description/ }), "Checks invoices against orders");
    await user.selectOptions(screen.getByRole("combobox", { name: /^Business unit/ }), "ETB");
    await user.selectOptions(screen.getByRole("combobox", { name: /^Owner/ }), "1");
    await user.selectOptions(screen.getByRole("combobox", { name: /^Flagship/ }), "1");
    await user.selectOptions(screen.getByRole("combobox", { name: /^Solution type/ }), "1");
    await user.selectOptions(screen.getByRole("combobox", { name: /^Stage/ }), "Idea");
    await user.type(screen.getByRole("textbox", { name: /^Cases per year/ }), "3000");
    await user.type(screen.getByRole("textbox", { name: /^Hours saved per case/ }), "0.5");
    await user.selectOptions(screen.getByRole("combobox", { name: /^Complexity/ }), "4");
    await user.type(screen.getByRole("textbox", { name: /^One-time cost/ }), "200000");
    await user.type(screen.getByRole("textbox", { name: /^Operating cost/ }), "50000");
    await user.click(screen.getByRole("radio", { name: "Benchmark" }));
    return user;
  }

  it("previews value and risk live and refuses to save an incomplete form", async () => {
    mockWithReference();
    renderAt("/new");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Save initiative" }));
    expect(screen.getByText("Enter a name.")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();

    await fillRequired();
    const preview = screen.getByRole("complementary", { name: "Estimate preview" });
    // 3,000 x 0.5 h x 60 € = 90k; x 0.60 x 0.65 = 35k; cost 200k x 0.65 / 5 + 50k x 0.65 = 59k
    expect(preview).toHaveTextContent("Potential per year35k €");
    expect(preview).toHaveTextContent("Expected cost per year59k €");
    expect(preview).toHaveTextContent("1 · Very low risk");
    await user.click(screen.getByRole("radio", { name: "Prepares" }));
    expect(preview).toHaveTextContent("3 · Medium risk");
  });

  it("saves, returns to the cockpit and shows the new initiative as pending", async () => {
    mockWithReference();
    post.mockReset();
    post.mockImplementation((async (_path: string, body: Record<string, unknown>) => ({
      ...SAMPLE[0], id: -1, user_input_id: 1, status: "pending", business_transaction_id: null,
      name: body.name as string,
    })) as never);
    renderAt("/new");
    const user = await fillRequired();
    await user.click(screen.getByRole("button", { name: "Save initiative" }));

    expect(post).toHaveBeenCalledWith("/initiatives", expect.objectContaining({
      name: "Smart Invoice Check", owner_id: 1, cases_per_year: 3000, hours_saved_per_case: 0.5,
      error_rate_before: null, estimate_basis: "benchmark", solution_complexity_score: 4,
      one_time_costs: 200000, decisions_on_employees: "none",
    }));
    expect(await screen.findByRole("status")).toHaveTextContent("“Smart Invoice Check” was saved. Its estimate is pending");
    expect(screen.getByRole("region", { name: "Key figures" })).toHaveTextContent("5matching the filters");
  });

  it("shows the server's message for a duplicate name", async () => {
    mockWithReference();
    post.mockReset();
    post.mockImplementation((async () => {
      throw { response: { status: 409, data: { detail: "An initiative named “Alpha” already exists in ETB." } } };
    }) as never);
    renderAt("/new");
    const user = await fillRequired();
    await user.click(screen.getByRole("button", { name: "Save initiative" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already exists in ETB");
  });
});

describe("feature switch", () => {
  it("hides the input form when the backend switches it off", async () => {
    get.mockReset();
    get.mockImplementation((async (path: string) =>
      path === "/features" ? { initiative_input: false } : { items: SAMPLE, total: SAMPLE.length, limit: 500, offset: 0 }) as never);
    renderAt("/new");
    expect(await screen.findByRole("region", { name: "Estimated value" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "+ New initiative" })).not.toBeInTheDocument();
  });

  it("shows the button when it is on", async () => {
    get.mockReset();
    get.mockImplementation((async (path: string) =>
      path === "/features" ? { initiative_input: true } : { items: SAMPLE, total: SAMPLE.length, limit: 500, offset: 0 }) as never);
    renderAt("/");
    expect(await screen.findByRole("link", { name: "+ New initiative" })).toBeInTheDocument();
  });
});
