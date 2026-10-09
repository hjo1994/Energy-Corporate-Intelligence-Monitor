import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import { SAMPLE } from "./test/fixtures";

import { serviceApi } from "./shared/api/serviceApi";

// ServiceApi (axios) is replaced: tests must not depend on the internal package's behaviour.
vi.mock("./shared/api/serviceApi", () => ({ serviceApi: { get: vi.fn() } }));

const get = vi.mocked(serviceApi.get);
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
  it("shows KPIs and flags initiatives that cannot be plotted", async () => {
    mockApi(ok);
    renderAt("/");
    expect(await screen.findByText("Effort vs. value")).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "" })).toHaveTextContent("2 of 4 initiatives are not plotted");
    expect(screen.getAllByRole("button", { name: /, (Idea|PoC)$/ })).toHaveLength(2);
  });

  it("selecting a dot shows its details; missing owner is stated, not hidden", async () => {
    mockApi(ok);
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Alpha, Idea" }));
    const panel = screen.getByRole("complementary", { name: "Details" });
    expect(within(panel).getByText("Alpha")).toBeInTheDocument();
    expect(within(panel).getByText("CAPEX delivery")).toBeInTheDocument();
    expect(within(panel).getByText("Q3 2026")).toBeInTheDocument();
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
    mockApi(() => (++calls === 1 ? failWith(503)() : ok()));
    renderAt("/");
    expect(await screen.findByRole("alert")).toHaveTextContent("unavailable");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Effort vs. value")).toBeInTheDocument();
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
    await screen.findByText("Effort vs. value");
    expect(get).toHaveBeenCalledWith("/initiatives", { limit: 500, offset: 0, sort: "name" });
  });
});

describe("flagship widget", () => {
  it("shows counts and average value per flagship, including the unassigned group", async () => {
    mockApi(ok);
    renderAt("/");
    const widget = await screen.findByRole("region", { name: "Flagships" });
    expect(within(widget).getByRole("button", { name: /CAPEX delivery/ })).toHaveTextContent("1 · avg. 8.0 (1 of 1 rated)");
    expect(within(widget).getByRole("button", { name: /Not assigned/ })).toHaveTextContent("3 · avg. 5.0 (1 of 3 rated)");
  });

  it("filters by the clicked flagship while keeping the other rows visible to switch back", async () => {
    mockApi(ok);
    renderAt("/");
    const widget = await screen.findByRole("region", { name: "Flagships" });
    await userEvent.click(within(widget).getByRole("button", { name: /CAPEX delivery/ }));

    expect(screen.getByRole("region", { name: "Key figures" })).toHaveTextContent("1matching the filters");
    expect(within(widget).getByRole("button", { name: /CAPEX delivery/ })).toHaveAttribute("aria-pressed", "true");
    expect(within(widget).getByRole("button", { name: /Not assigned/ })).toBeInTheDocument();

    await userEvent.click(within(widget).getByRole("button", { name: /CAPEX delivery/ }));
    expect(screen.getByRole("region", { name: "Key figures" })).toHaveTextContent("4matching the filters");
  });

  it("follows the other filters (business unit)", async () => {
    mockApi(ok);
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "IT" }));
    const widget = screen.getByRole("region", { name: "Flagships" });
    expect(within(widget).queryByRole("button", { name: /CAPEX delivery/ })).not.toBeInTheDocument();
    expect(within(widget).getByRole("button", { name: /Not assigned/ })).toHaveTextContent("1 · no value rated");
  });
});
