import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, createInitiative, fetchReferenceData, type ReferenceData } from "../api/client";
import type { Stagegate } from "../api/types";
import { GateDatesEditor } from "../components/GateDates";
import { flagshipLabel } from "../domain/format";
import { GATES, STAGE_GATE_RULES, gateRequirement, type GateRules } from "../domain/lifecycle";
import { riskActions, riskLevelLabel } from "../domain/risk";
import {
  AI_LAYERS,
  EMPTY_FORM,
  LEVERS,
  RUNNING_COST_RANGES,
  STAGES,
  VALUE_DOMAINS,
  domainOption,
  previewInput,
  previewRiskLevel,
  previewValue,
  quarterOptions,
  toInput,
  typicalValues,
  validate,
  type DomainField,
  type DomainOption,
  type FormState,
  type LeverKey,
} from "../domain/userInput";
import { useApp } from "../store";

type Errors = ReturnType<typeof validate>;

const keur = (eur: number) => `${Math.round(eur / 1000).toLocaleString("en-US")}k €`;
const signedKeur = (eur: number) => (eur > 0 ? "+" : eur < 0 ? "−" : "") + keur(Math.abs(eur));

const COMPLEXITY_HINT: Record<string, string> = {
  "1": "off the shelf",
  "3": "configuration",
  "5": "new integration",
  "7": "custom development",
  "9": "new platform",
};

function Field({ label, required, error, hint, children }: { label: string; required?: boolean; error?: string; hint?: string; children: ReactNode }) {
  return (
    <label className="nf-field">
      <span className="nf-label">
        {label}
        {required && <b aria-hidden="true"> *</b>}
      </span>
      {children}
      {error ? <span className="nf-error">{error}</span> : hint ? <span className="nf-hint">{hint}</span> : null}
    </label>
  );
}

/** A number chosen from its domain; the option's value is what is stored. */
function DomainSelect({ value, onChange, options, invalid }: { value: string; onChange: (v: string) => void; options: DomainOption[]; invalid?: boolean }) {
  return (
    <select className={`nf-input${invalid ? " invalid" : ""}`} value={value} aria-invalid={invalid || undefined} onChange={(e) => onChange(e.target.value)}>
      <option value="">Choose …</option>
      {options.map((o) => <option key={o.value} value={String(o.value)}>{o.label}</option>)}
    </select>
  );
}

/** A radio group drawn as a segmented control. */
function Segmented<T extends string>({ name, label, value, options, onChange }: { name: string; label: string; value: T; options: [T, string][]; onChange: (v: T) => void }) {
  return (
    <div className="nf-seg" role="radiogroup" aria-label={label}>
      {options.map(([v, text]) => (
        <label key={v} className={v === value ? "on" : undefined}>
          <input type="radio" name={name} value={v} checked={v === value} onChange={() => onChange(v)} />
          {text}
        </label>
      ))}
    </div>
  );
}

const yesNo = (v: boolean): "yes" | "no" => (v ? "yes" : "no");
const ownerLabel = (o: { name: string; category: string | null }) => (o.category ? `${o.name} · ${o.category}` : o.name);

