import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, decideUseCase, fetchApprovals, fetchReferenceData, fetchSimilar, fetchUseCase, type ReferenceData } from "../api/client";
import type { ApprovalItem, SimilarUseCase, UseCaseDetail } from "../api/types";
import { PendingTag } from "../components/small";
import { flagshipLabel } from "../domain/format";
import { age, keur, shortDate, todayIso } from "../domain/lifecycle";
import { riskActions, riskLevelLabel } from "../domain/risk";
import { runningCostLabel } from "../domain/userInput";

const ANSWERS: [keyof UseCaseDetail, string][] = [
  ["employee_personal_data", "Personal data of employees"],
  ["performance_or_behaviour_control", "Performance or behaviour monitoring"],
  ["decisions_on_employees", "Decisions about employees"],
  ["profiling_of_individuals", "Profiling of individuals"],
  ["changes_employee_workflows", "Changes how employees work"],
  ["prohibited_practice", "Prohibited practice"],
];

const answerText = (v: unknown) => (v === true ? "yes" : v === false ? "no" : v === null || v === undefined ? "–" : String(v));
const allNo = (d: UseCaseDetail) => ANSWERS.every(([k]) => d[k] === false || d[k] === "no" || d[k] === "none");

function valueLine(d: UseCaseDetail): string | null {
  const buckets: [string, number | null][] = [
    ["efficiency", d.efficiency_score_eur],
    ["quality", d.quality_score_eur],
    ["risk reduction", d.risk_reduction_score_eur],
    ["speed", d.strategic_value_score_eur],
  ];
  const top = buckets.filter(([, v]) => (v ?? 0) > 0).sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0))[0];
  return top ? `Mostly ${top[0]}: ${keur(top[1])} of ${keur(d.hypothetical_value_eur)} per year` : null;
}

function Decision({ d, lists, onDone }: { d: UseCaseDetail; lists: ReferenceData; onDone: (name: string, approved: boolean) => void }) {
  const [leadId, setLeadId] = useState(d.owner?.id ? String(d.owner.id) : "");
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tried, setTried] = useState<"approve" | "reject" | null>(null);

  async function decide(decision: "approve" | "reject") {
    setTried(decision);
    setError(null);
    if (decision === "approve" && !leadId) return;
    if (decision === "reject" && !comment.trim()) return;
    setSaving(true);
    try {
      await decideUseCase(d.id, {
        decision,
        base_revision: d.revision,
        ...(decision === "approve" ? { lead_id: Number(leadId) } : {}),
        ...(comment.trim() ? { comment: comment.trim() } : {}),
      });
      onDone(d.name, decision === "approve");
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : "The decision could not be saved.");
      setSaving(false);
    }
  }

  return (
    <section className="lc-decision" aria-labelledby="ap-decision">
      <h3 id="ap-decision" className="lc-h3">Decision</h3>
      <div className="lc-fields">
        <label className="nf-field">
          <span className="nf-label">Assign use case lead <b aria-hidden="true">*</b></span>
          <select className="nf-input" value={leadId} onChange={(e) => setLeadId(e.target.value)}>
            <option value="">Choose …</option>
            {lists.owners.map((o) => <option key={o.id} value={o.id}>{o.category ? `${o.name} · ${o.category}` : o.name}</option>)}
          </select>
          {tried === "approve" && !leadId ? <span className="nf-error">Required to approve.</span> : <span className="nf-hint">required to approve</span>}
        </label>
        <p className="nf-hint lc-decision-note">
          {d.needs_gate_date && d.needs_gate_date.slice(0, 10) <= todayIso()
            ? `The submitter dated the needs gate ${shortDate(d.needs_gate_date)}; approving keeps that date.`
            : "Approving passes the needs gate today."}
        </p>
      </div>
      <label className="nf-field">
        <span className="nf-label">Comment to the submitter</span>
        <textarea className="nf-input nf-textarea" rows={3} value={comment} maxLength={1000} onChange={(e) => setComment(e.target.value)} />
        {tried === "reject" && !comment.trim() ? <span className="nf-error">Tell the submitter why it goes back.</span> : <span className="nf-hint">required to reject</span>}
      </label>
      {error && <p className="nf-save-error" role="alert">{error}</p>}
      <div className="lc-actions">
        <button type="button" className="lc-btn lc-danger" disabled={saving || !d.can_decide} onClick={() => void decide("reject")}>Reject</button>
        <button type="button" className="lc-btn lc-primary" disabled={saving || !d.can_decide} onClick={() => void decide("approve")}>
          {saving ? "Saving …" : "Approve & assign lead"}
        </button>
      </div>
      {!d.can_decide && <p className="muted">The idea is still being processed – you can decide in about a minute.</p>}
    </section>
  );
}

