import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { flushSync } from "react-dom";
import { useNavigate } from "react-router-dom";
import { atlasItems } from "../domain/atlas";
import { pathStats, percent, type PathStats } from "../domain/path";
import { useForm1 } from "../nav/form1";
import { useApp } from "../store";
import { useFullBleed } from "./fullBleed";
import "./journey.css";

// "From Idea to Production" as agreed in 11/2026: a scroll journey along an abstract path, ported from the reference page.

type WithColor = CSSProperties & { "--c"?: string };
type Kind = "doc" | "gate" | "stage";

interface Step {
  kind: Kind;
  side: "l" | "r";
  /** colour variable */
  c: string;
  name: string;
  kicker: string;
  title: string;
  text: string;
  /** text in the marker (forms and stages) */
  mark?: string;
}

const STEPS: Step[] = [
  { kind: "doc", side: "l", c: "--doc", name: "Form 1", mark: "F1", kicker: "Deliverable · Form 1", title: "Describe your idea",
    text: "The problem, a rough value estimate and six questions on people and data. Ranges are fine." },
  { kind: "gate", side: "r", c: "--gate", name: "Needs gate", kicker: "Gate 1 · Needs gate", title: "An approver confirms the need",
    text: "Approved with a named lead, or sent back with a comment." },
  { kind: "stage", side: "l", c: "--s-ideation", name: "Ideation", mark: "IDEA", kicker: "Stage 1 · Ideation", title: "Shape the use case",
    text: "You and the lead work out what will be built, for whom and how success is measured." },
  { kind: "doc", side: "r", c: "--doc", name: "Form 2", mark: "F2", kicker: "Deliverable · Form 2", title: "Add the details",
    text: "Solution type, KPIs, target users and compliance classes, filled in step by step during ideation." },
  { kind: "gate", side: "l", c: "--gate", name: "Scope gate", kicker: "Gate 2 · Scope gate", title: "Scope agreed",
    text: "Required before a proof of concept can start." },
  { kind: "stage", side: "r", c: "--s-poc", name: "PoC", mark: "PoC", kicker: "Stage 2 · PoC", title: "Prove it works",
    text: "A small build on real data answers one question: does the AI do the job well enough?" },
  { kind: "stage", side: "l", c: "--s-mvp", name: "MVP", mark: "MVP", kicker: "Stage 3 · MVP", title: "First real users",
    text: "A minimal product with a few colleagues, whose feedback shapes the full build." },
  { kind: "stage", side: "r", c: "--s-impl", name: "Implementation", mark: "IMPL", kicker: "Stage 4 · Implementation", title: "Build it to last",
    text: "Integration into the tools people use, plus security, operations and training." },
  { kind: "gate", side: "l", c: "--gate", name: "Deploy gate", kicker: "Gate 3 · Deploy gate", title: "Cleared to go live",
    text: "Required before production." },
  { kind: "stage", side: "r", c: "--s-prod", name: "Production", mark: "LIVE", kicker: "Stage 5 · Production", title: "Live and creating value",
    text: "From the delivery date on, the cockpit counts the value your solution realizes." },
  { kind: "gate", side: "l", c: "--gate", name: "Retire gate", kicker: "Gate 4 · Retire gate", title: "A planned end",
    text: "When a solution is replaced or no longer needed." },
  { kind: "stage", side: "r", c: "--s-ret", name: "Retired", mark: "RET", kicker: "Stage 6 · Retired", title: "Switched off",
    text: "The use case stays in the cockpit, so its lessons and value remain visible." },
];

const NOTE: Record<string, string> = {
  "Form 1": "Your first deliverable. The cockpit sizes value and risk as soon as you save.",
  "Needs gate": "An approver decides and names a lead.",
  "Form 2": "Your second deliverable, completed during ideation.",
  "Scope gate": "Passed before a proof of concept starts.",
  "Deploy gate": "Passed before production.",
  "Retire gate": "Passed at the planned end.",
};

/** value, unit, label, note */
type Fact = [string, string, string, string];

