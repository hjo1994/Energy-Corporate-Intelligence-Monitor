import { make, SAMPLE } from "../test/fixtures";
import { applyFilters, EMPTY_FILTERS, NO_BUSINESS_UNIT, sortInitiatives, summarize, businessUnitsIn } from "./filters";
import { formatQuarter, initials, scoreBars } from "./format";
import { layoutDots } from "./matrix";

describe("filters", () => {
  it("combines business unit, status and search; empty filters keep everything", () => {
    expect(applyFilters(SAMPLE, EMPTY_FILTERS)).toHaveLength(4);
    expect(applyFilters(SAMPLE, { ...EMPTY_FILTERS, businessUnits: ["ETB"] }).map((i) => i.name)).toEqual(["Alpha", "Beta"]);
    expect(applyFilters(SAMPLE, { ...EMPTY_FILTERS, statuses: ["Idea"], businessUnits: ["IT"] }).map((i) => i.name)).toEqual(["Gamma"]);
    expect(applyFilters(SAMPLE, { ...EMPTY_FILTERS, search: "AUTOMAT" }).map((i) => i.name)).toEqual(["Alpha"]);
  });

  it("treats initiatives without owner as their own business unit", () => {
    expect(applyFilters(SAMPLE, { ...EMPTY_FILTERS, businessUnits: [NO_BUSINESS_UNIT] }).map((i) => i.name)).toEqual(["Delta"]);
    expect(businessUnitsIn(SAMPLE)).toEqual(["ETB", "IT", NO_BUSINESS_UNIT]);
  });

  it("sorts missing values last in both directions", () => {
    expect(sortInitiatives(SAMPLE, "value", "desc").map((i) => i.name)).toEqual(["Alpha", "Beta", "Gamma", "Delta"]);
    expect(sortInitiatives(SAMPLE, "value", "asc").map((i) => i.name)).toEqual(["Beta", "Alpha", "Gamma", "Delta"]);
  });

  it("summarizes without counting missing scores as zero", () => {
    expect(summarize(SAMPLE)).toMatchObject({ total: 4, inProgress: 1, withValue: 2, withoutValue: 2, averageValue: 6.5 });
    expect(summarize([]).averageValue).toBeNull();
  });
});

describe("format", () => {
  it("derives initials", () => {
    expect(initials("Anna Beispiel")).toBe("AB");
    expect(initials("EDT")).toBe("ED");
    expect(initials("  ")).toBe("?");
  });
  it("maps scores to 0-5 bars, none for a missing score", () => {
    expect([null, 1, 3, 5, 7, 9, 10].map(scoreBars)).toEqual([0, 1, 2, 3, 4, 5, 5]);
  });
  it("shows quarters without time-zone shifts", () => {
    expect(formatQuarter("2026-01-01T00:00:00")).toBe("Q1 2026");
    expect(formatQuarter("2026-10-01T00:00:00")).toBe("Q4 2026");
    expect(formatQuarter(null)).toBe("–");
  });
});

describe("matrix layout", () => {
  it("plots only initiatives with both scores", () => {
    expect(layoutDots(SAMPLE).map((d) => d.initiative.name)).toEqual(["Alpha", "Beta"]);
  });
  it("puts high value at the top and keeps identical scores apart", () => {
    const [a, b] = layoutDots(SAMPLE);
    expect(a.y).toBeLessThan(b.y);
    const twins = layoutDots([1, 2, 3].map((id) => make({ id, name: `T${id}`, value_score: 5, solution_complexity_score: 5 })));
    const spots = new Set(twins.map((d) => `${d.dx},${d.dy}`));
    expect(spots.size).toBe(3);
  });
});

import { cleanPage } from "../api/client";
import { flagshipLabel } from "./format";

describe("display cleanup", () => {
  it("strips zero-width characters from catalog names but keeps everything else", () => {
    const page = cleanPage({
      items: [make({ id: 1, name: "X", value_type: { id: 1, name: "Connection lif﻿ecycle", description: "d" } })],
      total: 1, limit: 1, offset: 0,
    });
    expect(page.items[0].value_type).toEqual({ id: 1, name: "Connection lifecycle", description: "d" });
  });
  it("labels the catalog's literal '-' flagship", () => {
    expect(flagshipLabel("-")).toBe("No flagship");
    expect(flagshipLabel("CAPEX delivery")).toBe("CAPEX delivery");
  });
});
