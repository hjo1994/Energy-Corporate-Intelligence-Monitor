import type { Initiative } from "../api/types";
import { make } from "../test/fixtures";
import {
  breakEvenPoints,
  breakEvenStats,
  costIfDelivered,
  formatMillions,
  formatSignedEur,
  niceMax,
  stageGroupOf,
  valueBridge,
  valueRoadmap,
  waterfallSteps,
} from "./value";

// Fully estimated initiative: buckets, factors and costs as the backend derives them.
function valued(
  id: number,
  buckets: [number, number, number, number],
  confidence: number,
  delivery: number,
  cost: number,
  over: Partial<Initiative> = {},
): Initiative {
  const hypothetical = buckets.reduce((a, b) => a + b, 0);
  return make({
    id,
    name: `I${id}`,
    efficiency_score_eur: buckets[0],
    quality_score_eur: buckets[1],
    risk_reduction_score_eur: buckets[2],
    strategic_value_score_eur: buckets[3],
    confidence_score: confidence,
    delivery_score: delivery,
    hypothetical_value_eur: hypothetical,
    potential_value_eur: hypothetical * confidence * delivery,
    annual_cost_eur: cost,
    ...over,
  });
}

// potential 54,000, cost 44,000 -> net +10,000
const a = valued(1, [10_000, 20_000, 30_000, 40_000], 0.6, 0.9, 44_000);
// potential 4,550, cost 17,500 -> net -12,950
const b = valued(2, [5_000, 5_000, 5_000, 5_000], 0.35, 0.65, 17_500);
// potential 21,000, cost 44,000 -> net -23,000
const c = valued(3, [60_000, 0, 0, 0], 0.35, 1, 44_000);
const unestimated = make({ id: 4, name: "Unestimated" });

describe("value bridge", () => {
  const bridge = valueBridge([a, b, c, unestimated]);

  it("only counts initiatives with potential and cost, and says how many are left out", () => {
    expect(bridge.total).toBe(4);
    expect(bridge.valued).toBe(3);
  });

  it("splits the hypothetical value into haircuts that add up to the potential", () => {
    expect(bridge.hypothetical).toBe(180_000);
    // 100k x 0.4 + 20k x 0.65 + 60k x 0.65
    expect(bridge.confidenceHaircut).toBeCloseTo(92_000);
    // 100k x 0.6 x 0.1 + 20k x 0.35 x 0.35 + 0
    expect(bridge.deliveryHaircut).toBeCloseTo(8_450);
    expect(bridge.potential).toBeCloseTo(79_550);
    expect(bridge.hypothetical - bridge.confidenceHaircut - bridge.deliveryHaircut).toBeCloseTo(bridge.potential);
    expect(bridge.annualCost).toBe(105_500);
    expect(bridge.net).toBeCloseTo(-25_950);
  });

  it("separates net positive from net negative initiatives", () => {
    expect(bridge.positive.count).toBe(1);
    expect(bridge.positive.net).toBeCloseTo(10_000);
    expect(bridge.negative.count).toBe(2);
    expect(bridge.negative.net).toBeCloseTo(-35_950);
    expect(bridge.lowestConfidence).toEqual({ value: 0.35, count: 2 });
  });

  it("splits the potential per bucket", () => {
    const byLabel = Object.fromEntries(bridge.buckets.map((x) => [x.label, x.potential]));
    expect(byLabel.Efficiency).toBeCloseTo(10_000 * 0.54 + 5_000 * 0.2275 + 60_000 * 0.35);
    expect(byLabel.Strategic).toBeCloseTo(40_000 * 0.54 + 5_000 * 0.2275);
    expect(bridge.buckets.reduce((s, x) => s + x.potential, 0)).toBeCloseTo(bridge.potential);
  });

  it("builds the waterfall down to a negative net", () => {
    const steps = waterfallSteps(bridge);
    expect(steps.map((s) => s.label)).toEqual([
      "Hypothetical", "Confidence", "Delivery", "Potential", "Cost / year", "Net / year",
    ]);
    expect(steps[2].to).toBeCloseTo(steps[3].to); // the delivery step ends at the potential
    expect(steps[4].to).toBeCloseTo(steps[5].to); // the cost step ends at the net
    expect(steps[5].to).toBeLessThan(0);
  });

  it("is all zero without any estimate", () => {
    const empty = valueBridge([unestimated]);
    expect(empty.valued).toBe(0);
    expect(empty.net).toBe(0);
    expect(empty.lowestConfidence).toBeNull();
  });
});

