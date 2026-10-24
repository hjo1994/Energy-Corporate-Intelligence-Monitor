import type { Initiative } from "../api/types";
import { formatEur } from "../domain/format";
import { formatMillions, formatSignedEur, valueBridge, waterfallSteps } from "../domain/value";

// Waterfall geometry in SVG units.
const W = 1200;
const TOP = 34;
const BOTTOM = 380;
const BAR = 130;
const SLOT = 190;
const LEFT = 60;

/** A · From the hypothetical value to the net value per year, as a waterfall. */
export function ValueBridge({ items }: { items: Initiative[] }) {
  const b = valueBridge(items);
  const steps = waterfallSteps(b);
  const max = Math.max(0, ...steps.flatMap((s) => [s.from, s.to]));
  const min = Math.min(0, ...steps.flatMap((s) => [s.from, s.to]));
  const y = (v: number) => TOP + ((max - v) / (max - min || 1)) * (BOTTOM - TOP);
  const largestBucket = Math.max(1, ...b.buckets.map((x) => x.potential));
  const haircutShare = b.hypothetical > 0 ? b.confidenceHaircut / b.hypothetical : null;

  const label = steps
    .map((s) => `${s.label} ${formatMillions(s.kind === "haircut" || s.kind === "cost" ? s.to - s.from : s.to)}`)
    .join(", ");

  return (
    <section className="value-section" aria-label="Value bridge">
      <div className="value-head">
        <h2>Value bridge</h2>
        <p className="muted">
          From the hypothetical value to the estimated potential and, after the expected annual cost (weighted by
          delivery, like the potential), the net value per year.
        </p>
      </div>
      <div className="value-split">
        <div className="card value-chart">
          {b.valued === 0 ? (
            <p className="empty">No initiative with estimated potential and cost matches the filters.</p>
          ) : (
            <svg viewBox={`0 0 ${W} 450`} width="100%" role="img" aria-label={`Waterfall in M € per year: ${label}`}>
              <defs>
                <pattern id="haircut-hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                  <rect width="8" height="8" className="hatch-bg" />
                  <line x1="0" y1="0" x2="0" y2="8" className="hatch-line" strokeWidth="3" />
                </pattern>
              </defs>
              {steps.slice(0, -1).map((s, k) => (
                <line
                  key={s.label}
                  className="wf-connector"
                  x1={LEFT + k * SLOT + BAR}
                  x2={LEFT + (k + 1) * SLOT}
                  y1={y(s.to)}
                  y2={y(s.to)}
                />
              ))}
              {steps.map((s, k) => {
                const x = LEFT + k * SLOT;
                const top = y(Math.max(s.from, s.to));
                const bottom = y(Math.min(s.from, s.to));
                const negativeNet = s.kind === "net" && s.to < 0;
                const shown = s.kind === "haircut" || s.kind === "cost" ? s.to - s.from : s.to;
                return (
                  <g key={s.label}>
                    <rect
                      className={`wf-bar wf-${s.kind}${negativeNet ? " wf-below" : ""}`}
                      x={x}
                      y={top}
                      width={BAR}
                      height={Math.max(1, bottom - top)}
                      rx="3"
                    />
                    <text
                      className={`wf-value wf-value-${s.kind}`}
                      x={x + BAR / 2}
                      y={negativeNet ? bottom + 24 : s.kind === "haircut" ? (top + bottom) / 2 + 8 : top - 10}
                      textAnchor="middle"
                    >
                      {formatMillions(shown)}
                    </text>
                    <text className="wf-label" x={x + BAR / 2} y={440} textAnchor="middle">
                      {s.label}
                    </text>
                  </g>
                );
              })}
              <line className="wf-axis" x1="30" x2={W - 20} y1={y(0)} y2={y(0)} />
            </svg>
          )}
          <p className="value-caption mono">
            M € per year · {b.valued} initiatives
            {b.valued < b.total && ` (${b.total - b.valued} without estimated potential or cost left out)`} ·
            estimate (heuristic v2)
          </p>
        </div>

        <aside className="value-side">
          <div className="card value-fact">
            <span className="kpi-label">Confidence haircut</span>
            <span className="mono kpi-value value-potential-text">
              {haircutShare === null ? "–" : `−${Math.round(haircutShare * 100)} %`}
            </span>
            <span className="kpi-note">
              {b.lowestConfidence
                ? `${b.lowestConfidence.count} of ${b.valued} initiatives are at the lowest confidence (${b.lowestConfidence.value.toFixed(2)}). Firmer assumptions lift the potential most here.`
                : "No confidence estimated."}
            </span>
          </div>
          <div className="card value-fact">
            <span className="kpi-label">Net positive</span>
            <span className="mono kpi-value value-potential-text">
              {b.positive.count} / {b.valued}
            </span>
            <span className="kpi-note">
              Together they bring {formatSignedEur(b.positive.net)}/yr; the other {b.negative.count} cost{" "}
              {formatEur(Math.abs(b.negative.net))}/yr net.
            </span>
          </div>
        </aside>
      </div>

      <div className="bucket-tiles" aria-label="Potential per value bucket">
        {b.buckets.map((x) => (
          <div key={x.label} className="card bucket-tile">
            <span className="kpi-label">{x.label}</span>
            <span className="mono bucket-value">{formatEur(x.potential)}</span>
            <span className="bucket-track" aria-hidden="true">
              <span style={{ width: `${(x.potential / largestBucket) * 100}%` }} />
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
