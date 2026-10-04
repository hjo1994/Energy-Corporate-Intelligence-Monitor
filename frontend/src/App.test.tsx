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
    expect(await screen.findByText("Aufwand vs. Mehrwert")).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "" })).toHaveTextContent("2 von 4 Initiativen sind nicht eingezeichnet");
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
    await userEvent.click(screen.getByRole("button", { name: "Ohne Business Unit" }));
    expect(screen.getByRole("region", { name: "Cancelled" })).toHaveTextContent("Delta");
    expect(screen.queryByText("Alpha")).not.toBeInTheDocument();
  });

  it("list sorts and opens a detail dialog that closes on Escape", async () => {
    mockApi(ok);
    renderAt("/liste");
    await userEvent.click(await screen.findByRole("button", { name: "Beta" }));
    expect(screen.getByRole("dialog", { name: "Beta" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("explains a 503 and can retry", async () => {
    let calls = 0;
    mockApi(() => (++calls === 1 ? failWith(503)() : ok()));
    renderAt("/");
    expect(await screen.findByRole("alert")).toHaveTextContent("nicht erreichbar");
    await userEvent.click(screen.getByRole("button", { name: "Erneut versuchen" }));
    expect(await screen.findByText("Aufwand vs. Mehrwert")).toBeInTheDocument();
  });
});

describe("api errors", () => {
  it.each([
    [401, "angemeldet"],
    [403, "Berechtigung"],
    [500, "HTTP 500"],
    [undefined, "nicht erreichbar"],
  ])("explains status %s", async (status, text) => {
    mockApi(failWith(status));
    renderAt("/");
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
  });

  it("asks the backend for the whole data set page by page", async () => {
    mockApi(ok);
    renderAt("/");
    await screen.findByText("Aufwand vs. Mehrwert");
    expect(get).toHaveBeenCalledWith("/initiatives", { limit: 500, offset: 0, sort: "name" });
  });
});
