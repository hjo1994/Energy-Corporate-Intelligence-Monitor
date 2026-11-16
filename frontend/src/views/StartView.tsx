import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { departmentCount } from "../domain/departments";
import { pathStats, percent, type PathStats } from "../domain/path";
import { stageColor } from "../domain/stage";
import { useFormDrawer } from "../nav/formDrawer";
import { useApp } from "../store";

interface Figure {
  value: string;
  label: string;
}

type Stop =
  | { kind: "form"; mark: string; title: string; text: string }
  | { kind: "gate"; title: string; text: string }
  | { kind: "stage"; title: string; text: string; figures: Figure[] };

// Planned durations come from the gate dates in the plans (11/2026); they are not measured yet.
function stops(s: PathStats): Stop[] {
  const moveOn = (k: number, label = "move on"): Figure => ({ value: percent(s.moveOn[k]), label });
  const notMeasured: Figure = { value: "not measured", label: "duration" };
  return [
    { kind: "form", mark: "F1", title: "Form 1", text: "Describe the need in a few sentences. About 10 minutes." },
    { kind: "gate", title: "Needs gate", text: "Is the need real and worth exploring? Leads are assigned here." },
    {
      kind: "stage", title: "Ideation", text: "Sharpen the idea, find data and estimate the value.",
      figures: [{ value: "≈ 3 months", label: "planned · median of 27 plans" }, moveOn(0)],
    },
    { kind: "form", mark: "F2", title: "Form 2", text: "Scope, data, value estimate and risk answers." },
    { kind: "gate", title: "Scope gate", text: "Approved for a proof of concept." },
    {
      kind: "stage", title: "PoC", text: "Show that it works on real data.",
      figures: [{ value: "≈ 6 months", label: "planned · only 3 plans" }, moveOn(1)],
    },
    { kind: "stage", title: "MVP", text: "A first version real users can try.", figures: [notMeasured, moveOn(2)] },
    { kind: "stage", title: "Implementation", text: "Build it into the tools people use.", figures: [notMeasured, moveOn(3, "go live")] },
    { kind: "gate", title: "Deploy gate", text: "Cleared to go live." },
    {
      kind: "stage", title: "Production", text: "Live and creating value.",
      figures: [{ value: String(s.live), label: "live" }, { value: percent(s.liveShare), label: "of all" }],
    },
  ];
}

function Marker({ stop }: { stop: Stop }) {
  if (stop.kind === "form") return <span className="st-mark st-mark-form">{stop.mark}</span>;
  if (stop.kind === "gate") return <span className="st-mark st-mark-gate" />;
  return <span className="st-mark st-mark-stage" style={{ background: stageColor(stop.title) }} />;
}

/** Innovator start page: the path of an idea, then two ways on (explore, submit). */
export function StartView() {
  const { all } = useApp();
  const navigate = useNavigate();
  const form = useFormDrawer();
  const stats = useMemo(() => pathStats(all), [all]);
  const departments = useMemo(() => departmentCount(all), [all]);

  return (
    <div className="st view-enter">
      <section className="st-hero" aria-labelledby="st-title">
        <span className="st-kicker">Start · how an idea becomes a solution</span>
        <h1 id="st-title">Every AI use case here started as a few sentences.</h1>
        <p>Follow the path below to see what happens after you submit, how long each step usually takes and how many ideas move on.</p>
      </section>

      <section className="card st-path-card" aria-label="The path of an idea">
        <ol className="st-path">
          {stops(stats).map((s) => (
            <li key={s.title} className={`st-stop st-stop-${s.kind}`}>
              <Marker stop={s} />
              <div className="st-text">
                <h3>
                  {s.title}
                  {s.kind === "gate" && <span className="sr-only"> (decision)</span>}
                </h3>
                <p>{s.text}</p>
              </div>
              {s.kind === "stage" && (
                <dl className="st-figures">
                  {s.figures.map((f) => (
                    <div key={f.label}>
                      <dt className="st-fig-label">{f.label}</dt>
                      <dd className="mono st-fig-value">{f.value}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </li>
          ))}
        </ol>
        <p className="st-note">
          Times are planned, not measured. Shares are counted from the {stats.total} use cases in the cockpit: of those that reached a
          stage, how many are at the next one or beyond.
        </p>
      </section>

      <section className="st-next" aria-labelledby="st-next">
        <h2 id="st-next">Where do you go from here?</h2>
        <div className="st-doors">
          <article className="card st-door">
            <h3>See what others are building</h3>
            <p>
              {all.length} use cases from {departments} departments. Maybe someone already works on your problem.
            </p>
            <button type="button" className="st-door-btn" onClick={() => navigate("/innovate/explore")}>
              Explore the map →
            </button>
          </article>
          <article className="st-door st-door-primary">
            <h3>Submit your idea</h3>
            <p>Form 1 takes about 10 minutes. You can save a draft.</p>
            <button type="button" className="st-door-btn" disabled={!form.enabled} onClick={form.open}>
              Start Form 1 →
            </button>
            {!form.enabled && <span className="st-door-off">The form is switched off at the moment.</span>}
          </article>
        </div>
      </section>
    </div>
  );
}
