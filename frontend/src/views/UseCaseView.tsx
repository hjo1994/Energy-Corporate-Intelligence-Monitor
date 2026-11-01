import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, fetchReferenceData, fetchUseCase, updateUseCase, type ReferenceData } from "../api/client";
import type { Option, Stagegate, UseCaseDetail } from "../api/types";
import { GateDatesEditor } from "../components/GateDates";
import { PendingTag } from "../components/small";
import { flagshipLabel } from "../domain/format";
import {
  FORM2_FIELDS,
  GATES,
  GATE_FIELD,
  PROCESSING_HINT,
  STAGE_GATE_RULES,
  approvalLabel,
  fieldValue,
  gateProblems,
  keur,
  savedGateDates,
  shortDate,
  type Form2Field,
  type GateDates,
  type GateRules,
} from "../domain/lifecycle";
import { riskLevelLabel } from "../domain/risk";
import { RUNNING_COST_RANGES, STAGES, VALUE_DOMAINS, domainOption, parseNumber, runningCostLabel, type DomainOption } from "../domain/userInput";

type Draft = Record<string, unknown>;

const initials = (name: string | null | undefined) =>
  (name ?? "?")
    .split(/[\s.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");

/** A draft value as shown in its input. */
function shown(draft: Draft, d: UseCaseDetail, key: string): unknown {
  return key in draft ? draft[key] : fieldValue(d, key);
}

/** The PATCH body: only fields that differ from the saved state, in the API's types. */
export function toPatch(draft: Draft, d: UseCaseDetail): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, raw] of Object.entries(draft)) {
    const field = FORM2_FIELDS.find((f) => f.key === key);
    let value: unknown = raw;
    if (field && ["eur", "int"].includes(field.kind)) value = typeof raw === "string" ? parseNumber(raw) : raw;
    if (field?.kind === "multi") value = Array.isArray(raw) ? raw : [];
    if (typeof value === "string") value = value.trim();
    if (value === "" || value === null || value === undefined) continue; // the API cannot clear a field
    const saved = fieldValue(d, key);
    const same = field?.kind === "multi" ? (value as string[]).join(",") === (saved ?? "") : String(value) === String(saved ?? "");
    if (!same) out[key] = value;
  }
  return out;
}

function Seg({ label, value, options, onChange, disabled }: { label: string; value: unknown; options: Option[]; onChange: (v: string) => void; disabled?: boolean }) {
  return (
    <div className="nf-seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <label key={o.value} className={o.value === value ? "on" : undefined}>
          <input type="radio" value={o.value} checked={o.value === value} disabled={disabled} onChange={() => onChange(o.value)} />
          {o.label}
        </label>
      ))}
    </div>
  );
}

