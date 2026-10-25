import { useState, type KeyboardEvent } from "react";
import {
  cockpit,
  EFFORT_MAX,
  EFFORT_MIN,
  EFFORT_SPLIT,
  formatKEur,
  formatMEur,
  formatTick,
  logPosition,
  VALUE_SPLIT,
  valueMatrix,
  type MatrixPoint,
} from "../domain/cockpit";
import { businessUnitOf, EMPTY_FILTERS, NO_BUSINESS_UNIT, NO_BUSINESS_UNIT_LABEL } from "../domain/filters";
import { useApp } from "../store";

// Matrix geometry in SVG units: the plot spans LEFT..RIGHT and TOP..BOTTOM of a 700 × 450 view box.
const LEFT = 60;
const RIGHT = 680;
const TOP = 20;
const BOTTOM = 400;
const effortX = (effort: number) => LEFT + ((effort - EFFORT_MIN) / (EFFORT_MAX - EFFORT_MIN)) * (RIGHT - LEFT);
const clampX = (x: number, pad: number) => Math.min(RIGHT - pad, Math.max(LEFT + pad, x));
const TOP_GAP = 26; // ranked dots closer than this are pushed apart so their numbers stay legible

// The heuristic works in steps, so many initiatives share an effort score: small dots get a
// deterministic nudge, ranked dots (in rank order) step sideways until they no longer overlap.
function placeDots(points: MatrixPoint[], y: (eur: number) => number): Map<number, { cx: number; cy: number }> {
  const out = new Map<number, { cx: number; cy: number }>();
  const ranked: { cx: number; cy: number }[] = [];
  for (const p of points) {
    const base = effortX(p.effort);
    const cy = y(p.potential);
    if (p.rank === null) {
      out.set(p.initiative.id, { cx: clampX(base + (((p.initiative.id * 7) % 9) - 4) * 4, 6), cy });
      continue;
    }
    let cx = clampX(base, 14);
    for (let k = 1; k < 20 && ranked.some((r) => Math.hypot(r.cx - cx, r.cy - cy) < TOP_GAP); k++) {
      cx = clampX(base + (k % 2 ? 1 : -1) * Math.ceil(k / 2) * TOP_GAP, 14);
    }
    ranked.push({ cx, cy });
    out.set(p.initiative.id, { cx, cy });
  }
  return out;
}

const buLabel = (p: MatrixPoint) => {
  const bu = businessUnitOf(p.initiative);
  return bu === NO_BUSINESS_UNIT ? NO_BUSINESS_UNIT_LABEL : bu;
};
const tip = (p: MatrixPoint) => `${p.initiative.name} · ${buLabel(p)} · ${p.initiative.stage} · ${formatKEur(p.potential)}`;

function Bars({ rows, tone }: { rows: { label: string; potential: number }[]; tone: "bu" | "driver" }) {
  const largest = Math.max(1, ...rows.map((r) => r.potential));
  if (rows.length === 0) return <p className="empty small">No initiatives with an estimated value.</p>;
  return (
    <div className="ck-bars">
      {rows.map((r) => (
        <div key={r.label} className="ck-bar-row">
          <span className="ck-bar-label">{r.label}</span>
          <span className="ck-track">
            <span className={`ck-fill ck-fill-${tone}`} style={{ width: `${(Math.max(0, r.potential) / largest) * 100}%` }} />
          </span>
          <span className="mono ck-bar-value">{formatMEur(r.potential)}</span>
        </div>
      ))}
    </div>
  );
}

