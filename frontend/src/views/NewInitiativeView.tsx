import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, createInitiative, fetchReferenceData, type ReferenceData } from "../api/client";
import { flagshipLabel } from "../domain/format";
import { riskActions, riskLevelLabel } from "../domain/risk";
import {
  EMPTY_FORM,
  LEVERS,
  STAGES,
  previewRiskLevel,
  previewValue,
  quarterOptions,
  toInput,
  typicalValues,
  validate,
  type FormState,
  type LeverKey,
} from "../domain/userInput";
import { useApp } from "../store";

type Errors = ReturnType<typeof validate>;

const keur = (eur: number) => `${Math.round(eur / 1000).toLocaleString("en-US")}k €`;
const signedKeur = (eur: number) => (eur > 0 ? "+" : eur < 0 ? "−" : "") + keur(Math.abs(eur));
const fmt = (n: number | undefined, unit = "") => (n === undefined ? "" : `${n.toLocaleString("en-US")}${unit}`);

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

function NumberInput({ value, onChange, unit, invalid, placeholder }: { value: string; onChange: (v: string) => void; unit?: string; invalid?: boolean; placeholder?: string }) {
  return (
    <span className={`nf-input nf-number${invalid ? " invalid" : ""}`}>
      <input inputMode="decimal" value={value} placeholder={placeholder} aria-invalid={invalid || undefined} onChange={(e) => onChange(e.target.value)} />
      {unit && <span className="nf-unit">{unit}</span>}
    </span>
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

export function NewInitiativeView() {
  const navigate = useNavigate();
  const { addInitiative } = useApp();
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
  const owners = (ref?.owners ?? []).filter((o) => o.category === form.businessUnit);
  const solutionType = ref?.solutionTypes.find((t) => String(t.id) === form.solutionTypeId)?.name;
  const flagship = ref?.valueTypes.find((t) => String(t.id) === form.valueTypeId)?.name;
  const typical = typicalValues(solutionType, flagship);
  const quarters = useMemo(() => quarterOptions(), []);

  const input = toInput(form);
  const preview = previewValue(input);
  const level = previewRiskLevel(input);
  const errors: Errors = showErrors ? validate(form) : {};

  async function save() {
    setShowErrors(true);
    setSaveError(null);
    if (Object.keys(validate(form)).length > 0) return;
    setSaving(true);
    try {
      const created = await createInitiative(toInput(form));
      addInitiative(created);
      navigate("/", { state: { created: created.name } });
    } catch (err) {
      setSaveError(err instanceof ApiError || err instanceof Error ? err.message : "The initiative could not be saved.");
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
        <Field label="Cases per year" error={errors.casesPerYear}>
          <NumberInput value={form.casesPerYear} onChange={(v) => set("casesPerYear", v)} invalid={!!errors.casesPerYear} />
        </Field>
        <Field label="Hours saved per case" error={errors.hoursSavedPerCase} hint={typical.hoursSavedPerCase ? `Typical for this solution type: ${typical.hoursSavedPerCase} h` : undefined}>
          <NumberInput value={form.hoursSavedPerCase} onChange={(v) => set("hoursSavedPerCase", v)} unit="h" invalid={!!errors.hoursSavedPerCase} />
        </Field>
      </div>
    ),
    quality: (
      <div className="nf-grid3">
        {!form.levers.efficiency && (
          <Field label="Cases per year" error={errors.casesPerYear}>
            <NumberInput value={form.casesPerYear} onChange={(v) => set("casesPerYear", v)} invalid={!!errors.casesPerYear} />
          </Field>
        )}
        <Field label="Error rate today" error={errors.errorRatePct} hint={`Typical: ${typical.errorRatePct} %`}>
          <NumberInput value={form.errorRatePct} onChange={(v) => set("errorRatePct", v)} unit="%" invalid={!!errors.errorRatePct} />
        </Field>
        <Field label="Errors avoided" error={errors.errorsAvoidedPct} hint={typical.errorsAvoidedPct ? `Typical: ${typical.errorsAvoidedPct} %` : undefined}>
          <NumberInput value={form.errorsAvoidedPct} onChange={(v) => set("errorsAvoidedPct", v)} unit="%" invalid={!!errors.errorsAvoidedPct} />
        </Field>
        <Field label="Cost per error" error={errors.costPerError} hint={`Typical for this flagship: ${fmt(typical.costPerError, " €")}`}>
          <NumberInput value={form.costPerError} onChange={(v) => set("costPerError", v)} unit="€" invalid={!!errors.costPerError} />
        </Field>
      </div>
    ),
    riskReduction: (
      <div className="nf-grid3">
        <Field label="Incidents per year" error={errors.riskEventsPerYear}>
          <NumberInput value={form.riskEventsPerYear} onChange={(v) => set("riskEventsPerYear", v)} invalid={!!errors.riskEventsPerYear} />
        </Field>
        <Field label="Incidents avoided" error={errors.eventsAvoidedPct} hint={typical.eventsAvoidedPct ? `Typical: ${typical.eventsAvoidedPct} %` : undefined}>
          <NumberInput value={form.eventsAvoidedPct} onChange={(v) => set("eventsAvoidedPct", v)} unit="%" invalid={!!errors.eventsAvoidedPct} />
        </Field>
        <Field label="Cost per incident" error={errors.costPerEvent} hint={`Typical for this flagship: ${fmt(typical.costPerEvent, " €")}`}>
          <NumberInput value={form.costPerEvent} onChange={(v) => set("costPerEvent", v)} unit="€" invalid={!!errors.costPerEvent} />
        </Field>
      </div>
    ),
    speed: (
      <div className="nf-grid3">
        <Field label="Delay-relevant events per year" error={errors.delayEventsPerYear}>
          <NumberInput value={form.delayEventsPerYear} onChange={(v) => set("delayEventsPerYear", v)} invalid={!!errors.delayEventsPerYear} />
        </Field>
        <Field label="Cost of delay per event" error={errors.costOfDelayPerEvent} hint={`Typical for this flagship: ${fmt(typical.costOfDelayPerEvent, " €")}`}>
          <NumberInput value={form.costOfDelayPerEvent} onChange={(v) => set("costOfDelayPerEvent", v)} unit="€" invalid={!!errors.costOfDelayPerEvent} />
        </Field>
        <Field label="Lead time saved" error={errors.leadTimeSavedPct} hint={typical.leadTimeSavedPct ? `Typical: ${typical.leadTimeSavedPct} %` : undefined}>
          <NumberInput value={form.leadTimeSavedPct} onChange={(v) => set("leadTimeSavedPct", v)} unit="%" invalid={!!errors.leadTimeSavedPct} />
        </Field>
      </div>
    ),
  };

  const FORMULA: Record<LeverKey, string> = {
    efficiency: "cases × hours saved × 60 €/h",
    quality: "cases × error rate × errors avoided × cost per error",
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
          <span className="nf-crumb">Cockpit / New initiative</span>
          <h1>Add an AI initiative</h1>
          <p className="muted">Enter the drivers. The value and the risk level are calculated from them.</p>
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
              <Field label="Business unit" required error={errors.businessUnit}>
                <select className="nf-input" value={form.businessUnit} onChange={(e) => setForm((f) => ({ ...f, businessUnit: e.target.value, ownerId: "" }))}>
                  <option value="">Choose …</option>
                  {businessUnits.map((bu) => <option key={bu} value={bu}>{bu}</option>)}
                </select>
              </Field>
              <Field label="Owner" required error={errors.ownerId}>
                <select className="nf-input" value={form.ownerId} disabled={!form.businessUnit} onChange={(e) => set("ownerId", e.target.value)}>
                  <option value="">{form.businessUnit ? "Choose …" : "Choose a business unit first"}</option>
                  {owners.map((o) => <option key={o.id} value={o.id}>{o.department ? `${o.name} · ${o.department}` : o.name}</option>)}
                </select>
              </Field>
              <Field label="Flagship" required error={errors.valueTypeId}>
                <select className="nf-input" value={form.valueTypeId} onChange={(e) => set("valueTypeId", e.target.value)}>
                  <option value="">Choose …</option>
                  {ref.valueTypes.map((t) => <option key={t.id} value={t.id}>{flagshipLabel(t.name)}</option>)}
                </select>
              </Field>
              <Field label="Solution type" required error={errors.solutionTypeId}>
                <select className="nf-input" value={form.solutionTypeId} onChange={(e) => set("solutionTypeId", e.target.value)}>
                  <option value="">Choose …</option>
                  {ref.solutionTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </Field>
              <Field label="Stage" required error={errors.stage}>
                <select className="nf-input" value={form.stage} onChange={(e) => set("stage", e.target.value)}>
                  <option value="">Choose …</option>
                  {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
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
              <Field label="One-time cost" required error={errors.oneTimeCosts}>
                <NumberInput value={form.oneTimeCosts} onChange={(v) => set("oneTimeCosts", v)} unit="€" invalid={!!errors.oneTimeCosts} />
              </Field>
              <Field label="Operating cost" required error={errors.operatingCosts}>
                <NumberInput value={form.operatingCosts} onChange={(v) => set("operatingCosts", v)} unit="€ / yr" invalid={!!errors.operatingCosts} />
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
            {saving ? "Saving …" : "Save initiative"}
          </button>
          <button type="button" className="nf-btn nf-secondary" onClick={() => navigate(-1)}>
            Cancel
          </button>
          <span className="nf-side-small">Final values are calculated by the pipeline a few seconds after saving.</span>
        </aside>
      </div>
    </div>
  );
}
