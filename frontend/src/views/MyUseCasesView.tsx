import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { fetchMyUseCases } from "../api/client";
import type { MyUseCase } from "../api/types";
import { PendingTag } from "../components/small";
import { ROLE_LABEL, approvalLabel, keur, nextGate, shortDate } from "../domain/lifecycle";
import { useApp } from "../store";

type Role = "all" | "owner" | "lead" | "submitter";

const ROLE_FILTERS: [Role, string][] = [
  ["all", "All"],
  ["owner", "Owner"],
  ["lead", "Lead"],
  ["submitter", "Submitted by me"],
];

// re-read while the pipeline still has to process something of mine
const POLL_MS = 5000;

/** The next step for a use case, as the button in its row. */
function action(u: MyUseCase): { label: string; primary: boolean } {
  if (u.todos.includes("revise_and_resubmit")) return { label: "Revise", primary: true };
  if (u.todos.includes("complete_details")) return { label: "Form 2", primary: true };
  if (u.approval_status === "pending" && u.can_edit) return { label: "Edit idea", primary: false };
  return { label: "Open", primary: false };
}

function attention(u: MyUseCase): { title: string; detail: string; button: string } | null {
  if (u.todos.includes("revise_and_resubmit")) {
    return { title: "Rejected – revise and resubmit", detail: u.comment ? `“${u.comment}”` : u.name, button: "Revise" };
  }
  if (u.todos.includes("complete_details")) {
    const gate = nextGate(u.stagegate);
    return {
      title: "Approved – add the details",
      detail: `${u.form2_progress.filled} / ${u.form2_progress.total} details filled${gate ? ` · next: ${gate} gate` : ""}`,
      button: "Fill in Form 2",
    };
  }
  return null;
}

