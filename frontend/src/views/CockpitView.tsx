import { useLayoutEffect, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import { BusinessUnitChips, StageChips } from "../components/FilterChips";
import { Kpis } from "../components/Kpis";
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
import { businessUnitOf, NO_BUSINESS_UNIT, NO_BUSINESS_UNIT_LABEL } from "../domain/filters";
import { useApp } from "../store";

// The matrix SVG is drawn at its real pixel size (view box = measured box), so text and lines are
// never scaled and stay sharp. Margins in px around the plot area:
const MARGIN = { left: 62, right: 14, top: 10, bottom: 44 };
const FALLBACK_SIZE = { w: 700, h: 380 }; // until measured (and in tests, without ResizeObserver)
const TOP_GAP = 26; // ranked dots closer than this are pushed apart so their numbers stay legible

function useBoxSize(ref: RefObject<HTMLElement>) {
  const [size, setSize] = useState(FALLBACK_SIZE);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setSize({ w: Math.round(width), h: Math.round(height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return size;
}

/** Snap a coordinate to the pixel grid's centre so 1px lines are not smeared over two pixels. */
const crisp = (v: number) => Math.round(v) + 0.5;

interface Geometry {
  left: number;
  right: number;
  top: number;
  bottom: number;
  x: (effort: number) => number;
  y: (eur: number) => number;
}

function geometry(w: number, h: number, min: number, max: number): Geometry {
  const left = MARGIN.left;
  const right = w - MARGIN.right;
  const top = MARGIN.top;
  const bottom = h - MARGIN.bottom;
  return {
    left,
    right,
    top,
    bottom,
    x: (effort) => left + ((effort - EFFORT_MIN) / (EFFORT_MAX - EFFORT_MIN)) * (right - left),
    y: (eur) => bottom - logPosition(eur, min, max) * (bottom - top),
  };
}

// The heuristic works in steps, so many initiatives share an effort score: small dots get a
// deterministic nudge, ranked dots (in rank order) step sideways until they no longer overlap.
function placeDots(points: MatrixPoint[], g: Geometry): Map<number, { cx: number; cy: number }> {
  const clampX = (x: number, pad: number) => Math.min(g.right - pad, Math.max(g.left + pad, x));
  const out = new Map<number, { cx: number; cy: number }>();
  const ranked: { cx: number; cy: number }[] = [];
  for (const p of points) {
    const base = g.x(p.effort);
    const cy = g.y(p.potential);
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
  const { all, visible } = useApp();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const { w, h } = useBoxSize(box);

  const c = cockpit(visible);
  const m = valueMatrix(visible);
  const g = geometry(w, h, m.min, m.max);
  const { left: LEFT, right: RIGHT, top: TOP, bottom: BOTTOM, y } = g;
  const splitX = crisp(g.x(EFFORT_SPLIT));
  const splitY = crisp(y(VALUE_SPLIT));
  const at = placeDots(m.points, g);
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
      <div className="filter-row">
        <BusinessUnitChips all={all} />
        <StageChips all={all} />
      </div>

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

      <Kpis items={visible} />

      <section className="card ck-section" aria-label="Where the value lies">
        <div className="ck-head">
          <h2>Where the value lies</h2>
          <span className="muted">Effort × potential · click a dot or a row</span>
        </div>
        <div className="ck-matrix">
          <div className="ck-plot">
            <div className="ck-canvas" ref={box}>
            <svg
              viewBox={`0 0 ${w} ${h}`}
              width={w}
              height={h}
              role="img"
              aria-label="Matrix of effort against potential, the ten most valuable initiatives numbered"
            >
              <rect x={LEFT} y={TOP} width={splitX - LEFT} height={splitY - TOP} className="ck-quickwin" shapeRendering="crispEdges" />
              <line x1={splitX} y1={TOP} x2={splitX} y2={BOTTOM} className="ck-split" />
              <line x1={LEFT} y1={splitY} x2={RIGHT} y2={splitY} className="ck-split" />
              {ticks.map((t) => (
                <g key={t}>
                  {t !== VALUE_SPLIT && <line x1={LEFT} y1={crisp(y(t))} x2={RIGHT} y2={crisp(y(t))} className="ck-grid" />}
                  <text x={LEFT - 8} y={Math.round(y(t)) + 4} textAnchor="end" className="ck-tick">
                    {formatTick(t)}
                  </text>
                </g>
              ))}
              <line x1={LEFT} y1={BOTTOM} x2={RIGHT} y2={BOTTOM} className="ck-axis" />
              <line x1={LEFT} y1={TOP} x2={LEFT} y2={BOTTOM} className="ck-axis" />
              <text x={LEFT + 12} y={TOP + 20} className="ck-quad ck-quad-win">Quick wins</text>
              <text x={RIGHT - 12} y={TOP + 20} textAnchor="end" className="ck-quad">Major projects</text>
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

              <text x={g.x(EFFORT_MIN)} y={BOTTOM + 18} textAnchor="middle" className="ck-tick">{EFFORT_MIN}</text>
              <text x={splitX} y={BOTTOM + 18} textAnchor="middle" className="ck-tick">{EFFORT_SPLIT}</text>
              <text x={g.x(EFFORT_MAX)} y={BOTTOM + 18} textAnchor="end" className="ck-tick">{EFFORT_MAX}</text>
              <text x={Math.round((LEFT + RIGHT) / 2)} y={h - 6} textAnchor="middle" className="ck-axis-label">
                Effort (solution complexity, {EFFORT_MIN} to {EFFORT_MAX})
              </text>
              <text
                x={12}
                y={Math.round((TOP + BOTTOM) / 2)}
                textAnchor="middle"
                transform={`rotate(-90 12 ${Math.round((TOP + BOTTOM) / 2)})`}
                className="ck-axis-label"
              >
                Potential (€ / year, log)
              </text>
            </svg>
            </div>
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
                      <span className="ck-row-name" title={p.initiative.name}>
                        {p.initiative.name}
                      </span>
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
