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
    expect(within(top).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "1AlphaETB · Idea54 k€",
      "2BetaETB · PoC5 k€",
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
    mockApi(() => (++calls === 1 ? failWith(503)() : ok()));
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