export function CockpitView() {
  const { all, visible, setFilters } = useApp();
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const c = cockpit(visible);
  const m = valueMatrix(visible);
  const y = (eur: number) => BOTTOM - logPosition(eur, m.min, m.max) * (BOTTOM - TOP);
  const splitX = effortX(EFFORT_SPLIT);
  const splitY = y(VALUE_SPLIT);
  const at = placeDots(m.points, y);
  const ticks: number[] = [];
  for (let v = m.min; v <= m.max; v *= 10) ticks.push(v);

  const pick = (id: number) => setSelectedId((cur) => (cur === id ? null : id));
  const onKey = (id: number) => (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      pick(id);
    }
  };
  const asOf = new Date().toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

  return (
    <div className="cockpit">
      {visible.length < all.length && (
        <p className="ck-filtered" role="status">
          Showing {visible.length} of {all.length} initiatives (filters active).{" "}
          <button type="button" className="link-btn" onClick={() => setFilters(() => EMPTY_FILTERS)}>
            Show all
          </button>
        </p>
      )}

      <section className="ck-hero" aria-label="Estimated value">
        <div className="ck-hero-main">
          <div className="ck-hero-top">
            <span className="ck-eyebrow">
              Our {c.total} AI initiatives are estimated to create
            </span>
            <span className="ck-badge">Estimate</span>
          </div>
          <div className="ck-hero-figure">
            <span className="mono ck-total">{formatMEur(c.potential)}</span>
            <span className="ck-total-note">
              per year, net <strong>{formatMEur(c.net, true)}</strong> after costs
            </span>
          </div>
          {c.valued < c.total && (
            <span className="ck-hero-small">
              Based on the {c.valued} initiatives with an estimated value and cost.
            </span>
          )}
        </div>
        <div className="ck-hero-kpis">
          <div>
            <span className="mono">{formatMEur(c.live)}</span>
            <span>already delivering today</span>
          </div>
          <div>
            <span className="mono">
              {c.selfFunding} / {c.valued}
            </span>
            <span>cover their own costs</span>
          </div>
          <div>
            <span className="mono">{formatMEur(c.scheduled.potential)}</span>
            <span>scheduled by {c.scheduled.until}</span>
          </div>
        </div>
      </section>

      <section className="card ck-section" aria-label="Where the value lies">
        <div className="ck-head">
          <h2>Where the value lies</h2>
          <span className="muted">Effort × potential · click a dot or a row</span>
        </div>
        <div className="ck-matrix">
          <div className="ck-plot">
            <svg
              viewBox="0 0 700 450"
              width="100%"
              role="img"
              aria-label="Matrix of effort against potential, the ten most valuable initiatives numbered"
            >
              <rect x={LEFT} y={TOP} width={splitX - LEFT} height={splitY - TOP} className="ck-quickwin" />
              <line x1={splitX} y1={TOP} x2={splitX} y2={BOTTOM} className="ck-split" />
              <line x1={LEFT} y1={splitY} x2={RIGHT} y2={splitY} className="ck-split" />
              {ticks.map((t) => (
                <g key={t}>
                  {t !== VALUE_SPLIT && <line x1={LEFT} y1={y(t)} x2={RIGHT} y2={y(t)} className="ck-grid" />}
                  <text x={LEFT - 8} y={y(t) + 4} textAnchor="end" className="ck-tick">
                    {formatTick(t)}
                  </text>
                </g>
              ))}
              <line x1={LEFT} y1={BOTTOM} x2={RIGHT} y2={BOTTOM} className="ck-axis" />
              <line x1={LEFT} y1={TOP} x2={LEFT} y2={BOTTOM} className="ck-axis" />
              <text x={LEFT + 12} y={TOP + 22} className="ck-quad ck-quad-win">Quick wins</text>
              <text x={RIGHT - 12} y={TOP + 22} textAnchor="end" className="ck-quad">Major projects</text>
              <text x={LEFT + 12} y={BOTTOM - 12} className="ck-quad ck-quad-muted">Small helpers</text>
              <text x={RIGHT - 12} y={BOTTOM - 12} textAnchor="end" className="ck-quad ck-quad-review">Review</text>

              {m.points
                .filter((p) => p.rank === null)
                .map((p) => (
                  <circle
                    key={p.initiative.id}
                    cx={at.get(p.initiative.id)?.cx}
                    cy={at.get(p.initiative.id)?.cy}
                    r={5}
                    className="ck-dot-small"
                  >
                    <title>{tip(p)}</title>
                  </circle>
                ))}
              {[...m.top].reverse().map((p) => {
                const active = p.initiative.id === selectedId;
                const { cx, cy } = at.get(p.initiative.id) as { cx: number; cy: number };
                return (
                  <g
                    key={p.initiative.id}
                    role="button"
                    tabIndex={0}
                    aria-label={`#${p.rank} ${p.initiative.name}`}
                    aria-pressed={active}
                    className={`ck-dot${active ? " sel" : ""}`}
                    onClick={() => pick(p.initiative.id)}
                    onKeyDown={onKey(p.initiative.id)}
                  >
                    <circle cx={cx} cy={cy} r={active ? 14 : 11}>
                      <title>{tip(p)}</title>
                    </circle>
                    <text x={cx} y={cy + 4} textAnchor="middle">
                      {p.rank}
                    </text>
                  </g>
                );
              })}

              <text x={effortX(EFFORT_MIN)} y={420} textAnchor="middle" className="ck-tick">{EFFORT_MIN}</text>
              <text x={splitX} y={420} textAnchor="middle" className="ck-tick">{EFFORT_SPLIT}</text>
              <text x={effortX(EFFORT_MAX)} y={420} textAnchor="middle" className="ck-tick">{EFFORT_MAX}</text>
              <text x={(LEFT + RIGHT) / 2} y={444} textAnchor="middle" className="ck-axis-label">
                Effort (solution complexity, {EFFORT_MIN} to {EFFORT_MAX})
              </text>
              <text x={14} y={(TOP + BOTTOM) / 2} textAnchor="middle" transform={`rotate(-90 14 ${(TOP + BOTTOM) / 2})`} className="ck-axis-label">
                Potential (€ / year, log)
              </text>
            </svg>
            <p className="muted ck-note">
              {m.plotted} of {m.estimated} initiatives have an effort estimate
              {m.coverage !== null && `, covering ${Math.round(m.coverage * 100)} % of the potential`}.
            </p>
          </div>

          <ol className="ck-top" aria-label="Top 10 by potential">
            {m.top.length === 0 && <li className="empty small">No initiatives with effort and potential.</li>}
            {m.top.map((p) => {
              const active = p.initiative.id === selectedId;
              return (
                <li key={p.initiative.id}>
                  <button
                    type="button"
                    className={`ck-row${active ? " sel" : ""}`}
                    aria-pressed={active}
                    onClick={() => pick(p.initiative.id)}
                  >
                    <span className="mono ck-rank">{p.rank}</span>
                    <span className="ck-row-text">
                      <span className="ck-row-name">{p.initiative.name}</span>
                      <span className="ck-row-meta">
                        {buLabel(p)} · {p.initiative.stage}
                      </span>
                    </span>
                    <span className="mono ck-row-value">{formatKEur(p.potential)}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        </div>
      </section>

      <div className="ck-cards">
        <section className="card ck-section" aria-label="Value by business unit">
          <h2>Value by business unit</h2>
          <Bars rows={c.byBusinessUnit} tone="bu" />
        </section>
        <section className="card ck-section" aria-label="What drives the value">
          <h2>What drives the value</h2>
          <Bars rows={c.drivers} tone="driver" />
        </section>
      </div>

      <footer className="ck-footer">
        <span>
          <strong>All values are estimates</strong>, weighted by confidence and delivery likelihood.
        </span>
        <span>As of {asOf}</span>
      </footer>
    </div>
  );
}
