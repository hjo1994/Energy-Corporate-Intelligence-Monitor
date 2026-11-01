import type { Stagegate } from "../api/types";
import { gateState, type GateDates } from "../domain/lifecycle";

/** The maturity order of the stages; On hold, Cancelled and Unknown stand outside it. */
export const STAGE_ORDER = ["Idea", "Exploration", "PoC", "MVP", "Implementation", "Production", "Retired"];
export const SIDE_STAGES = ["On hold", "Cancelled"];

/** The gate that lies right before a stage in the order. */
const GATE_BEFORE: Record<string, Stagegate> = { Idea: "Needs", PoC: "Scope", Production: "Deploy", Retired: "Retire" };

export const belowFloor = (stage: string, floor: string | null | undefined, order: string[] = STAGE_ORDER) =>
  !!floor && order.includes(stage) && order.includes(floor) && order.indexOf(stage) < order.indexOf(floor);

/**
 * The stages in their order with the stage gates between them, to pick the stage. Stages below the
 * one given in form 1 cannot be chosen; On hold and Cancelled stand aside and can be chosen any time.
 */
export function StageTrack({
  stage,
  saved,
  floor,
  dates,
  onChange,
  disabled = false,
  order = STAGE_ORDER,
}: {
  stage: string;
  /** the saved stage, to mark what changes */
  saved: string | null | undefined;
  floor: string | null | undefined;
  dates: GateDates;
  onChange: (stage: string) => void;
  disabled?: boolean;
  order?: string[];
}) {
  const current = order.indexOf(stage);
  const sides = [...SIDE_STAGES, ...(stage === "Unknown" || saved === "Unknown" ? ["Unknown"] : [])];

  const option = (s: string, i: number | null) => {
    const below = belowFloor(s, floor, order);
    const state = s === stage ? "current" : i !== null && current >= 0 && i < current ? "done" : "later";
    return (
      <label
        key={s}
        className={`lc-stage-opt lc-stage-${state}${below ? " lc-stage-below" : ""}${s === saved && s !== stage ? " lc-stage-saved" : ""}`}
        title={below ? `Below ${floor}, the stage given when the idea was submitted` : undefined}
      >
        <input type="radio" name="stage" value={s} checked={s === stage} disabled={disabled || below} onChange={() => onChange(s)} />
        <span className="lc-stage-name">{s}</span>
        {s === saved && s !== stage && <span className="lc-stage-note">saved</span>}
        {below && <span className="lc-stage-note">before form 1</span>}
      </label>
    );
  };

  return (
    <div className="lc-track-wrap">
      <div className="lc-track" role="radiogroup" aria-label="Stage / maturity">
        {order.map((s, i) => {
          const gate = GATE_BEFORE[s];
          return (
            <span key={s} className="lc-track-step">
              {gate && (
                <span className={`lc-track-gate lc-track-gate-${gateState(dates[gate])}`} title={`${gate} gate`}>
                  <span className="lc-track-diamond" aria-hidden="true" />
                  <span className="lc-track-gate-name">{gate}</span>
                </span>
              )}
              {i > 0 && !gate && <span className="lc-track-arrow" aria-hidden="true">›</span>}
              {option(s, i)}
            </span>
          );
        })}
      </div>
      <div className="lc-track-side" role="radiogroup" aria-label="Paused or stopped">
        <span className="muted">Paused or stopped:</span>
        {sides.map((s) => option(s, null))}
      </div>
    </div>
  );
}
