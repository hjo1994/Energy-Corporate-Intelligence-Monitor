import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, fetchReferenceData, fetchUseCase, updateUseCase, type ReferenceData } from "../api/client";
import type { Option, Stagegate, UseCaseDetail } from "../api/types";
import { PendingTag } from "../components/small";
import { flagshipLabel } from "../domain/format";
import {
  GATES,
  GATE_GROUPS,
  PROCESSING_HINT,
  approvalLabel,
  fieldValue,
  filledCount,
  groupOpen,
  isFilled,
  keur,
  nextGate,
  shortDate,
  todayIso,
  type Form2Field,
  type GateGroup,
} from "../domain/lifecycle";
import { riskLevelLabel } from "../domain/risk";
import { parseNumber, runningCostLabel } from "../domain/userInput";

type Draft = Record<string, unknown>;

const initials = (name: string | null | undefined) =>
  (name ?? "?")
    .split(/[\s.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");

/** The last passed gate; use cases from the Excel sheet start with the scope group open. */
function passedGate(d: UseCaseDetail): Stagegate | null {
  return d.stagegate ?? (d.approval_status === null || d.approval_status === undefined ? "Needs" : null);
}

/** A draft value as shown in its input. */
function shown(draft: Draft, d: UseCaseDetail, key: string): unknown {
  return key in draft ? draft[key] : fieldValue(d, key);
}

/** The PATCH body: only fields that differ from the saved state, in the API's types. */
export function toPatch(draft: Draft, d: UseCaseDetail): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, raw] of Object.entries(draft)) {
    const field = GATE_GROUPS.flatMap((g) => g.fields).find((f) => f.key === key);
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

function Group({ group, d, draft, setField, lists, open, editable, gateDate, setGateDate }: {
  group: GateGroup; d: UseCaseDetail; draft: Draft; setField: (k: string, v: unknown) => void; lists: ReferenceData;
  open: boolean; editable: boolean; gateDate: string; setGateDate: (v: string) => void;
}) {
  const done = filledCount(d, group);
  const passed = passedGate(d);
  const isNext = group.gate !== null && nextGate(passed) === group.gate;
  return (
    <section className={`card lc-group${open ? " open" : ""}`} aria-labelledby={`g-${group.key}`}>
      <header className="lc-group-head">
        <div>
          <h2 id={`g-${group.key}`} className="lc-h2">{group.title}</h2>
          <span className="muted">{group.subtitle}</span>
        </div>
        <span className="mono lc-count">{done} / {group.fields.length}</span>
      </header>
      {open && (
        <>
          <div className="lc-fields">
            {group.fields.map((f) => (
              <label key={f.key} className={`nf-field${["segmented", "multi", "bool"].includes(f.kind) ? " lc-wide" : ""}`}>
                <span className="nf-label">{f.label}</span>
                <FieldInput field={f} value={shown(draft, d, f.key)} onChange={(v) => setField(f.key, v)} lists={lists} disabled={!editable} />
                {f.hint && <span className="nf-hint">{f.hint}</span>}
              </label>
            ))}
          </div>
          {isNext && group.gate && group.gate !== "Retire" && (
            <label className="nf-field lc-gate">
              <span className="nf-label">{group.gate} gate passed on</span>
              <input type="date" className="nf-input" value={gateDate} max={todayIso()} disabled={!editable} onChange={(e) => setGateDate(e.target.value)} />
              <span className="nf-hint">Setting this date moves the use case to the next phase and opens the next group.</span>
            </label>
          )}
        </>
      )}
      {!open && <p className="muted lc-closed">Opens after the {group.opensAfter.toLowerCase()} gate.</p>}
    </section>
  );
}

function Stepper({ d }: { d: UseCaseDetail }) {
  const passed = passedGate(d);
  const passedIndex = passed ? GATES.indexOf(passed) : -1;
  return (
    <ol className="lc-stepper" aria-label="Stage gates">
      {GATES.map((g, i) => {
        const state = i <= passedIndex ? "done" : i === passedIndex + 1 ? "now" : "later";
        return (
          <li key={g} className={`lc-step lc-step-${state}`} aria-current={state === "now" ? "step" : undefined}>
            <span className="lc-step-dot">{state === "done" ? "✓" : i + 1}</span>
            <span>
              <b>{g} gate</b>
              <span className="lc-step-sub">
                {state === "done" ? (g === d.stagegate ? shortDate(d.passed_at) : "passed") : state === "now" ? "Now filling in" : `v${i + 1}.x`}
              </span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function UseCaseView() {
  const { id } = useParams();
  const useCaseId = Number(id);
  const [d, setD] = useState<UseCaseDetail | null>(null);
  const [ref, setRef] = useState<ReferenceData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [gateDate, setGateDate] = useState("");
  const [description, setDescription] = useState<string | null>(null);
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
  const passed = d ? passedGate(d) : null;

  if (error) {
    return (
      <div className="state card" role="alert">
        <p>{error}</p>
        <Link className="primary-link" to="/my">Back to my use cases</Link>
      </div>
    );
  }
  if (!d || !ref) return <p className="state" role="status">Loading the use case …</p>;

  const isIdea = d.approval_status === "pending" || d.approval_status === "rejected";
  const stillProcessing = d.id < 0;
  const editable = d.can_edit && !stillProcessing && !saving;
  const gate = nextGate(passed);
  const dirty = Object.keys(patch).length > 0 || (gateDate !== "" && !!gate);

  async function save(extra: Record<string, unknown> = {}) {
    if (!d) return;
    setSaving(true);
    setMessage(null);
    const body: Record<string, unknown> = { ...patch, ...extra, base_revision: d.revision };
    if (gateDate && gate && !extra.resubmit) {
      body.stagegate = gate;
      body.passed_at = gateDate;
    }
    try {
      const saved = await updateUseCase(d.id, body as never);
      setD(saved);
      setDraft({});
      setGateDate("");
      setDescription(null);
      setMessage({ kind: "ok", text: extra.resubmit ? "Resubmitted – the approvers will check it again." : "Saved. The pipeline processes the changes within about a minute." });
    } catch (err) {
      const text = err instanceof ApiError || err instanceof Error ? err.message : "The changes could not be saved.";
      setMessage({ kind: "error", text });
      if (err instanceof ApiError && err.status === 409) void load(); // someone else changed it meanwhile
    } finally {
      setSaving(false);
    }
  }

  const currentGroup = GATE_GROUPS.find((g) => g.gate === gate);
  const stillOpen = currentGroup ? currentGroup.fields.filter((f) => !isFilled(shown(draft, d, f.key))) : [];

  const side: ReactNode = (
    <aside className="lc-side" aria-label="Summary">
      <section className="card lc-side-card">
        <h2 className="lc-h2">From your idea</h2>
        <div className="lc-side-rows">
          <div><span>Potential per year</span><span className="mono">{keur(d.potential_value_eur)}{d.provisional ? " *" : ""}</span></div>
          <div><span>Realised value</span><span className="mono">{keur(d.realized_value_eur)}</span></div>
          <div><span>One-time costs</span><span className="mono">{keur(d.drivers?.one_time_costs as number | undefined ?? d.one_time_costs)}</span></div>
          <div><span>Running costs</span><span>{runningCostLabel(d.running_cost_range) ?? keur(d.running_costs)}</span></div>
          <div>
            <span>Risk level</span>
            <span>{d.risk_classification ? `${d.risk_classification.id} · ${riskLevelLabel(d.risk_classification.id)}` : "–"}</span>
          </div>
          <div><span>Flagship</span><span>{d.value_type ? flagshipLabel(d.value_type.name) : "–"}</span></div>
          <div><span>AI layer</span><span>{d.ai_layer ?? "–"}</span></div>
        </div>
        {d.provisional && <p className="nf-side-small">* Preview – not assessed by the pipeline yet.</p>}
      </section>
      {!isIdea && currentGroup && (
        <section className="card lc-side-card">
          <h2 className="lc-h2">Still open for the {gate?.toLowerCase()} gate</h2>
          {stillOpen.length === 0 ? <p className="muted">All filled in.</p> : (
            <ul className="lc-open">{stillOpen.map((f) => <li key={f.key}>{f.label}</li>)}</ul>
          )}
        </section>
      )}
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
          <p className="muted">
            {isIdea ? "Form 1 – the idea as submitted." : "Form 2 grows with your use case. Only what the next gate needs is open, the rest waits."}
          </p>
        </div>
        <span className={`lc-status lc-status-${d.approval_status ?? "excel"}`}>{approvalLabel(d.approval_status ?? null)}</span>
      </header>

      {d.processing !== "assessed" && <p className="lc-banner lc-banner-soft" role="status">{PROCESSING_HINT[d.processing ?? "assessed"]}</p>}
      {message && <p className={`lc-banner${message.kind === "error" ? " lc-banner-error" : ""}`} role={message.kind === "error" ? "alert" : "status"}>{message.text}</p>}

      <div className="lc-layout">
        <div className="lc-main">
          {isIdea ? (
            <section className="card lc-group open" aria-labelledby="lc-idea">
              <h2 id="lc-idea" className="lc-h2">Your idea</h2>
              {d.approval_status === "rejected" && d.comment && (
                <div className="lc-reject" role="note">
                  <b>Sent back by the approvers:</b> “{d.comment}”
                </div>
              )}
              <label className="nf-field">
                <span className="nf-label">Description</span>
                <textarea className="nf-input nf-textarea" rows={4} value={description ?? d.description ?? ""} disabled={!editable}
                  onChange={(e) => setDescription(e.target.value)} />
              </label>
              <div className="lc-side-rows">
                <div><span>Owner</span><span>{d.owner?.name ?? "–"}</span></div>
                <div><span>Stage</span><span>{d.stage ?? "–"}</span></div>
                <div><span>Submitted</span><span>{d.submitted_by ?? "–"} · {shortDate(d.submitted_at)}</span></div>
              </div>
              {stillProcessing && <p className="muted">You can edit the idea once the pipeline has processed it.</p>}
              {d.can_edit && !stillProcessing && (
                <div className="lc-actions">
                  {d.approval_status === "rejected" ? (
                    <button type="button" className="lc-btn lc-primary" disabled={saving}
                      onClick={() => void save(description !== null && description.trim() && description.trim() !== d.description ? { description: description.trim(), resubmit: true } : { resubmit: true })}>
                      {saving ? "Submitting …" : "Resubmit idea"}
                    </button>
                  ) : (
                    <button type="button" className="lc-btn lc-primary" disabled={saving || description === null || !description.trim() || description.trim() === d.description}
                      onClick={() => void save({ description: description?.trim() })}>
                      {saving ? "Saving …" : "Save changes"}
                    </button>
                  )}
                </div>
              )}
            </section>
          ) : (
            <>
              <Stepper d={d} />
              {GATE_GROUPS.map((g) => (
                <Group key={g.key} group={g} d={d} draft={draft} lists={ref} open={groupOpen(g, passed)} editable={editable}
                  setField={(k, v) => setDraft((x) => ({ ...x, [k]: v }))} gateDate={gateDate} setGateDate={setGateDate} />
              ))}
              {d.can_edit && (
                <div className="lc-actions lc-sticky">
                  <span className="muted">{d.form2_progress.filled} / {d.form2_progress.total} details filled</span>
                  <button type="button" className="lc-btn" disabled={!dirty || saving} onClick={() => { setDraft({}); setGateDate(""); }}>Discard</button>
                  <button type="button" className="lc-btn lc-primary" disabled={!dirty || !editable} onClick={() => void save()}>
                    {saving ? "Saving …" : gateDate && gate ? `Save and pass the ${gate.toLowerCase()} gate` : "Save"}
                  </button>
                </div>
              )}
              {!d.can_edit && <p className="muted">Only the submitter, owner and lead can edit this use case.</p>}
            </>
          )}
        </div>
        {side}
      </div>
    </div>
  );
}
