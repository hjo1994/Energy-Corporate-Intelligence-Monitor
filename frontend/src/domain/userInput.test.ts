import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { InitiativeInput } from "../api/types";
import { EMPTY_FORM, VALUE_DOMAINS, domainOption, parseNumber, previewInput, previewRiskLevel, previewValue, toInput, validate, type FormState } from "./userInput";

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
    const p = previewValue(i as unknown as Parameters<typeof previewValue>[0]); // the fixture carries the amount
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
  aiLayer: "AI for productivity and efficiency",
  stage: "Idea",
  dateDelivery: "Q3 2027",
  levers: { efficiency: true, quality: true, riskReduction: false, speed: false },
  // values of the domains (the selects store the option's value)
  casesPerYear: "5000",
  hoursSavedPerCase: "0.4",
  errorRateBefore: "0.075",
  errorsAvoided: "0.5",
  costPerError: "500",
  riskEventsPerYear: "3", // lever switched off -> not sent
  complexity: "4",
  oneTimeCosts: "175000",
  runningCostRange: "up_to_10k",
};

describe("form", () => {
  it("parses numbers with thousands separators and rejects the rest", () => {
    expect(parseNumber("3,000")).toBe(3000);
    expect(parseNumber("0.5")).toBe(0.5);
    expect(parseNumber("-1")).toBeNull();
    expect(parseNumber("abc")).toBeNull();
  });

  it("builds the request body: shares as fractions, switched-off levers left out", () => {
    const body = toInput(filled);
    expect(body).toMatchObject({
      name: "Smart Invoice Check",
      owner_id: 1,
      cases_per_year: 5000,
      error_rate_before: 0.075,
      errors_avoided: 0.5,
      risk_events_per_year: null,
      date_start: null,
      date_delivery: "Q3 2027",
      solution_complexity_score: 4,
      one_time_costs: 175000,
      ai_layer: "AI for productivity and efficiency",
      running_cost_range: "up_to_10k",
    });
    expect(body).not.toHaveProperty("solution_type_id");
    expect(validate(filled)).toEqual({});
    // the preview counts 5,000 € / year for "up to 10k", weighted by delivery (medium: 0.65)
    expect(previewValue(previewInput(body)).operatingCosts).toBeCloseTo(3250, 6);
  });

  it("requires the basics and one complete lever", () => {
    const errors = validate({ ...EMPTY_FORM });
    expect(Object.keys(errors)).toEqual(
      expect.arrayContaining(["name", "ownerId", "aiLayer", "stage", "complexity", "oneTimeCosts", "runningCostRange", "levers"]),
    );
    expect(validate({ ...filled, hoursSavedPerCase: "", levers: { ...filled.levers, quality: false } }).levers).toBeDefined();
    // only values of the domain
    expect(validate({ ...filled, casesPerYear: "3000" }).casesPerYear).toMatch(/ranges/);
    expect(validate({ ...filled, oneTimeCosts: "200000" }).oneTimeCosts).toMatch(/ranges/);
  });

  it("asks for the gate dates the stage needs", () => {
    const today = "2026-11-01";
    expect(validate({ ...filled, stage: "PoC" }, undefined, today).gateScope).toMatch(/needs the date the scope gate/);
    const poc = { ...filled, stage: "PoC", gateDates: { ...filled.gateDates, Scope: "2026-02-10" } };
    expect(validate(poc, undefined, today)).toEqual({});
    expect(validate({ ...poc, gateDates: { ...poc.gateDates, Scope: "2026-12-01" } }, undefined, today).gateScope).toMatch(/cannot be in the future/);
    expect(validate({ ...poc, gateDates: { ...poc.gateDates, Needs: "2026-03-01" } }, undefined, today).gateScope).toMatch(/before the needs gate/);
    expect(toInput(poc)).toMatchObject({ scope_gate_date: "2026-02-10", needs_gate_date: null });
  });

  it("finds the range of a value", () => {
    expect(domainOption(VALUE_DOMAINS.one_time_costs, 175000)?.label).toBe("100k–250k €");
    expect(domainOption(VALUE_DOMAINS.one_time_costs, 200000)?.label).toBe("100k–250k €"); // nearest, for old values
    expect(domainOption(VALUE_DOMAINS.errors_avoided, 0.4)?.label).toBe("about 50 %");
  });
});
