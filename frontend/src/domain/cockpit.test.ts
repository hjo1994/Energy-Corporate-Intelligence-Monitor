import type { Initiative } from "../api/types";
import { make } from "../test/fixtures";
import { cockpit, formatKEur, formatMEur, formatTick, logPosition, valueMatrix } from "./cockpit";

const unit = (category: string | null) => (category ? { id: 1, name: "O", department: null, category } : null);

function valued(id: number, potential: number, cost: number, over: Partial<Initiative> = {}): Initiative {
  return make({
    id,
    name: `I${id}`,
    efficiency_score_eur: potential,
    confidence_score: 1,
    delivery_score: 1,
    hypothetical_value_eur: potential,
    potential_value_eur: potential,
    annual_cost_eur: cost,
    ...over,
  });
}

const TODAY = new Date(2026, 9, 25); // Q4 2026 -> scheduled by Q1 2027

describe("cockpit", () => {
  const items = [
    valued(1, 500_000, 100_000, { stage: "Production", owner: unit("ETB"), date_delivery: "2026-04-01T00:00:00" }),
    valued(2, 200_000, 300_000, { stage: "Implementation", owner: unit("50Hertz"), date_delivery: "2027-01-01T00:00:00" }),
    valued(3, 300_000, 50_000, { stage: "Idea", owner: null, date_delivery: "2027-04-01T00:00:00" }),
    make({ id: 4, name: "unvalued", potential_value_eur: 90_000 }),
  ];

  it("sums potential and net over the valued initiatives", () => {
    const c = cockpit(items, TODAY);
    expect(c).toMatchObject({ total: 4, valued: 3, potential: 1_000_000, net: 550_000, selfFunding: 2 });
  });

  it("counts Implementation and Production as delivering today", () => {
    expect(cockpit(items, TODAY).live).toBe(700_000);
  });

  it("schedules up to the end of the next quarter", () => {
    expect(cockpit(items, TODAY).scheduled).toEqual({ until: "Q1 2027", potential: 700_000 });
    expect(cockpit(items, new Date(2026, 11, 31)).scheduled.until).toBe("Q1 2027");
    expect(cockpit(items, new Date(2027, 0, 1)).scheduled).toEqual({ until: "Q2 2027", potential: 1_000_000 });
  });

  it("splits the value by business unit, biggest first, and by driver", () => {
    const c = cockpit(items, TODAY);
    expect(c.byBusinessUnit).toEqual([
      { label: "ETB", potential: 500_000 },
      { label: "No business unit", potential: 300_000 },
      { label: "50Hertz", potential: 200_000 },
    ]);
    expect(c.drivers.map((d) => d.potential)).toEqual([1_000_000, 0, 0, 0]);
  });
});

describe("valueMatrix", () => {
  const items = Array.from({ length: 12 }, (_, k) =>
    make({ id: k + 1, name: `I${k + 1}`, potential_value_eur: (k + 1) * 10_000, solution_complexity_score: k === 0 ? 12 : 3 }),
  ).concat([make({ id: 99, name: "no effort", potential_value_eur: 220_000 })]);

  it("ranks the ten most valuable plotted initiatives", () => {
    const m = valueMatrix(items);
    expect(m.top.map((p) => p.initiative.id)).toEqual([12, 11, 10, 9, 8, 7, 6, 5, 4, 3]);
    expect(m.points.filter((p) => p.rank === null).map((p) => p.initiative.id)).toEqual([2, 1]);
  });

  it("states how much of the potential has an effort estimate", () => {
    const m = valueMatrix(items);
    expect(m).toMatchObject({ estimated: 13, plotted: 12 });
    expect(m.coverage).toBeCloseTo(780_000 / 1_000_000);
  });

  it("clamps effort to 1..9 and spans the axis by decades around the 100k split", () => {
    const m = valueMatrix(items);
    expect(m.points.find((p) => p.initiative.id === 1)?.effort).toBe(9);
    expect([m.min, m.max]).toEqual([10_000, 1_000_000]);
    expect(valueMatrix([make({ id: 1, name: "a", potential_value_eur: 2_500, solution_complexity_score: 1 })]).min).toBe(1_000);
  });

  it("places potentials on a log axis", () => {
    expect(logPosition(100_000, 10_000, 1_000_000)).toBeCloseTo(0.5);
    expect(logPosition(5, 10_000, 1_000_000)).toBe(0);
  });
});

describe("labels", () => {
  it("formats in English", () => {
    expect(formatMEur(9_812_000)).toBe("9.8 M€");
    expect(formatMEur(2_700_000, true)).toBe("+2.7 M€");
    expect(formatKEur(1_061_400)).toBe("1,061 k€");
    expect([1_000, 100_000, 1_000_000].map(formatTick)).toEqual(["1k", "100k", "1M"]);
  });
});