// Times are planned (median of the gate dates in the plans, 11/2026), not measured; the shares come from the data.
function numbers(s: PathStats, retired: number): Record<string, Fact[]> {
  const of = (k: number) => `${s.reached[k + 1]} of ${s.reached[k]}`;
  return {
    Ideation: [["≈ 3", "months", "typical time in this stage", "planned, median of 27 plans"], [percent(s.moveOn[0]), "", "moved on to PoC or later", of(0)]],
    PoC: [["≈ 6", "months", "typical time in this stage", "planned, only 3 plans so far"], [percent(s.moveOn[1]), "", "moved on to MVP or later", of(1)]],
    MVP: [["–", "", "typical time in this stage", "not measured yet"], [percent(s.moveOn[2]), "", "moved on to implementation or later", of(2)]],
    Implementation: [["–", "", "typical time in this stage", "not measured yet"], [percent(s.moveOn[3]), "", "went live in production", of(3)]],
    Production: [[String(s.live), "", "solutions live today", `${percent(s.liveShare)} of all use cases`]],
    Retired: [[String(retired), "", "retired so far", retired ? `${retired} of ${s.total} use cases` : "no solution has reached its planned end yet"]],
  };
}

function FactBox({ f: [v, u, l, n], pop }: { f: Fact; pop?: boolean }) {
  return (
    <div className={pop ? "fact pop" : "fact"}>
      <span className="v">
        {v}
        {u && (
          <>
            {" "}
            <small>{u}</small>
          </>
        )}
      </span>
      <span className="l">{l}</span>
      {n && <span className="n">{n}</span>}
    </div>
  );
}

const NS = "http://www.w3.org/2000/svg";
function mk(tag: string, attrs: Record<string, string | number>): SVGElement {
  const e = document.createElementNS(NS, tag) as SVGElement;
  for (const k in attrs) e.setAttribute(k, String(attrs[k]));
  return e;
}