export function NewInitiativeView() {
  const navigate = useNavigate();
  const { addInitiative, rights, reloadRights } = useApp();
  // The owner can be chosen; by default it is the signed-in user, who chooses their business unit
  // once while they have no owner row yet.
  const myOwner = rights.owner ?? null;
  const [ref, setRef] = useState<ReferenceData | null>(null);
  const [refError, setRefError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [showErrors, setShowErrors] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchReferenceData().then(
      (data) => !cancelled && setRef(data),
      (err: unknown) => !cancelled && setRefError(err instanceof Error ? err.message : "The lists could not be loaded."),
    );
    return () => {
      cancelled = true;
    };
  }, []);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }));
  const toggleLever = (key: LeverKey) => setForm((f) => ({ ...f, levers: { ...f.levers, [key]: !f.levers[key] } }));

  const businessUnits = useMemo(
    () => [...new Set((ref?.owners ?? []).map((o) => o.category).filter((c): c is string => !!c))].sort(),
    [ref],
  );
  const otherOwners = useMemo(
    () => (ref?.owners ?? []).filter((o) => o.id !== myOwner?.id),
    [ref, myOwner],
  );
  const chosenOwner = form.ownerId ? ref?.owners.find((o) => String(o.id) === form.ownerId) ?? null : null;
  const flagship = ref?.valueTypes.find((t) => String(t.id) === form.valueTypeId)?.name;
  const typical = typicalValues(form.aiLayer || undefined, flagship);
  const aiLayers = ref?.options?.ai_layers?.map((o) => o.value) ?? AI_LAYERS;
  const costRanges = ref?.options?.running_cost_ranges ?? RUNNING_COST_RANGES;
  const quarters = useMemo(() => quarterOptions(), []);
  const domains = { ...VALUE_DOMAINS, ...(ref?.options?.value_domains as Record<DomainField, DomainOption[]> | undefined) };
  const rules: GateRules = ref?.options?.stage_gate_rules ?? STAGE_GATE_RULES;
  const stages = ref?.options?.stages?.map((o) => o.value) ?? STAGES;
  /** "Typical: …" as the label of the range the typical value falls in. */
  const typicalHint = (field: DomainField, value: number | undefined, what = "Typical") =>
    value === undefined ? undefined : `${what}: ${domainOption(domains[field], value)?.label ?? value}`;
  /** A new stage asks for other gates: dates of gates it does not ask for are dropped. */
  const changeStage = (stage: string) =>
    setForm((f) => {
      const asked = GATES.filter((g) => gateRequirement(stage, g, rules) === "passed");
      const keep = (g: Stagegate) => asked.includes(g) || (g === "Needs" && asked.length > 0);
      const gateDates = Object.fromEntries(GATES.map((g) => [g, keep(g) ? f.gateDates[g] : ""])) as FormState["gateDates"];
      return { ...f, stage, gateDates };
    });
  const pick = (field: DomainField, key: keyof FormState) => (
    <DomainSelect value={String(form[key])} options={domains[field]} invalid={!!errors[key]} onChange={(v) => set(key, v as never)} />
  );

  // with an owner (chosen, or the user's own) the business unit is the owner's: not asked, not sent
  const owner = chosenOwner ?? myOwner;
  const checked: FormState = owner ? { ...form, businessUnit: owner.category || "owner" } : form;
  const input = { ...toInput(form), business_unit: owner ? null : form.businessUnit || null };
  const preview = previewValue(previewInput(input));
  const level = previewRiskLevel(input);
  const errors: Errors = showErrors ? validate(checked, domains, undefined, rules) : {};

  async function save() {
    setShowErrors(true);
    setSaveError(null);
    if (Object.keys(validate(checked, domains, undefined, rules)).length > 0) return;
    setSaving(true);
    try {
      const created = await createInitiative(input);
      addInitiative(created);
      if (!myOwner && !form.ownerId) reloadRights();
      navigate("/my", { state: { created: created.name } });
    } catch (err) {
      setSaveError(err instanceof ApiError || err instanceof Error ? err.message : "The idea could not be saved.");
      setSaving(false);
    }
  }

  if (refError) {
    return (
      <div className="state card" role="alert">
        <p>{refError}</p>
      </div>
    );
  }
  if (!ref) return <p className="state" role="status">Loading lists …</p>;

  const leverFields: Record<LeverKey, ReactNode> = {
    efficiency: (
      <div className="nf-grid2">
        <Field label="Runs per year" error={errors.casesPerYear}>{pick("cases_per_year", "casesPerYear")}</Field>
        <Field label="Time saved per run" error={errors.hoursSavedPerCase} hint={typicalHint("hours_saved_per_case", typical.hoursSavedPerCase, "Typical for this AI layer")}>
          {pick("hours_saved_per_case", "hoursSavedPerCase")}
        </Field>
      </div>
    ),
    quality: (
      <div className="nf-grid3">
        {!form.levers.efficiency && (
          <Field label="Runs per year" error={errors.casesPerYear}>{pick("cases_per_year", "casesPerYear")}</Field>
        )}
        <Field label="Error rate today" error={errors.errorRateBefore} hint={typicalHint("error_rate_before", typical.errorRateBefore)}>
          {pick("error_rate_before", "errorRateBefore")}
        </Field>
        <Field label="Errors avoided" error={errors.errorsAvoided} hint={typicalHint("errors_avoided", typical.errorsAvoided)}>
          {pick("errors_avoided", "errorsAvoided")}
        </Field>
        <Field label="Cost per error" error={errors.costPerError} hint={typicalHint("cost_per_error", typical.costPerError, "Typical for this topic")}>
          {pick("cost_per_error", "costPerError")}
        </Field>
      </div>
    ),
    riskReduction: (
      <div className="nf-grid3">
        <Field label="Incidents per year" error={errors.riskEventsPerYear}>{pick("risk_events_per_year", "riskEventsPerYear")}</Field>
        <Field label="Incidents avoided" error={errors.eventsAvoided} hint={typicalHint("events_avoided", typical.eventsAvoided)}>
          {pick("events_avoided", "eventsAvoided")}
        </Field>
        <Field label="Cost per incident" error={errors.costPerEvent} hint={typicalHint("cost_per_event", typical.costPerEvent, "Typical for this topic")}>
          {pick("cost_per_event", "costPerEvent")}
        </Field>
      </div>
    ),
    speed: (
      <div className="nf-grid3">
        <Field label="Delay-relevant events per year" error={errors.delayEventsPerYear}>{pick("delay_events_per_year", "delayEventsPerYear")}</Field>
        <Field label="Cost of delay per event" error={errors.costOfDelayPerEvent} hint={typicalHint("cost_of_delay_per_event", typical.costOfDelayPerEvent, "Typical for this topic")}>
          {pick("cost_of_delay_per_event", "costOfDelayPerEvent")}
        </Field>
        <Field label="Lead time saved" error={errors.leadTimeSaved} hint={typicalHint("lead_time_saved", typical.leadTimeSaved)}>
          {pick("lead_time_saved", "leadTimeSaved")}
        </Field>
      </div>
    ),
  };

  const FORMULA: Record<LeverKey, string> = {
    efficiency: "runs × time saved × 60 €/h",
    quality: "runs × error rate × errors avoided × cost per error",
    riskReduction: "incidents × share avoided × cost per incident",
    speed: "events × cost of delay × lead time saved",
  };

  const question = (title: string, detail: string | null, control: ReactNode) => (
    <div className="nf-q">
      <div>
        <div className="nf-qt">{title}</div>
        {detail && <div className="nf-qd">{detail}</div>}
      </div>
      {control}
    </div>
  );

  return (
    <div className="nf">
      <header className="nf-head">
        <div>
          <span className="nf-crumb">My use cases / New AI idea</span>
          <h1>Add a new AI idea</h1>
          <p className="muted">
            Choose the drivers. The value and the risk level are calculated from them. An approver checks the idea and
            assigns a use case lead. The details (form 2) can be added at any time on the use case page.
          </p>
        </div>
        <span className="muted">
          Fields marked <b className="nf-req">*</b> are required
        </span>
      </header>

      <div className="nf-layout">
        <form
          className="nf-main"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <section className="card nf-card" aria-labelledby="nf-basics">
            <h2 id="nf-basics" className="nf-h2"><span className="nf-num">1</span>Basics</h2>
            <Field label="Name" required error={errors.name}>
              <input className={`nf-input${errors.name ? " invalid" : ""}`} value={form.name} maxLength={200} onChange={(e) => set("name", e.target.value)} />
            </Field>
            <Field label="Description" required error={errors.description}>
              <textarea className={`nf-input nf-textarea${errors.description ? " invalid" : ""}`} value={form.description} rows={3} onChange={(e) => set("description", e.target.value)} />
            </Field>
            <div className="nf-grid3">
              <Field
                label="Owner"
                hint={chosenOwner ? "You still find the use case under My use cases." : "You by default; choose someone else if they own it."}
              >
                <select className="nf-input" value={form.ownerId} onChange={(e) => set("ownerId", e.target.value)}>
                  <option value="">{myOwner ? `Me · ${ownerLabel(myOwner)}` : "Me"}</option>
                  {otherOwners.map((o) => <option key={o.id} value={o.id}>{ownerLabel(o)}</option>)}
                </select>
              </Field>
              {!owner && (
                <Field label="Your business unit" required error={errors.businessUnit} hint="Asked once: you become an owner.">
                  <select className="nf-input" value={form.businessUnit} onChange={(e) => set("businessUnit", e.target.value)}>
                    <option value="">Choose …</option>
                    {businessUnits.map((bu) => <option key={bu} value={bu}>{bu}</option>)}
                  </select>
                </Field>
              )}
              <Field label="Topic" required error={errors.valueTypeId}>
                <select className="nf-input" value={form.valueTypeId} onChange={(e) => set("valueTypeId", e.target.value)}>
                  <option value="">Choose …</option>
                  {ref.valueTypes.map((t) => <option key={t.id} value={t.id}>{flagshipLabel(t.name)}</option>)}
                </select>
              </Field>
              <Field label="AI layer" required error={errors.aiLayer} hint="The solution type follows in the details after approval.">
                <select className="nf-input" value={form.aiLayer} onChange={(e) => set("aiLayer", e.target.value)}>
                  <option value="">Choose …</option>
                  {aiLayers.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </Field>
              <Field label="Stage" required error={errors.stage}>
                <select className="nf-input" value={form.stage} onChange={(e) => changeStage(e.target.value)}>
                  {stages.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <div className="nf-grid2 nf-dates">
                <Field label="Start">
                  <select className="nf-input" value={form.dateStart} onChange={(e) => set("dateStart", e.target.value)}>
                    <option value="">–</option>
                    {quarters.map((q) => <option key={q} value={q}>{q}</option>)}
                  </select>
                </Field>
                <Field label="Delivery">
                  <select className="nf-input" value={form.dateDelivery} onChange={(e) => set("dateDelivery", e.target.value)}>
                    <option value="">–</option>
                    {quarters.map((q) => <option key={q} value={q}>{q}</option>)}
                  </select>
                </Field>
              </div>
            </div>
            <GateDatesEditor stage={form.stage} dates={form.gateDates} mode="new" rules={rules} showProblems={showErrors}
              onChange={(gate: Stagegate, date: string) => setForm((f) => ({ ...f, gateDates: { ...f.gateDates, [gate]: date } }))} />
          </section>

          <section className="card nf-card" aria-labelledby="nf-value">
            <h2 id="nf-value" className="nf-h2"><span className="nf-num">2</span>Value drivers <span className="nf-sub">at least one</span></h2>
            {errors.levers && <p className="nf-error" role="alert">{errors.levers}</p>}
            {LEVERS.map((l) => {
              const on = form.levers[l.key];
              return (
                <div key={l.key} className={`nf-lever${on ? " on" : ""}`}>
                  <div className="nf-lever-head">
                    <label className="nf-toggle">
                      <input type="checkbox" checked={on} onChange={() => toggleLever(l.key)} />
                      {l.label}
                    </label>
                    <span className="mono nf-lever-result">{on ? `${preview.buckets[l.key].toLocaleString("en-US", { maximumFractionDigits: 0 })} € / yr` : "not used"}</span>
                  </div>
                  {on && (
                    <>
                      {leverFields[l.key]}
                      <span className="nf-formula">{FORMULA[l.key]}</span>
                    </>
                  )}
                </div>
              );
            })}
          </section>

          <section className="card nf-card" aria-labelledby="nf-delivery">
            <h2 id="nf-delivery" className="nf-h2"><span className="nf-num">3</span>Delivery &amp; cost</h2>
            <div className="nf-grid2">
              <Field label="How solid are the numbers?" required>
                <Segmented name="estimateBasis" label="How solid are the numbers?" value={form.estimateBasis} onChange={(v) => set("estimateBasis", v)}
                  options={[["rough", "Rough guess"], ["benchmark", "Benchmark"], ["measured", "Measured"]]} />
              </Field>
              <Field label="Delivery likelihood" required>
                <Segmented name="deliveryLikelihood" label="Delivery likelihood" value={form.deliveryLikelihood} onChange={(v) => set("deliveryLikelihood", v)}
                  options={[["low", "Low"], ["medium", "Medium"], ["high", "High"]]} />
              </Field>
            </div>
            <div className="nf-grid3">
              <Field label="Complexity (1–9)" required error={errors.complexity}>
                <select className="nf-input" value={form.complexity} onChange={(e) => set("complexity", e.target.value)}>
                  <option value="">Choose …</option>
                  {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((c) => (
                    <option key={c} value={c}>{COMPLEXITY_HINT[c] ? `${c} · ${COMPLEXITY_HINT[c]}` : c}</option>
                  ))}
                </select>
              </Field>
              <Field label="One-time cost" required error={errors.oneTimeCosts}>{pick("one_time_costs", "oneTimeCosts")}</Field>
              <Field label="Running costs" required error={errors.runningCostRange} hint="A range is enough at this point.">
                <select className="nf-input" value={form.runningCostRange} onChange={(e) => set("runningCostRange", e.target.value as FormState["runningCostRange"])}>
                  <option value="">Choose …</option>
                  {costRanges.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
              </Field>
            </div>
          </section>

          <section className="card nf-card" aria-labelledby="nf-risk">
            <h2 id="nf-risk" className="nf-h2"><span className="nf-num">4</span>Risk indicators <span className="nf-sub">framework agreement on AI</span></h2>
            <div>
              {question("Does it process personal data of employees?", "Names, shift data, notes that identify a person",
                <Segmented name="pd" label="Personal data of employees" value={form.employeePersonalData} onChange={(v) => set("employeePersonalData", v)}
                  options={[["no", "No"], ["pseudonymised", "Pseudonymised"], ["yes", "Yes"]]} />)}
              {question("Could it be used to monitor performance or behaviour?", null,
                <Segmented name="pbc" label="Performance or behaviour monitoring" value={yesNo(form.performanceOrBehaviourControl)} onChange={(v) => set("performanceOrBehaviourControl", v === "yes")}
                  options={[["no", "No"], ["yes", "Yes"]]} />)}
              {question("Does it make decisions about employees?", "Prepares: a person decides on its proposal",
                <Segmented name="doe" label="Decisions about employees" value={form.decisionsOnEmployees} onChange={(v) => set("decisionsOnEmployees", v)}
                  options={[["none", "None"], ["prepares", "Prepares"], ["automated", "Automated"]]} />)}
              {question("Does it build profiles of or learn about individuals?", null,
                <Segmented name="prof" label="Profiling of individuals" value={yesNo(form.profilingOfIndividuals)} onChange={(v) => set("profilingOfIndividuals", v === "yes")}
                  options={[["no", "No"], ["yes", "Yes"]]} />)}
              {question("Does it change how employees work?", "Automates or reshapes their tasks",
                <Segmented name="wf" label="Changes how employees work" value={yesNo(form.changesEmployeeWorkflows)} onChange={(v) => set("changesEmployeeWorkflows", v === "yes")}
                  options={[["no", "No"], ["yes", "Yes"]]} />)}
              {question("Emotion recognition, lie detection, or no way to trace or object?", "Not acceptable under the agreement",
                <Segmented name="pp" label="Prohibited practice" value={yesNo(form.prohibitedPractice)} onChange={(v) => set("prohibitedPractice", v === "yes")}
                  options={[["no", "No"], ["yes", "Yes"]]} />)}
            </div>
          </section>
          <button type="submit" hidden aria-hidden="true" tabIndex={-1} />
        </form>

        <aside className="nf-side" aria-label="Estimate preview">
          <div className="nf-side-top">
            <span>Estimate</span>
            <span className="ck-badge">preview</span>
          </div>
          <div className="nf-side-block">
            <span className="nf-side-label">Potential per year</span>
            <span className="mono nf-side-total">{keur(preview.potential)}</span>
            <span className="nf-side-small">
              {keur(preview.hypothetical)} × {preview.confidence.toFixed(2)} × {preview.delivery.toFixed(2)}
            </span>
          </div>
          <div className="nf-side-rows">
            <div><span>Expected cost per year</span><span className="mono">{keur(preview.annualCost)}</span></div>
            <div><span>Net per year</span><span className={`mono${preview.net >= 0 ? " nf-pos" : ""}`}>{signedKeur(preview.net)}</span></div>
          </div>
          <div className="nf-side-rows">
            <span className="nf-side-label">Risk level</span>
            <span className={`nf-risk nf-risk-${level}`}>{level} · {riskLevelLabel(level)}</span>
            <span className="nf-side-small">{riskActions(level)}</span>
          </div>
          {saveError && <p className="nf-save-error" role="alert">{saveError}</p>}
          <button type="button" className="nf-btn nf-primary" disabled={saving} onClick={() => void save()}>
            {saving ? "Submitting …" : "Submit idea"}
          </button>
          <button type="button" className="nf-btn nf-secondary" onClick={() => navigate(-1)}>
            Cancel
          </button>
          <span className="nf-side-small">
            The idea goes to the approvers. Final values are calculated by the pipeline within about a minute.
          </span>
        </aside>
      </div>
    </div>
  );
}
