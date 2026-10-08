import type { Initiative } from "../api/types";
import { flagshipLabel, formatQuarter } from "../domain/format";
import { Avatar, EffortMeter, StatusBadge, ValueMeter } from "./small";

export function DetailBody({ initiative: i }: { initiative: Initiative }) {
  return (
    <div className="detail">
      <div className="detail-head">
        <StatusBadge status={i.status} />
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
          <span className="label">Value</span>
          <ValueMeter score={i.value_score} />
        </div>
      </div>

      <dl className="facts">
        <dt>Flagship</dt>
        <dd>{i.value_type ? flagshipLabel(i.value_type.name) : <span className="missing">not assigned</span>}</dd>
        <dt>Solution Type</dt>
        <dd>
          {i.solution_type?.name ?? (
            <span className="missing">not assigned (free text in the source)</span>
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