/** Draws the path and moves the dot with the scroll; returns the cleanup. */
function drawRoad(road: HTMLElement, svg: SVGSVGElement, root: HTMLElement, onStop: (i: number) => void): () => void {
  const steps = [...road.querySelectorAll<HTMLElement>(".step")];
  let full: SVGPathElement | null = null;
  let segs: { p: SVGPathElement; from: number; len: number }[] = [];
  let car: SVGElement | null = null;
  let pts: number[][] = [];
  let total = 0;
  const css = (v: string) => getComputedStyle(root).getPropertyValue(v).trim();

  function build() {
    const box = road.getBoundingClientRect();
    svg.setAttribute("viewBox", `0 0 ${box.width} ${box.height}`);
    svg.replaceChildren();
    full = null;
    pts = steps.map((el) => {
      const r = el.querySelector(".mk")!.getBoundingClientRect();
      return [r.left + r.width / 2 - box.left, r.top + r.height / 2 - box.top];
    });
    const start = [pts[0][0] + (pts[1][0] - pts[0][0]) * 0.5, 0];
    const end = [pts[pts.length - 1][0] + (pts[pts.length - 2][0] - pts[pts.length - 1][0]) * 0.5, box.height];
    const all = [start, ...pts, end];
    const curve = (a: number[], b: number[]) => {
      const dy = (b[1] - a[1]) * 0.55;
      return `C ${a[0]} ${a[1] + dy} ${b[0]} ${b[1] - dy} ${b[0]} ${b[1]}`;
    };
    let d = `M ${all[0][0]} ${all[0][1]}`;
    for (let i = 1; i < all.length; i++) d += " " + curve(all[i - 1], all[i]);
    const narrow = box.width < 640;
    const defs = mk("defs", {});
    const blur = mk("filter", { id: "jr-soft", x: "-50%", y: "-50%", width: "200%", height: "200%" });
    blur.append(mk("feGaussianBlur", { stdDeviation: narrow ? 18 : 40 }));
    defs.append(blur);
    svg.append(defs);
    steps.forEach((el, i) => {
      if (!el.querySelector(".mk.stage")) return;
      svg.append(mk("circle", { cx: pts[i][0], cy: pts[i][1], r: narrow ? 46 : 120, fill: css(el.dataset.c!), opacity: ".16", filter: "url(#jr-soft)" }));
    });
    svg.append(mk("path", { d, fill: "none", stroke: css("--border"), "stroke-width": narrow ? 10 : 18, "stroke-linecap": "round", opacity: ".45" }));
    svg.append(mk("path", { d, fill: "none", stroke: css("--ink-soft"), "stroke-width": 1.5, opacity: ".5" }));
    const path = mk("path", { d, fill: "none", stroke: "none" }) as SVGPathElement;
    svg.append(path);
    if (typeof path.getTotalLength !== "function") return; // no layout (tests)
    full = path;
    total = path.getTotalLength();
    // each lane takes the colour of the stage it belongs to (gates and forms inherit the stage before them)
    let stageColor = css("--s-ideation");
    const laneColor = steps.map((el) => {
      if (el.querySelector(".mk.stage")) stageColor = css(el.dataset.c!);
      return stageColor;
    });
    segs = [];
    let acc = 0;
    for (let i = 1; i < all.length; i++) {
      const sd = `M ${all[i - 1][0]} ${all[i - 1][1]} ${curve(all[i - 1], all[i])}`;
      const color = laneColor[Math.min(i - 1, steps.length - 1)];
      const p = mk("path", { d: sd, fill: "none", stroke: color, "stroke-width": narrow ? 3 : 4, "stroke-linecap": "round" }) as SVGPathElement;
      svg.append(p);
      const len = p.getTotalLength();
      p.style.strokeDasharray = `${len} ${len + 1}`;
      p.style.strokeDashoffset = String(len);
      segs.push({ p, from: acc, len });
      acc += len;
    }
    car = mk("g", {});
    car.append(mk("circle", { r: narrow ? 14 : 22, fill: css("--accent"), opacity: ".18" }));
    car.append(mk("circle", { r: narrow ? 5 : 7, fill: css("--accent") }));
    svg.append(car);
    update();
  }
  function lengthAtY(y: number) {
    let lo = 0;
    let hi = total;
    for (let k = 0; k < 24; k++) {
      const mid = (lo + hi) / 2;
      if (full!.getPointAtLength(mid).y < y) lo = mid;
      else hi = mid;
    }
    return lo;
  }
  let ticking = false;
  function update() {
    ticking = false;
    if (!full || !car) return;
    const box = road.getBoundingClientRect();
    const y = Math.max(0, Math.min(box.height, innerHeight * 0.5 - box.top));
    const len = lengthAtY(y);
    const pt = full.getPointAtLength(len);
    car.setAttribute("transform", `translate(${pt.x} ${pt.y})`);
    segs.forEach((s) => {
      const done = Math.max(0, Math.min(s.len, len - s.from));
      s.p.style.strokeDashoffset = String(s.len - done);
    });
    let i = 0;
    pts.forEach((p, j) => {
      if (p[1] <= y + 40) i = j;
    });
    onStop(i);
  }
  const onScroll = () => {
    if (!ticking) {
      ticking = true;
      requestAnimationFrame(update);
    }
  };
  let rt: ReturnType<typeof setTimeout> | undefined;
  const onResize = () => {
    clearTimeout(rt);
    rt = setTimeout(build, 120);
  };
  let alive = true;
  addEventListener("scroll", onScroll, { passive: true });
  addEventListener("resize", onResize);
  (document.fonts?.ready ?? Promise.resolve()).then(() => alive && build());
  build();
  return () => {
    alive = false;
    clearTimeout(rt);
    removeEventListener("scroll", onScroll);
    removeEventListener("resize", onResize);
  };
}

