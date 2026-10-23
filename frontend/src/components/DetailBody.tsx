import type { Initiative } from "../api/types";
import { flagshipLabel, formatEur, formatFactor, formatQuarter } from "../domain/format";
import { Avatar, EffortMeter, RiskBadge, StageBadge, ValueMeter } from "./small";

export function DetailBody({ initiative: i }: { initiative: Initiative }) {
  return (
    <div className="detail">
      <div className="detail-head">
        <StageBadge stage={i.stage} />
        <RiskBadge risk={i.risk_classification} />
      </div>
      <h3>{i.name}</h3>
      <p className="muted">{i.description ?? "No description recorded."}</p>

      <div className="owner-cell">
        {i.owner ? (
          <>
            <Avatar name={i.owner.name} size={32} />
            <span>
              <span className="owner-name">{i.owner.name}</span>
              <span className="owner-dept">
                {[i.owner.department, i.owner.category].filter(Boolean).join(" · ") || "–"}
              </span>
            </span>
          </>
        ) : (
          <span className="missing">No owner recorded in the source</span>
        )}
      </div>

      <div className="detail-scores">
        <div>
          <span className="label">Effort</span>
          <EffortMeter score={i.solution_complexity_score} />
        </div>
        <div>
          <span className="label">Potential per year</span>
          <ValueMeter eur={i.potential_value_eur} />
        </div>
      </div>

      <section aria-label="Value estimate">
        <h4 className="facts-title">Value estimate (heuristic, € per year)</h4>
        <dl className="facts">
          <dt>Efficiency</dt>
          <dd className="mono">{formatEur(i.efficiency_score_eur)}</dd>
          <dt>Quality</dt>
          <dd className="mono">{formatEur(i.quality_score_eur)}</dd>
          <dt>Risk reduction</dt>
          <dd className="mono">{formatEur(i.risk_reduction_score_eur)}</dd>
          <dt>Strategic value</dt>
          <dd className="mono">{formatEur(i.strategic_value_score_eur)}</dd>
          <dt>Hypothetical value</dt>
          <dd className="mono">{formatEur(i.hypothetical_value_eur)}</dd>
          <dt>Confidence</dt>
          <dd className="mono">{formatFactor(i.confidence_score)}</dd>
          <dt>Delivery</dt>
          <dd className="mono">{formatFactor(i.delivery_score)}</dd>
          <dt>Potential</dt>
          <dd className="mono">{formatEur(i.potential_value_eur)}</dd>
        </dl>
      </section>

      <section aria-label="Cost estimate">
        <h4 className="facts-title">Cost estimate (heuristic)</h4>
        <dl className="facts">
          <dt>One-time</dt>
          <dd className="mono">{formatEur(i.one_time_costs)}</dd>
          <dt>Operating per year</dt>
          <dd className="mono">{formatEur(i.operating_costs)}</dd>
          <dt>Depreciation</dt>
          <dd className="mono">{i.depreciation_years === null ? "–" : `${i.depreciation_years} years`}</dd>
          <dt>Cost per year</dt>
          <dd className="mono">{formatEur(i.annual_cost_eur)}</dd>
        </dl>
      </section>

      <dl className="facts">
        <dt>Flagship</dt>
        <dd>{i.value_type ? flagshipLabel(i.value_type.name) : <span className="missing">not assigned</span>}</dd>
        <dt>Solution Type</dt>
        <dd>
          {i.solution_type?.name ?? (
            <span className="missing">not assigned (free text in the source)</span>
          )}
        </dd>
        <dt>Risk level</dt>
        <dd>
          {i.risk_classification ? (
            `${i.risk_classification.id} – ${i.risk_classification.name} (estimated)`
          ) : (
            <span className="missing">not classified</span>
          )}
        </dd>
        <dt>Start (approx.)</dt>
        <dd>{formatQuarter(i.date_start)}</dd>
        <dt>Delivery (approx.)</dt>
        <dd>{formatQuarter(i.date_delivery)}</dd>
      </dl>
    </div>
  );
}