export function MyUseCasesView() {
  const { rights } = useApp();
  const location = useLocation();
  const created = (location.state as { created?: string } | null)?.created;
  const [items, setItems] = useState<MyUseCase[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [role, setRole] = useState<Role>("all");
  const itemsRef = useRef<MyUseCase[] | null>(null);
  itemsRef.current = items;

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      fetchMyUseCases().then(
        (data) => !cancelled && setItems(Array.isArray(data) ? data : []),
        (err: unknown) => !cancelled && setError(err instanceof Error ? err.message : "Your use cases could not be loaded."),
      );
    void load();
    const timer = setInterval(() => {
      // silent refresh, only while something is waiting for the pipeline
      if (itemsRef.current?.some((u) => u.processing === "pending" || u.processing === "changes_pending")) void load();
    }, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const shown = useMemo(() => (items ?? []).filter((u) => role === "all" || u.roles.includes(role)), [items, role]);

  if (error) {
    return (
      <div className="state card" role="alert">
        <p>{error}</p>
      </div>
    );
  }
  if (!items) return <p className="state" role="status">Loading your use cases …</p>;

  const pending = items.filter((u) => u.approval_status === "pending").length;
  const rejected = items.filter((u) => u.approval_status === "rejected").length;
  const todo = items.filter((u) => u.todos.length > 0);
  const approved = items.filter((u) => u.approval_status !== "pending" && u.approval_status !== "rejected");
  const potential = approved.reduce((sum, u) => sum + (u.potential_value_eur ?? 0), 0);
  const count = (r: Role) => items.filter((u) => r === "all" || u.roles.includes(r)).length;

  return (
    <div className="lc">
      <header className="lc-head">
        <div>
          <h1>My use cases</h1>
          <p className="muted">Everything you submitted, own or lead.</p>
        </div>
        <div className="chip-group" role="group" aria-label="Filter by role">
          {ROLE_FILTERS.map(([r, label]) => (
            <button key={r} type="button" className={`chip${role === r ? " active" : ""}`} aria-pressed={role === r} onClick={() => setRole(r)}>
              {label} {count(r)}
            </button>
          ))}
        </div>
      </header>

      {created && (
        <p className="lc-banner" role="status">
          “{created}” was submitted. An approver will check it; you will find it here in the meantime.
        </p>
      )}

      <section className="kpis" aria-label="Overview">
        <div className="card kpi">
          <span className="kpi-label">My use cases</span>
          <span className="kpi-value mono">{items.length}</span>
          <span className="kpi-note">{pending} pending, {rejected} rejected</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">Need your input</span>
          <span className="kpi-value mono">{todo.length}</span>
          <span className="kpi-note">Form 2, revisions</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">Potential value</span>
          <span className="kpi-value mono">{keur(potential)}</span>
          <span className="kpi-note">per year, approved only</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">Your rights</span>
          <span className="kpi-value lc-kpi-text">{rights.canAdmin ? "Admin" : rights.canApprove ? "Approver" : "Submitter"}</span>
          <span className="kpi-note">{rights.canApprove ? "You can decide on new ideas" : "Approvers decide on new ideas"}</span>
        </div>
      </section>

      {todo.length > 0 && (
        <section className="card lc-attention" aria-labelledby="lc-attention">
          <h2 id="lc-attention" className="lc-h2">Needs your attention</h2>
          <ul>
            {todo.map((u) => {
              const a = attention(u);
              if (!a) return null;
              return (
                <li key={u.id}>
                  <div>
                    <div className="lc-att-title">{a.title}</div>
                    <div className="muted lc-att-detail">{u.name} · {a.detail}</div>
                  </div>
                  <Link className="lc-btn lc-primary" to={`/use-cases/${u.id}`}>{a.button}</Link>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <section className="card lc-table-card" aria-label="My use cases">
        {shown.length === 0 ? (
          <div className="state">
            <p>No use cases yet.</p>
            <Link className="primary-link" to="/new">Add a new AI idea</Link>
          </div>
        ) : (
          <table className="lc-table">
            <thead>
              <tr>
                <th>Use case</th>
                <th>My role</th>
                <th>Approval</th>
                <th>Stage</th>
                <th>Last gate</th>
                <th className="num">Potential value</th>
                <th>Risk</th>
                <th><span className="sr-only">Action</span></th>
              </tr>
            </thead>
            <tbody>
              {shown.map((u) => {
                const a = action(u);
                return (
                  <tr key={u.id}>
                    <td>
                      <Link className="lc-name" to={`/use-cases/${u.id}`}>{u.name}</Link>
                      <div className="lc-sub">
                        {u.id > 0 ? `AI-${String(u.id).padStart(4, "0")}` : "new"}
                        {u.approval_status === null && <span className="tag">from Excel</span>}
                        <PendingTag initiative={{ status: u.processing === "pending" ? "pending" : "active", processing: u.processing }} />
                      </div>
                      {u.approval_status === "rejected" && u.comment && <div className="lc-comment">“{u.comment}”</div>}
                    </td>
                    <td>{u.roles.map((r) => ROLE_LABEL[r]).join(", ")}</td>
                    <td><span className={`lc-status lc-status-${u.approval_status ?? "excel"}`}>{approvalLabel(u.approval_status)}</span></td>
                    <td>{u.stage ?? "–"}</td>
                    <td>{u.stagegate ? `${u.stagegate} · ${shortDate(u.passed_at)}` : "–"}</td>
                    <td className="num mono">
                      {keur(u.potential_value_eur)}
                      {u.provisional && u.potential_value_eur !== null && <span className="lc-prov" title="Preview, not assessed yet">*</span>}
                    </td>
                    <td>{u.risk_classification ? <span className={`nf-risk nf-risk-${u.risk_classification.id}`}>{u.risk_classification.id}</span> : "–"}</td>
                    <td>
                      <Link className={`lc-btn${a.primary ? " lc-primary" : ""}`} to={`/use-cases/${u.id}`} aria-label={`${a.label}: ${u.name}`}>
                        {a.label}
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {shown.some((u) => u.provisional) && <p className="note lc-note">* Preview: the pipeline has not assessed this value yet.</p>}
      </section>
    </div>
  );
}