function FieldInput({ field, value, onChange, lists, disabled }: { field: Form2Field; value: unknown; onChange: (v: unknown) => void; lists: ReferenceData; disabled: boolean }) {
  const options = field.options ? ((lists.options as unknown as Record<string, Option[]>)[field.options] ?? []) : [];
  const text = value === null || value === undefined ? "" : String(value);
  switch (field.kind) {
    case "select":
      return (
        <select className="nf-input" value={text} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
          <option value="">Choose …</option>
          {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      );
    case "segmented":
      return <Seg label={field.label} value={value} options={options} onChange={onChange} disabled={disabled} />;
    case "bool":
      return (
        <Seg label={field.label} value={value === true ? "yes" : value === false ? "no" : null} disabled={disabled}
          options={[{ value: "no", label: "No" }, { value: "yes", label: "Yes" }]} onChange={(v) => onChange(v === "yes")} />
      );
    case "multi": {
      const selected = Array.isArray(value) ? (value as string[]) : text ? text.split(",") : [];
      return (
        <div className="lc-multi" role="group" aria-label={field.label}>
          {options.map((o) => {
            const on = selected.includes(o.value);
            return (
              <label key={o.value} className={on ? "on" : undefined}>
                <input type="checkbox" checked={on} disabled={disabled}
                  onChange={() => onChange(on ? selected.filter((s) => s !== o.value) : [...selected, o.value])} />
                {o.label}
              </label>
            );
          })}
        </div>
      );
    }
    case "date":
      return <input type="date" className="nf-input" value={text.slice(0, 10)} disabled={disabled} onChange={(e) => onChange(e.target.value)} />;
    case "owner":
      return (
        <select className="nf-input" value={text} disabled={disabled} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")}>
          <option value="">Choose …</option>
          {lists.owners.map((o) => <option key={o.id} value={o.id}>{o.category ? `${o.name} · ${o.category}` : o.name}</option>)}
        </select>
      );
    case "solutionType":
      return (
        <select className="nf-input" value={text} disabled={disabled} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")}>
          <option value="">Choose …</option>
          {lists.solutionTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      );
    case "eur":
    case "int":
      return (
        <span className="nf-input nf-number">
          <input inputMode="decimal" value={text} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
          {field.kind === "eur" && <span className="nf-unit">€</span>}
        </span>
      );
    default:
      return <input className="nf-input" value={text} maxLength={1000} disabled={disabled} onChange={(e) => onChange(e.target.value)} />;
  }
}

function Section({ id, title, subtitle, children }: { id: string; title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section className="card lc-group open" aria-labelledby={id}>
      <header className="lc-group-head">
        <div>
          <h2 id={id} className="lc-h2">{title}</h2>
          {subtitle && <span className="muted">{subtitle}</span>}
        </div>
      </header>
      {children}
    </section>
  );
}

export function UseCaseView() {
  const { id } = useParams();
  const useCaseId = Number(id);
  const [d, setD] = useState<UseCaseDetail | null>(null);
  const [ref, setRef] = useState<ReferenceData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      setD(await fetchUseCase(useCaseId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The use case could not be loaded.");
    }
  }, [useCaseId]);

  useEffect(() => {
    void load();
    fetchReferenceData().then(setRef, (err: unknown) => setError(err instanceof Error ? err.message : "The lists could not be loaded."));
  }, [load]);

  // the pipeline picks saved changes up within about a minute
  useEffect(() => {
    if (!d || (d.processing !== "pending" && d.processing !== "changes_pending")) return;
    const timer = setInterval(() => void load(), 5000);
    return () => clearInterval(timer);
  }, [d, load]);

  const patch = useMemo(() => (d ? toPatch(draft, d) : {}), [draft, d]);

  if (error) {
    return (
      <div className="state card" role="alert">
        <p>{error}</p>
        <Link className="primary-link" to="/my">Back to my use cases</Link>
      </div>
    );
  }
  if (!d || !ref) return <p className="state" role="status">Loading the use case …</p>;

  const rules: GateRules = ref.options?.stage_gate_rules ?? STAGE_GATE_RULES;
  const stages = ref.options?.stages?.map((o) => o.value) ?? STAGES;
  const oneTimeDomain: DomainOption[] = ref.options?.value_domains?.one_time_costs ?? VALUE_DOMAINS.one_time_costs;
  const costRanges = ref.options?.running_cost_ranges ?? RUNNING_COST_RANGES;
  const stillProcessing = d.id < 0;
  const editable = d.can_edit && !stillProcessing && !saving;
  const setField = (k: string, v: unknown) => setDraft((x) => ({ ...x, [k]: v }));

  const saved = savedGateDates(d);
  const stage = String(shown(draft, d, "stage") ?? "");
  const dates = Object.fromEntries(GATES.map((g) => [g, String(shown(draft, d, GATE_FIELD[g]) ?? "")])) as GateDates;
  const touchesGates = "stage" in patch || GATES.some((g) => GATE_FIELD[g] in patch);
  const problems = touchesGates ? gateProblems(stage, dates, undefined, rules) : [];
  const dirty = Object.keys(patch).length > 0;
  const oneTime = shown(draft, d, "one_time_costs") as number | null;
  const oneTimeOption = domainOption(oneTimeDomain, oneTime);
  const oneTimeExact = oneTimeOption !== undefined && oneTime === oneTimeOption.value;

  async function save(extra: Record<string, unknown> = {}) {
    if (!d) return;
    setSaving(true);
    setMessage(null);
    try {
      const saved = await updateUseCase(d.id, { ...patch, ...extra, base_revision: d.revision } as never);
      setD(saved);
      setDraft({});
      setMessage({ kind: "ok", text: extra.resubmit ? "Resubmitted – the approvers will check it again." : "Saved. The pipeline processes the changes within about a minute." });
    } catch (err) {
      const text = err instanceof ApiError || err instanceof Error ? err.message : "The changes could not be saved.";
      setMessage({ kind: "error", text });
      if (err instanceof ApiError && err.status === 409) void load(); // someone else changed it meanwhile
    } finally {
      setSaving(false);
    }
  }

  const side: ReactNode = (
    <aside className="lc-side" aria-label="Summary">
      <section className="card lc-side-card">
        <h2 className="lc-h2">From your idea</h2>
        <div className="lc-side-rows">
          <div><span>Potential per year</span><span className="mono">{keur(d.potential_value_eur)}{d.provisional ? " *" : ""}</span></div>
          <div><span>Realised value</span><span className="mono">{keur(d.realized_value_eur)}</span></div>
          <div><span>One-time costs</span><span>{oneTimeExact ? oneTimeOption.label : keur(oneTime ?? d.one_time_costs)}</span></div>
          <div><span>Running costs</span><span>{runningCostLabel(d.running_cost_range) ?? keur(d.running_costs)}</span></div>
          <div>
            <span>Risk level</span>
            <span>{d.risk_classification ? `${d.risk_classification.id} · ${riskLevelLabel(d.risk_classification.id)}` : "–"}</span>
          </div>
          <div><span>Flagship</span><span>{d.value_type ? flagshipLabel(d.value_type.name) : "–"}</span></div>
          <div><span>AI layer</span><span>{d.ai_layer ?? "–"}</span></div>
          <div><span>Submitted</span><span>{d.submitted_by ?? "–"} · {shortDate(d.submitted_at)}</span></div>
        </div>
        {d.provisional && <p className="nf-side-small">* Preview – not assessed by the pipeline yet.</p>}
      </section>
      <section className="card lc-side-card">
        <h2 className="lc-h2">Team</h2>
        <ul className="lc-team">
          {[["owner", d.owner], ["use case lead", d.lead]].map(([role, o]) => (
            <li key={role as string}>
              <span className="avatar lc-avatar" aria-hidden="true">{initials((o as { name?: string } | null)?.name)}</span>
              <span>{(o as { name?: string } | null)?.name ?? "–"} <span className="muted">· {role as string}</span></span>
            </li>
          ))}
        </ul>
        <p className="nf-side-small">Submitter, owner and lead can edit.</p>
      </section>
    </aside>
  );

  return (
    <div className="lc">
      <header className="lc-head">
        <div>
          <span className="nf-crumb"><Link to="/my">My use cases</Link> / {d.id > 0 ? `AI-${String(d.id).padStart(4, "0")}` : "new idea"}</span>
          <h1>{d.name} <PendingTag initiative={d} /></h1>
          <p className="muted">Stage, stage gate dates, estimated costs and the details can be updated at any time.</p>
        </div>
        <span className={`lc-status lc-status-${d.approval_status ?? "excel"}`}>{approvalLabel(d.approval_status ?? null)}</span>
      </header>

      {d.processing !== "assessed" && <p className="lc-banner lc-banner-soft" role="status">{PROCESSING_HINT[d.processing ?? "assessed"]}</p>}
      {message && <p className={`lc-banner${message.kind === "error" ? " lc-banner-error" : ""}`} role={message.kind === "error" ? "alert" : "status"}>{message.text}</p>}
      {stillProcessing && <p className="lc-banner lc-banner-soft">You can edit the idea once the pipeline has processed it.</p>}

      <div className="lc-layout">
        <div className="lc-main">
          {d.approval_status === "rejected" && d.comment && (
            <div className="lc-reject" role="note">
              <b>Sent back by the approvers:</b> “{d.comment}”
            </div>
          )}

          <Section id="lc-stage" title="Stage and stage gates" subtitle="The stage decides which gates already lie in the past.">
            <label className="nf-field lc-stage">
              <span className="nf-label">Stage / maturity</span>
              <select className="nf-input" value={stage} disabled={!editable} onChange={(e) => setField("stage", e.target.value)}>
                {!stage && <option value="">Choose …</option>}
                {stages.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            {!touchesGates && d.stage_problems?.length > 0 && (
              <p className="lc-banner lc-banner-soft" role="note">Stage and gate dates do not fit yet: {d.stage_problems.join(" ")}</p>
            )}
            <GateDatesEditor stage={stage} dates={dates} saved={saved} mode="edit" rules={rules} disabled={!editable}
              showProblems={touchesGates || d.stage_problems?.length > 0}
              onChange={(gate: Stagegate, date: string) => setField(GATE_FIELD[gate], date || saved[gate])} />
          </Section>

          <Section id="lc-idea" title="The idea" subtitle="Description and estimated costs">
            <label className="nf-field">
              <span className="nf-label">Description</span>
              <textarea className="nf-input nf-textarea" rows={4} value={String(shown(draft, d, "description") ?? "")} disabled={!editable}
                onChange={(e) => setField("description", e.target.value)} />
            </label>
            <div className="lc-fields">
              <label className="nf-field">
                <span className="nf-label">One-time cost (estimate)</span>
                <select className="nf-input" value={oneTimeExact ? String(oneTime) : ""} disabled={!editable}
                  onChange={(e) => setField("one_time_costs", e.target.value ? Number(e.target.value) : "")}>
                  <option value="">{oneTime !== null && !oneTimeExact ? `${keur(oneTime)} entered – choose a range` : "Choose …"}</option>
                  {oneTimeDomain.map((o) => <option key={o.value} value={String(o.value)}>{o.label}</option>)}
                </select>
              </label>
              <label className="nf-field">
                <span className="nf-label">Running costs (estimate)</span>
                <select className="nf-input" value={String(shown(draft, d, "running_cost_range") ?? "")} disabled={!editable}
                  onChange={(e) => setField("running_cost_range", e.target.value)}>
                  <option value="">Choose …</option>
                  {costRanges.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
              </label>
            </div>
          </Section>

          <Section id="lc-details" title="Details (form 2)" subtitle={`${d.form2_progress.filled} / ${d.form2_progress.total} filled · fill in what you know, update it any time`}>
            <div className="lc-fields">
              {FORM2_FIELDS.map((f) => (
                <label key={f.key} className={`nf-field${["segmented", "multi", "bool"].includes(f.kind) ? " lc-wide" : ""}`}>
                  <span className="nf-label">{f.label}</span>
                  <FieldInput field={f} value={shown(draft, d, f.key)} onChange={(v) => setField(f.key, v)} lists={ref} disabled={!editable} />
                  {f.hint && <span className="nf-hint">{f.hint}</span>}
                </label>
              ))}
            </div>
          </Section>

          {d.can_edit ? (
            <div className="lc-actions lc-sticky">
              {problems.length > 0 && <span className="nf-error">Fix the stage gate dates first.</span>}
              <button type="button" className="lc-btn" disabled={!dirty || saving} onClick={() => setDraft({})}>Discard</button>
              {d.approval_status === "rejected" && (
                <button type="button" className="lc-btn lc-primary" disabled={!editable || problems.length > 0} onClick={() => void save({ resubmit: true })}>
                  {saving ? "Submitting …" : "Resubmit idea"}
                </button>
              )}
              <button type="button" className={`lc-btn${d.approval_status === "rejected" ? "" : " lc-primary"}`} disabled={!dirty || !editable || problems.length > 0} onClick={() => void save()}>
                {saving ? "Saving …" : "Save"}
              </button>
            </div>
          ) : (
            <p className="muted">Only the submitter, owner and lead can edit this use case.</p>
          )}
        </div>
        {side}
      </div>
    </div>
  );
}
