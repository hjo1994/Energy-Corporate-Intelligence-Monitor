import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { InitiativeInput } from "../api/types";
import { EMPTY_FORM, parseNumber, previewRiskLevel, previewValue, toInput, validate, type FormState } from "./userInput";

// Same cases as the pipeline (binding) and the backend's pending values — one file in this repo.
const FIXTURE = JSON.parse(
  readFileSync(resolve(process.cwd(), "../backend/tests/fixtures/user_input_cases.json"), "utf-8"), // tests run in frontend/
) as {
  base: Record<string, unknown>;
  cases: { name: string; input: Record<string, unknown>; expected: Record<string, number> }[];
};

const snake = (key: string) => key.replace(/([a-z])([A-Z])/g, "$1_$2").toLowerCase();
const input = (c: { input: Record<string, unknown> }) =>
  Object.fromEntries(Object.entries({ ...FIXTURE.base, ...c.input }).map(([k, v]) => [snake(k), v])) as unknown as InitiativeInput;

describe("preview formulas against the shared fixture", () => {
  it.each(FIXTURE.cases.map((c) => [c.name, c] as const))("%s", (_, c) => {
    const i = input(c);
    expect(previewRiskLevel(i)).toBe(c.expected.riskLevel);
    if (!("efficiency" in c.expected)) return;
    const p = previewValue(i);
    const actual: Record<string, number> = {
      efficiency: p.buckets.efficiency,
      quality: p.buckets.quality,
      riskReduction: p.buckets.riskReduction,
      strategic: p.buckets.speed,
      hypothetical: p.hypothetical,
      confidenceScore: p.confidence,
      deliveryScore: p.delivery,
      potential: p.potential,
      oneTimeCosts: p.oneTimeCosts,
      operatingCosts: p.operatingCosts,
      depreciationYears: 5,
      annualCost: p.annualCost,
    };
    for (const [key, value] of Object.entries(c.expected)) {
      if (key !== "riskLevel") expect(actual[key]).toBeCloseTo(value, 6);
    }
  });
});

const filled: FormState = {
  ...EMPTY_FORM,
  name: " Smart Invoice Check ",
  description: "Checks invoices",
  businessUnit: "ETB",
  ownerId: "1",
  valueTypeId: "1",
  solutionTypeId: "1",
  stage: "Idea",
  dateDelivery: "Q3 2027",
  levers: { efficiency: true, quality: true, riskReduction: false, speed: false },
  casesPerYear: "3,000",
  hoursSavedPerCase: "0.5",
  errorRatePct: "8",
  errorsAvoidedPct: "40",
  costPerError: "2000",
  riskEventsPerYear: "4", // lever switched off -> not sent
  complexity: "4",
  oneTimeCosts: "200,000",
  operatingCosts: "0",
};

describe("form", () => {
  it("parses numbers with thousands separators and rejects the rest", () => {
    expect(parseNumber("3,000")).toBe(3000);
    expect(parseNumber("0.5")).toBe(0.5);
    expect(parseNumber("-1")).toBeNull();
    expect(parseNumber("abc")).toBeNull();
  });

  it("builds the request body: percentages as fractions, switched-off levers left out", () => {
    const body = toInput(filled);
    expect(body).toMatchObject({
      name: "Smart Invoice Check",
      owner_id: 1,
      cases_per_year: 3000,
      error_rate_before: 0.08,
      errors_avoided: 0.4,
      risk_events_per_year: null,
      date_start: null,
      date_delivery: "Q3 2027",
      solution_complexity_score: 4,
      one_time_costs: 200000,
    });
    expect(validate(filled)).toEqual({});
  });

  it("requires the basics and one complete lever", () => {
    const errors = validate({ ...EMPTY_FORM });
    expect(Object.keys(errors)).toEqual(
      expect.arrayContaining(["name", "ownerId", "stage", "complexity", "oneTimeCosts", "levers"]),
    );
    expect(validate({ ...filled, hoursSavedPerCase: "", levers: { ...filled.levers, quality: false } }).levers).toBeDefined();
    expect(validate({ ...filled, errorRatePct: "120" }).errorRatePct).toMatch(/percentage/);
  });
});