export function ApprovalsView() {
  const [items, setItems] = useState<ApprovalItem[] | null>(null);
  const [lists, setLists] = useState<ReferenceData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<UseCaseDetail | null>(null);
  const [similar, setSimilar] = useState<SimilarUseCase[]>([]);
  const [showAnswers, setShowAnswers] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchApprovals();
      const list = Array.isArray(data) ? data : [];
      setItems(list);
      setSelected((s) => (s !== null && list.some((i) => i.id === s) ? s : list[0]?.id ?? null));
    } catch (err) {
      setError(err instanceof ApiError && err.status === 403 ? "Only approvers can see the inbox." : err instanceof Error ? err.message : "The inbox could not be loaded.");
    }
  }, []);

  useEffect(() => {
    void load();
    fetchReferenceData().then(setLists, () => undefined);
  }, [load]);

  useEffect(() => {
    if (selected === null) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetail(null);
    setSimilar([]);
    setShowAnswers(false);
    fetchUseCase(selected).then((d) => !cancelled && setDetail(d), () => undefined);
    if (selected > 0) fetchSimilar(selected).then((s) => !cancelled && setSimilar(s));
    return () => {
      cancelled = true;
    };
  }, [selected]);

  if (error) {
    return (
      <div className="state card" role="alert">
        <p>{error}</p>
      </div>
    );
  }
  if (!items) return <p className="state" role="status">Loading the inbox …</p>;

  return (
    <div className="lc">
      <header className="lc-head">
        <div>
          <h1>Approvals</h1>
          <p className="muted">
            New AI ideas waiting for the needs gate. Value check, risk check, re-use check – then approve and assign a lead, or send back.
          </p>
        </div>
        <span className="chip active">Pending {items.length}</span>
      </header>
      {done && <p className="lc-banner" role="status">{done}</p>}

      {items.length === 0 ? (
        <div className="card state"><p>No ideas are waiting for a decision.</p></div>
      ) : (
        <div className="lc-inbox">
          <ul className="card lc-inbox-list" aria-label="Pending ideas">
            {items.map((i) => (
              <li key={i.id}>
                <button type="button" className={`lc-inbox-item${i.id === selected ? " on" : ""}`} aria-pressed={i.id === selected} onClick={() => setSelected(i.id)}>
                  <span className="lc-inbox-name">{i.name}</span>
                  <span className="lc-sub">
                    {i.id > 0 ? `AI-${String(i.id).padStart(4, "0")}` : "new"} · {i.owner?.category ?? "–"} · {age(i.submitted_at)}
                    <PendingTag initiative={{ status: "active", processing: i.processing }} />
                  </span>
                  <span className="lc-inbox-figs">
                    <span className="mono">{keur(i.potential_value_eur)}</span>
                    {i.risk_classification && <span className={`nf-risk nf-risk-${i.risk_classification.id}`}>{i.risk_classification.id}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>

          <section className="card lc-inbox-detail" aria-label="Selected idea">
            {!detail || !lists ? (
              <p className="state" role="status">Loading …</p>
            ) : (
              <>
                <header className="lc-detail-head">
                  <h2 className="lc-h2">{detail.name}</h2>
                  <span className="lc-status lc-status-pending">Pending</span>
                </header>
                <p className="lc-sub">
                  {detail.ai_layer ?? "–"} · {detail.value_type ? flagshipLabel(detail.value_type.name) : "–"} · submitted by {detail.submitted_by ?? "–"}
                  {" "}· {shortDate(detail.submitted_at)} · owner {detail.owner?.name ?? "–"}
                </p>
                <p>{detail.description}</p>

                <div className="lc-checks">
                  <div className="lc-check">
                    <h3 className="lc-h3">Value check</h3>
                    <span className="mono lc-big">{keur(detail.potential_value_eur)}</span>
                    <span className="nf-side-small">
                      potential / yr · {keur(detail.hypothetical_value_eur)} × {detail.confidence_score?.toFixed(2) ?? "–"} × {detail.delivery_score?.toFixed(2) ?? "–"}
                    </span>
                    {valueLine(detail) && <span className="nf-side-small">{valueLine(detail)}</span>}
                  </div>
                  <div className="lc-check">
                    <h3 className="lc-h3">Risk check</h3>
                    {detail.risk_classification ? (
                      <span className={`nf-risk nf-risk-${detail.risk_classification.id}`}>
                        Level {detail.risk_classification.id} · {riskLevelLabel(detail.risk_classification.id)}
                      </span>
                    ) : <span>–</span>}
                    <span className="nf-side-small">
                      {allNo(detail) ? "All 6 people questions answered “no”." : detail.risk_classification ? riskActions(detail.risk_classification.id) : ""}
                    </span>
                    <button type="button" className="lc-link" aria-expanded={showAnswers} onClick={() => setShowAnswers((s) => !s)}>
                      {showAnswers ? "Hide answers" : "Show answers"}
                    </button>
                    {showAnswers && (
                      <dl className="lc-answers">
                        {ANSWERS.map(([k, label]) => (
                          <div key={k}><dt>{label}</dt><dd>{answerText(detail[k])}</dd></div>
                        ))}
                      </dl>
                    )}
                  </div>
                  <div className="lc-check">
                    <h3 className="lc-h3">Effort</h3>
                    <span className="mono lc-big">{detail.solution_complexity_score ?? "–"} <span className="muted">/ 9</span></span>
                    <span className="nf-side-small">
                      {keur(detail.drivers?.one_time_costs as number | undefined ?? detail.one_time_costs)} one-time · {runningCostLabel(detail.running_cost_range) ?? keur(detail.running_costs)}
                    </span>
                  </div>
                </div>

                <section aria-labelledby="ap-similar">
                  <h3 id="ap-similar" className="lc-h3">Re-use check – similar initiatives <span className="muted">matched on name and description</span></h3>
                  {similar.length === 0 ? <p className="muted">No similar initiatives found.</p> : (
                    <ul className="lc-similar">
                      {similar.map((s) => (
                        <li key={s.id}>
                          <span>
                            <b>{s.name}</b>
                            <span className="lc-sub"> {s.owner?.category ?? "–"} · AI-{String(s.id).padStart(4, "0")} · owner {s.owner?.name ?? "–"}</span>
                          </span>
                          <span className="tag">{s.stage ?? "–"}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>

                <Decision key={detail.id} d={detail} lists={lists}
                  onDone={(name, approved) => {
                    setDone(approved ? `“${name}” was approved. The lead can now fill in the details.` : `“${name}” was sent back to the submitter.`);
                    void load();
                  }} />
                <p className="nf-side-small"><Link to={`/use-cases/${detail.id}`}>Open the full use case</Link></p>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
