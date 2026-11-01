import type { Stagegate } from "../api/types";
import {
  GATES,
  STAGE_GATE_RULES,
  gateProblems,
  gateRequirement,
  gateState,
  shortDate,
  todayIso,
  tomorrowIso,
  type GateDates,
  type GateRules,
} from "../domain/lifecycle";

const STATE_LABEL = { passed: "Passed", planned: "Planned", open: "No date" } as const;

/**
 * The stage gates with one date each (a date input opens the browser's calendar).
 * - mode "new" (form 1): only the gates the chosen stage needs as passed, plus the needs gate
 *   (optional) once a later gate is asked for.
 * - mode "edit": all four gates. A gate saved as passed stays fixed unless the stage needs it
 *   back in the future; planned and missing dates can be changed.
 */
export function GateDatesEditor({
  stage,
  dates,
  onChange,
  saved,
  mode,
  disabled = false,
  rules = STAGE_GATE_RULES,
  showProblems = true,
  today = todayIso(),
}: {
  stage: string;
  dates: GateDates;
  onChange: (gate: Stagegate, date: string) => void;
  saved?: GateDates;
  mode: "new" | "edit";
  disabled?: boolean;
  rules?: GateRules;
  showProblems?: boolean;
  today?: string;
}) {
  const problems = gateProblems(stage, dates, today, rules);
  const mustPass = GATES.filter((g) => gateRequirement(stage, g, rules) === "passed");
  const shown = mode === "edit" ? GATES : mustPass.length > 0 ? GATES.filter((g) => g === "Needs" || mustPass.includes(g)) : [];
  if (shown.length === 0) return null;
  const tomorrow = tomorrowIso(new Date(`${today}T12:00:00`));

  return (
    <div className="lc-gates" role="group" aria-label="Stage gates">
      {mode === "new" && (
        <p className="nf-hint lc-gates-intro">
          In {stage} the {mustPass.map((g) => g.toLowerCase()).join(" and ")} gate{mustPass.length > 1 ? "s are" : " is"} already
          passed. When was that?
        </p>
      )}
      <ol className="lc-gate-list">
        {shown.map((gate) => {
          const need = gateRequirement(stage, gate, rules);
          const date = dates[gate];
          const state = gateState(date, today);
          const savedPassed = !!saved && gateState(saved[gate], today) === "passed";
          const locked = mode === "edit" && savedPassed && need !== "not_passed" && date === saved?.[gate];
          const problem = showProblems ? problems.find((p) => p.gate === gate) : undefined;
          const required = need === "passed";
          const hint =
            need === "passed" ? "must be passed: a date up to today"
            : need === "not_passed" ? "not passed yet: a planned date or none"
            : gate === "Needs" ? "passed when the idea is approved" : "optional";
          return (
            <li key={gate} className={`lc-gate lc-gate-${state}${problem ? " invalid" : ""}`}>
              <span className="lc-gate-dot" aria-hidden="true">{state === "passed" ? "✓" : GATES.indexOf(gate) + 1}</span>
              <label className="lc-gate-body">
                <span className="nf-label">
                  {gate} gate{required && <b aria-hidden="true"> *</b>}
                  {mode === "edit" && <span className={`lc-gate-state lc-gate-state-${state}`}>{STATE_LABEL[state]}</span>}
                </span>
                {locked ? (
                  <span className="lc-gate-fixed">
                    {shortDate(date)} <span className="muted">· passed, fixed</span>
                  </span>
                ) : (
                  <input
                    type="date"
                    className={`nf-input${problem ? " invalid" : ""}`}
                    aria-label={`${gate} gate date`}
                    aria-invalid={problem ? true : undefined}
                    value={date}
                    disabled={disabled}
                    max={need === "passed" ? today : undefined}
                    min={need === "not_passed" ? tomorrow : undefined}
                    onChange={(e) => onChange(gate, e.target.value)}
                  />
                )}
                {problem ? <span className="nf-error">{problem.message}</span> : !locked && <span className="nf-hint">{hint}</span>}
              </label>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