describe("break-even map", () => {
  it("groups stages and keeps the jitter small and deterministic", () => {
    expect(["Ideation", "PoC", "MVP", "Implementation", "Production", "On hold", "Cancelled", "Unknown"]
      .map(stageGroupOf)).toEqual(["early", "test", "test", "live", "live", "other", "other", "other"]);
    const points = breakEvenPoints([a, b, c, unestimated]);
    expect(points.map((p) => p.initiative.id)).toEqual([1, 2, 3]);
    expect(points.every((p) => Math.abs(p.jitter) <= 8)).toBe(true);
    expect(breakEvenPoints([a])[0].jitter).toBe(points[0].jitter);
  });

  it("counts initiatives above break-even and the net sum", () => {
    expect(breakEvenStats(breakEvenPoints([a, b, c]))).toEqual({ total: 3, above: 1, net: expect.closeTo(-25_950) });
    expect(breakEvenStats([])).toEqual({ total: 0, above: 0, net: 0 });
  });

  it("rounds axis maxima up to whole steps", () => {
    expect(niceMax(583_333)).toBe(600_000);
    expect(niceMax(400_000)).toBe(400_000);
    expect(niceMax(0)).toBe(100_000);
    expect(niceMax(2_580_000, 500_000)).toBe(3_000_000);
  });
});

describe("value roadmap", () => {
  const items = [
    valued(1, [100_000, 0, 0, 0], 1, 1, 0, { date_delivery: "2026-04-01T00:00:00", owner: { id: 1, name: "A", department: null, category: "ETB" } }),
    valued(2, [50_000, 0, 0, 0], 1, 1, 0, { date_delivery: "2026-05-01T00:00:00", owner: { id: 1, name: "A", department: null, category: "ETB" } }),
    valued(3, [25_000, 0, 0, 0], 1, 1, 0, { date_delivery: "2027-01-01T00:00:00" }),
    valued(4, [200_000, 0, 0, 0], 1, 1, 0, { owner: { id: 2, name: "B", department: null, category: "IT" } }),
    unestimated,
  ];
  const r = valueRoadmap(items);

  it("sums potential per delivery quarter and fills empty quarters", () => {
    expect(r.quarters.map((q) => [q.label, q.potential, q.count])).toEqual([
      ["Q2 2026", 150_000, 2],
      ["Q3 2026", 0, 0],
      ["Q4 2026", 0, 0],
      ["Q1 2027", 25_000, 1],
    ]);
    expect(r.quarters.map((q) => q.cumulative)).toEqual([150_000, 150_000, 150_000, 175_000]);
  });

  it("reports what has no delivery date and which business units date nothing", () => {
    expect(r.undated).toEqual({ potential: 200_000, count: 1 });
    expect(r.undatedShare).toBeCloseTo(200_000 / 375_000);
    expect(r.undatedBusinessUnits).toEqual(["IT"]);
  });

  it("has no quarters without dates", () => {
    expect(valueRoadmap([unestimated])).toMatchObject({ quarters: [], undatedShare: null });
  });
});

describe("cost if delivered", () => {
  it("undoes the delivery weighting of the stored expected cost", () => {
    expect(costIfDelivered(b)).toBeCloseTo(17_500 / 0.65);
    expect(costIfDelivered(unestimated)).toBeNull();
    expect(costIfDelivered(make({ id: 5, name: "Zero", annual_cost_eur: 1_000, delivery_score: 0 }))).toBeNull();
  });
});

describe("value labels", () => {
  it("formats millions with a real minus sign", () => {
    expect(formatMillions(39_783_000)).toBe("39.8");
    expect(formatMillions(-5_731_580)).toBe("−5.7");
    expect(formatMillions(2_900_000, true)).toBe("+2.9");
    expect(formatMillions(-20)).toBe("0.0");
    expect(formatSignedEur(-5_731_580)).toBe("≈ −5.7 M €");
    expect(formatSignedEur(12_000)).toBe("≈ +12k €");
  });
});
