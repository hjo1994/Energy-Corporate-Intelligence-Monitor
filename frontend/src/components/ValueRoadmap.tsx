import type { Initiative } from "../api/types";
import { NO_BUSINESS_UNIT, NO_BUSINESS_UNIT_LABEL } from "../domain/filters";
import { formatEur } from "../domain/format";
import { formatThousands, niceMax, valueRoadmap } from "../domain/value";

// Chart geometry in SVG units.
const W = 800;
const LEFT = 60;
const RIGHT = 780;
const TOP = 60;
const BASE = 380;

const millions = (eur: number) => `${+(eur / 1_000_000).toFixed(1)} M`;

/** G · Potential per delivery quarter (bars) and cumulated (line), next to what has no date yet. */
export function ValueRoadmap({ items }: { items: Initiative[] }) {
  const r = valueRoadmap(items);
  const n = r.quarters.length;
  const last = r.quarters[n - 1]?.cumulative ?? 0;
  const step = last > 2_000_000 ? 1_000_000 : 500_000;
  const yMax = niceMax(last, step);
  const y = (eur: number) => BASE - (eur / yMax) * (BASE - TOP);
  const slot = (RIGHT - LEFT) / Math.max(1, n);
  const bar = Math.min(90, slot * 0.6);
  const cx = (k: number) => LEFT + slot * (k + 0.5);
  const ticks = Array.from({ length: yMax / step + 1 }, (_, k) => k * step);
  const line = [`${LEFT},${BASE}`, ...r.quarters.map((q, k) => `${cx(k)},${y(q.cumulative)}`)].join(" ");
  const datedCount = r.quarters.reduce((a, q) => a + q.count, 0);
  const unitNames = r.undatedBusinessUnits.map((bu) => (bu === NO_BUSINESS_UNIT ? NO_BUSINESS_UNIT_LABEL : bu));

  return (
    <section className="value-section" aria-label="Value roadmap">
      <div className="value-head">
        <h2>Value roadmap</h2>
        <p className="muted">When does the value arrive? Estimated potential by planned delivery quarter.</p>
      </div>
      <div className="value-split">
        <div className="card value-chart">
          {n === 0 ? (
            <p className="empty">No initiative matching the filters has a delivery date.</p>
          ) : (
            <>
              <ul className="legend">
                <li>
                  <span className="legend-swatch roadmap-swatch-bar" />
                  Potential per quarter
                </li>
                <li>
                  <span className="legend-swatch roadmap-swatch-line" />
                  Cumulative
                </li>
              </ul>
              <svg
                viewBox={`0 0 ${W} 430`}
                width="100%"
                role="img"
                aria-label={`Potential per delivery quarter in k €: ${r.quarters
                  .map((q) => `${q.label} ${formatThousands(q.potential)}`)
                  .join(", ")}; cumulative ${formatEur(last)}`}
              >
                {ticks.slice(1).map((t) => (
                  <line key={t} className="rm-grid" x1={LEFT} x2={RIGHT} y1={y(t)} y2={y(t)} />
                ))}
                {ticks.map((t) => (
                  <text key={t} className="rm-tick" x={LEFT - 8} y={y(t) + 4} textAnchor="end">
                    {t === 0 ? "0" : millions(t)}
                  </text>
                ))}
                {r.quarters.map((q, k) => (
                  <g key={q.label}>
                    <rect className="rm-bar" x={cx(k) - bar / 2} y={y(q.potential)} width={bar} height={BASE - y(q.potential)} rx="2" />
                    <text className="rm-label" x={cx(k)} y={404} textAnchor="middle">
                      {q.label}
                    </text>
                    <text className="rm-count" x={cx(k)} y={424} textAnchor="middle">
                      {k === 0 ? `${q.count} initiative${q.count === 1 ? "" : "s"}` : q.count}
                    </text>
                  </g>
                ))}
                <line className="wf-axis" x1={LEFT} x2={RIGHT} y1={BASE} y2={BASE} />
                <polyline className="rm-line" points={line} />
                {r.quarters.map((q, k) => (
                  <circle key={q.label} className="rm-point" cx={cx(k)} cy={y(q.cumulative)} r="6" />
                ))}
                {/* After the line, with a halo: at the foot of tall bars (the cumulative line runs
                    above them), above short ones. */}
                {r.quarters.map((q, k) =>
                  q.count > 0 ? (
                    <text
                      key={q.label}
                      className={`rm-value${BASE - y(q.potential) > 30 ? "" : " rm-value-above"}`}
                      x={cx(k)}
                      y={BASE - y(q.potential) > 30 ? BASE - 10 : y(q.potential) - 8}
                      textAnchor="middle"
                    >
                      {formatThousands(q.potential)}
                    </text>
                  ) : null,
                )}
                <text className="rm-total" x={cx(n - 1)} y={y(last) - 16} textAnchor="middle">
                  {formatEur(last)}
                </text>
              </svg>
            </>
          )}
          <p className="value-caption mono">
            k € potential per year · {datedCount} initiatives with a delivery date · estimate (heuristic v2)
          </p>
        </div>

        <div className="undated" aria-label="Without delivery date" role="group">
          <span className="undated-title">No delivery date</span>
          <span className="mono undated-value">{formatEur(r.undated.potential)}</span>
          <span className="undated-note">
            {r.undatedShare === null ? "–" : `${Math.round(r.undatedShare * 100)} %`} of the potential ·{" "}
            {r.undated.count} initiatives
            {unitNames.length > 0 && ` · no dates yet from ${unitNames.join(", ")}`}
          </span>
        </div>
      </div>
    </section>
  );
}
