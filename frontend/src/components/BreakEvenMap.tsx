import { useState } from "react";
import type { Initiative } from "../api/types";
import { businessUnitOf, NO_BUSINESS_UNIT, NO_BUSINESS_UNIT_LABEL } from "../domain/filters";
import { formatEur } from "../domain/format";
import {
  breakEvenPoints,
  breakEvenStats,
  formatSignedEur,
  niceMax,
  STAGE_GROUPS,
  type StageGroup,
} from "../domain/value";
import { DetailDialog } from "./DetailDialog";
import { Chip } from "./small";

const groupColor = (g: StageGroup) => `var(--group-${g})`;

/** B · One dot per initiative: annual cost against potential, with the break-even diagonal. */
export function BreakEvenMap({ items }: { items: Initiative[] }) {
  const [group, setGroup] = useState<StageGroup | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [open, setOpen] = useState<Initiative | null>(null);

  const points = breakEvenPoints(items);
  const inGroup = (g: StageGroup) => group === null || group === g;
  const stats = breakEvenStats(points.filter((p) => inGroup(p.group)));

  const xMax = niceMax(Math.max(0, ...points.map((p) => p.cost)));
  const yMax = niceMax(Math.max(0, ...points.map((p) => p.potential)));
  const xPct = (eur: number) => (eur / xMax) * 100;
  const yPct = (eur: number) => 100 - (eur / yMax) * 100;
  // Break-even diagonal (potential = cost) from the origin to where it leaves the plot.
  const m = Math.min(xMax, yMax);
  const above = [`0,100`, `${xPct(m)},${yPct(m)}`, ...(m === xMax ? [`100,0`] : []), `0,0`].join(" ");
  const xTicks = Array.from({ length: xMax / 100_000 + 1 }, (_, k) => k * 100_000);
  const yTicks = Array.from({ length: yMax / 100_000 + 1 }, (_, k) => k * 100_000);
  const tip = points.find((p) => p.initiative.id === hovered);

  return (
    <section className="value-section" aria-label="Break-even map">
      <div className="value-head value-head-row">
        <div>
          <h2>Break-even map</h2>
          <p className="muted">
            Each dot is one initiative. Above the dashed line its estimated potential exceeds its cost per year.
            Click a dot for the details.
          </p>
        </div>
        <div className="value-kpis">
          <div>
            <span className="kpi-label">Above break-even</span>
            <span className="mono kpi-value value-potential-text">
              {stats.above} / {stats.total}
            </span>
          </div>
          <div>
            <span className="kpi-label">Net per year</span>
            <span className="mono kpi-value value-cost-text">{formatSignedEur(stats.net)}</span>
          </div>
        </div>
      </div>

      <div className="chip-group" role="group" aria-label="Stage group">
        <Chip active={group === null} onClick={() => setGroup(null)}>
          All
        </Chip>
        {STAGE_GROUPS.map((g) => (
          <Chip key={g.id} dot={groupColor(g.id)} active={group === g.id} onClick={() => setGroup(g.id)}>
            {g.label}
          </Chip>
        ))}
      </div>

      <div className="card value-chart">
        {points.length === 0 ? (
          <p className="empty">No initiative with estimated potential and cost matches the filters.</p>
        ) : (
          <div className="plot-wrap be-wrap">
            <span className="axis-y">Potential (k €/yr)</span>
            <div className="plot-col">
              <div className="be-plot" data-testid="break-even-plot">
                <svg className="be-grid" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                  <polygon className="be-above" points={above} />
                  {xTicks.slice(1, -1).map((t) => (
                    <line key={`x${t}`} x1={xPct(t)} x2={xPct(t)} y1="0" y2="100" vectorEffect="non-scaling-stroke" />
                  ))}
                  {yTicks.slice(1, -1).map((t) => (
                    <line key={`y${t}`} x1="0" x2="100" y1={yPct(t)} y2={yPct(t)} vectorEffect="non-scaling-stroke" />
                  ))}
                  <line className="be-diagonal" x1="0" y1="100" x2={xPct(m)} y2={yPct(m)} vectorEffect="non-scaling-stroke" />
                </svg>
                {yTicks.slice(1).map((t) => (
                  <span key={t} className="be-tick be-tick-y mono" style={{ top: `${yPct(t)}%` }}>
                    {t / 1000}
                  </span>
                ))}
                <span className="be-zone be-zone-above">Pays off</span>
                <span className="be-zone be-zone-below">Costs more than it brings</span>
                {points.map((p) => (
                  <button
                    key={p.initiative.id}
                    type="button"
                    className={`be-dot${inGroup(p.group) ? "" : " faded"}`}
                    aria-label={`${p.initiative.name}: potential ${formatEur(p.potential)}, cost ${formatEur(p.cost)} per year`}
                    style={{
                      left: `calc(${xPct(p.cost)}% + ${p.jitter}px)`,
                      top: `${yPct(p.potential)}%`,
                      background: groupColor(p.group),
                    }}
                    onMouseEnter={() => setHovered(p.initiative.id)}
                    onMouseLeave={() => setHovered(null)}
                    onFocus={() => setHovered(p.initiative.id)}
                    onBlur={() => setHovered(null)}
                    onClick={() => setOpen(p.initiative)}
                  />
                ))}
                {tip && (
                  <div
                    className={`be-tip${xPct(tip.cost) > 60 ? " be-tip-left" : ""}`}
                    role="tooltip"
                    style={{ left: `calc(${xPct(tip.cost)}% + ${tip.jitter}px)`, top: `${yPct(tip.potential)}%` }}
                  >
                    <strong>{tip.initiative.name}</strong>
                    <span className="muted">
                      {businessUnitOf(tip.initiative) === NO_BUSINESS_UNIT ? NO_BUSINESS_UNIT_LABEL : businessUnitOf(tip.initiative)} ·{" "}
                      {tip.initiative.stage}
                    </span>
                    <span>
                      Potential <span className="mono">{formatEur(tip.potential)}</span> · cost{" "}
                      <span className="mono">{formatEur(tip.cost)}</span> /yr
                    </span>
                  </div>
                )}
              </div>
              <div className="be-xticks mono" aria-hidden="true">
                {xTicks.map((t) => (
                  <span key={t} style={{ left: `${xPct(t)}%` }}>
                    {t / 1000}
                  </span>
                ))}
              </div>
              <div className="axis-x be-axis-x">
                <span>Cost per year (k €)</span>
              </div>
            </div>
          </div>
        )}
        <p className="value-caption mono">
          Estimate (heuristic v2). The cost heuristic works in steps, hence the columns; dots are nudged
          sideways so that they stay visible.
        </p>
      </div>
      {open && <DetailDialog initiative={open} onClose={() => setOpen(null)} />}
    </section>
  );
}