const reducedMotion = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Innovator start page: the path from an idea to production, then two ways on (explore, submit). */
export function StartView() {
  const { all } = useApp();
  const navigate = useNavigate();
  const form = useForm1();
  const stats = useMemo(() => pathStats(all), [all]);
  const items = useMemo(() => atlasItems(all), [all]);
  const departments = useMemo(() => new Set(items.map((i) => i.dv).filter((d) => d !== "unassigned")).size, [items]);
  const retired = useMemo(() => all.filter((i) => i.stage === "Retired").length, [all]);
  const nums = numbers(stats, retired);
  const [current, setCurrent] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const roadRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  useFullBleed();

  useEffect(() => drawRoad(roadRef.current!, svgRef.current!, rootRef.current!, setCurrent), []);

  const explore = () => {
    const go = () => {
      flushSync(() => navigate("/innovate/explore"));
      window.scrollTo(0, 0);
    };
    const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
    if (doc.startViewTransition && !reducedMotion()) doc.startViewTransition(go);
    else go();
  };

  const step = STEPS[current];
  const today = new Date().toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

  return (
    <div className="jr" ref={rootRef}>
      <header className="hero">
        <div className="wrap">
          <p className="eyebrow">AI Cockpit · for innovators</p>
          <h1>The path from an idea to AI in production</h1>
          <p className="lead">
            Every use case follows the same path: two forms, four gates and six maturity stages. Scroll down and follow one idea along it.
          </p>
          <div className="route" aria-label="Forms, gates and stages in order">
            <span className="d">Form 1</span>
            <span className="g" title="Needs gate" />
            <span className="s" style={{ "--c": "var(--s-ideation)" } as WithColor}>Ideation</span>
            <span className="d">Form 2</span>
            <span className="g" title="Scope gate" />
            <span className="s" style={{ "--c": "var(--s-poc)" } as WithColor}>PoC</span>
            <span className="s" style={{ "--c": "var(--s-mvp)" } as WithColor}>MVP</span>
            <span className="s" style={{ "--c": "var(--s-impl)" } as WithColor}>Implementation</span>
            <span className="g" title="Deploy gate" />
            <span className="s" style={{ "--c": "var(--s-prod)" } as WithColor}>Production</span>
            <span className="g" title="Retire gate" />
            <span className="s" style={{ "--c": "var(--s-ret)" } as WithColor}>Retired</span>
          </div>
        </div>
      </header>

      <div className="wrap story">
        <div className="road" ref={roadRef}>
          <svg ref={svgRef} aria-hidden="true" />
          {STEPS.map((s, i) => (
            <section
              key={s.name}
              aria-label={s.name}
              className={["step", s.side, s.kind !== "stage" && s.kind, i === current && "is-active", i <= current && "passed"].filter(Boolean).join(" ")}
              data-c={s.c}
              style={{ "--c": `var(${s.c})` } as WithColor}
            >
              <div className="jr-card">
                <span className="eyebrow kicker">{s.kicker}</span>
                <h2>{s.title}</h2>
                <p>{s.text}</p>
                {nums[s.name] && (
                  <div className="facts-inline">
                    {nums[s.name].map((f) => (
                      <FactBox key={f[2]} f={f} />
                    ))}
                  </div>
                )}
              </div>
              <div className={`mk ${s.kind}`}>
                {s.kind === "gate" ? <span className="dia" /> : s.mark}
                {s.kind !== "stage" && <span className="sign">{s.name}</span>}
              </div>
            </section>
          ))}
        </div>

        <aside className="panel" aria-live="polite">
          <div className="odo" style={{ "--c": `var(${step.c})` } as WithColor}>
            <span className="where">{step.kicker}</span>
            <div className="meter">
              <div style={{ width: `${((current + 1) / STEPS.length) * 100}%` }} />
            </div>
            <div className="km">
              <span>Idea</span>
              <span>
                Stop {current + 1} of {STEPS.length}
              </span>
              <span>Retired</span>
            </div>
          </div>
          <div className="pcard" key={current} style={{ "--c": `var(${step.c})` } as WithColor}>
            {nums[step.name] ? nums[step.name].map((f) => <FactBox key={f[2]} f={f} pop />) : <p className="pnote pop">{NOTE[step.name]}</p>}
          </div>
        </aside>
      </div>

      <section className="cta" aria-labelledby="jr-next">
        <div className="wrap">
          <p className="eyebrow">Your turn</p>
          <h2 id="jr-next">Where do you go from here?</h2>
          <p>
            {stats.live} ideas already run in production. Yours could be next.
          </p>
          <div className="doors">
            <article className="door">
              <h3>See what others are building</h3>
              <p>
                {items.length} use cases from {departments} departments. Maybe someone already works on your problem.
              </p>
              <button type="button" className="btn ghost" onClick={explore}>
                Explore the map →
              </button>
            </article>
            <article className="door primary">
              <h3>Submit your idea</h3>
              <p>Form 1 takes about 10 minutes.</p>
              <button type="button" className="btn" disabled={!form.enabled} onClick={form.open}>
                Start Form 1 →
              </button>
              {!form.enabled && <span className="off">The form is switched off at the moment.</span>}
            </article>
          </div>
        </div>
      </section>
      <section className="method">
        <div className="wrap">
          <p>
            How the numbers are worked out: “moved on” counts, among the {stats.reached[0]} use cases with a known stage on {today}, those now in
            a later stage out of all that reached this stage. Use cases can enter at any stage, so this is a snapshot, not a tracked cohort.
            Typical time is the median planned time from start to delivery where a plan exists; measured times will replace it as stage changes
            are recorded.
          </p>
        </div>
      </section>
    </div>
  );
}
