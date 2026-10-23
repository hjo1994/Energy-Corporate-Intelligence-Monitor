import { make, SAMPLE } from "../test/fixtures";
import { applyFilters, EMPTY_FILTERS, NO_BUSINESS_UNIT, sortInitiatives, summarize, businessUnitsIn } from "./filters";
import { formatEur, formatQuarter, initials, scoreBars, valueFraction } from "./format";
import { layoutDots } from "./matrix";

describe("filters", () => {
  it("combines business unit, stage and search; empty filters keep everything", () => {
    expect(applyFilters(SAMPLE, EMPTY_FILTERS)).toHaveLength(4);
    expect(applyFilters(SAMPLE, { ...EMPTY_FILTERS, businessUnits: ["ETB"] }).map((i) => i.name)).toEqual(["Alpha", "Beta"]);
    expect(applyFilters(SAMPLE, { ...EMPTY_FILTERS, stages: ["Idea"], businessUnits: ["IT"] }).map((i) => i.name)).toEqual(["Gamma"]);
    expect(applyFilters(SAMPLE, { ...EMPTY_FILTERS, search: "AUTOMAT" }).map((i) => i.name)).toEqual(["Alpha"]);
  });

  it("treats initiatives without owner as their own business unit", () => {
    expect(applyFilters(SAMPLE, { ...EMPTY_FILTERS, businessUnits: [NO_BUSINESS_UNIT] }).map((i) => i.name)).toEqual(["Delta"]);
    expect(businessUnitsIn(SAMPLE)).toEqual(["ETB", "IT", NO_BUSINESS_UNIT]);
  });

  it("sorts missing values last in both directions", () => {
    expect(sortInitiatives(SAMPLE, "potential", "desc").map((i) => i.name)).toEqual(["Alpha", "Gamma", "Beta", "Delta"]);
    expect(sortInitiatives(SAMPLE, "potential", "asc").map((i) => i.name)).toEqual(["Beta", "Gamma", "Alpha", "Delta"]);
    expect(sortInitiatives(SAMPLE, "risk", "desc")[0].name).toBe("Alpha");
  });

  it("summarizes without counting missing estimates as zero", () => {
    expect(summarize(SAMPLE)).toMatchObject({
      total: 4, inProgress: 1, withPotential: 3, totalPotential: 78550, totalAnnualCost: 61500, elevatedRisk: 1,
    });
    expect(summarize([]).totalPotential).toBeNull();
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
  it("rounds money and marks it as an estimate", () => {
    expect(formatEur(null)).toBe("–");
    expect(formatEur(457380)).toBe("≈ 457k €");
    expect(formatEur(1452000)).toBe("≈ 1.5 M €");
    expect(formatEur(39794000)).toBe("≈ 40 M €");
    expect(formatEur(950)).toBe("≈ 950 €");
  });
  it("maps potential onto a clamped log scale", () => {
    expect([500, 1000, 31623, 1_000_000, 5_000_000].map((v) => Math.round(valueFraction(v) * 100))).toEqual([0, 0, 50, 100, 100]);
  });
  it("shows quarters without time-zone shifts", () => {
    expect(formatQuarter("2026-01-01T00:00:00")).toBe("Q1 2026");
    expect(formatQuarter("2026-10-01T00:00:00")).toBe("Q4 2026");
    expect(formatQuarter(null)).toBe("–");
  });
});

describe("matrix layout", () => {
  it("plots only initiatives with effort and potential", () => {
    expect(layoutDots(SAMPLE).map((d) => d.initiative.name)).toEqual(["Alpha", "Beta"]);
  });
  it("puts high potential at the top and keeps identical scores apart", () => {
    const [a, b] = layoutDots(SAMPLE);
    expect(a.y).toBeLessThan(b.y);
    const twins = layoutDots([1, 2, 3].map((id) => make({ id, name: `T${id}`, potential_value_eur: 5000, solution_complexity_score: 5 })));
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

import { flagshipStats } from "./flagship";

describe("flagship statistics", () => {
  const vt = (id: number, name: string) => ({ id, name, description: null });
  const items = [
    make({ id: 1, name: "a", value_type: vt(1, "CAPEX delivery"), potential_value_eur: 8000 }),
    make({ id: 2, name: "b", value_type: vt(1, "CAPEX delivery"), potential_value_eur: 4000 }),
    make({ id: 3, name: "c", value_type: vt(1, "CAPEX delivery"), potential_value_eur: null }),
    make({ id: 4, name: "d", value_type: vt(2, "-"), potential_value_eur: 3000 }),
    make({ id: 5, name: "e", value_type: vt(3, "Grid planning process") }),
    make({ id: 6, name: "f", value_type: vt(3, "Grid planning process") }),
    make({ id: 7, name: "g", value_type: null, potential_value_eur: 9000 }),
  ];
  const stats = flagshipStats(items);

  it("counts per flagship and sums only the initiatives that have an estimate", () => {
    const capex = stats.find((s) => s.key === "CAPEX delivery")!;
    expect(capex).toMatchObject({ count: 3, estimated: 2, totalPotential: 12000 });
  });

  it("does not turn a missing estimate into zero", () => {
    expect(stats.find((s) => s.key === "Grid planning process")).toMatchObject({ count: 2, estimated: 0, totalPotential: null });
  });

  it("keeps the catalog's '-' as 'No flagship' and lists unassigned initiatives so the counts add up", () => {
    expect(stats.find((s) => s.key === "-")?.label).toBe("No flagship");
    expect(stats.find((s) => s.key === "")).toMatchObject({ label: "Not assigned", count: 1 });
    expect(stats.reduce((n, s) => n + s.count, 0)).toBe(items.length);
  });

  it("sorts by size and puts the unassigned group last", () => {
    expect(stats.map((s) => s.label)).toEqual(["CAPEX delivery", "Grid planning process", "No flagship", "Not assigned"]);
  });

  it("is empty for no initiatives", () => {
    expect(flagshipStats([])).toEqual([]);
  });
});
