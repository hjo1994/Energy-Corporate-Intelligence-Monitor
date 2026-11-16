import * as d3 from "d3";
import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import {
  atlasItems, DEPT, parseQ, prepare, queryMatch, SUGGESTIONS, TCOL, TOPIC, TSHORT, type AtlasItem,
} from "../domain/atlas";
import { useApp } from "../store";
import { useFullBleed } from "./fullBleed";
import "./atlas.css";

// "Use Case Atlas" as agreed in 11/2026 (topographic design), ported from the reference page: every hexagon is one
// use case, departments are territories, topics are clusters (d3 pack + hex spiral). Deliberately no stage or value.

const cv = (v: string) => `var(${v})`;
const ESC: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ESC[c]);
const snippet = (s: string) => (s ? esc(s.length > 140 ? s.slice(0, 137).replace(/\s+\S*$/, "") + "…" : s) : "");
const W = 900;
const H = 820;

interface Hover {
  t: string | null;
  k: string | null;
  dv: string | null;
  id: number | null;
}
const NO_HOVER: Hover = { t: null, k: null, dv: null, id: null };

interface Filters {
  q: string;
  topic: string | null;
  div: string | null;
  sel: number | null;
}

function spiral(n: number): [number, number][] {
  const out: [number, number][] = [[0, 0]];
  const dirs = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]];
  for (let k = 1; out.length < n; k++) {
    let q = -k;
    let r = k;
    for (let d = 0; d < 6 && out.length < n; d++)
      for (let j = 0; j < k && out.length < n; j++) {
        out.push([q, r]);
        q += dirs[d][0];
        r += dirs[d][1];
      }
  }
  return out;
}
function hexPath(s: number): string {
  const p: number[][] = [];
  for (let a = 0; a < 6; a++) {
    const t = (Math.PI / 180) * (60 * a - 30);
    p.push([s * Math.cos(t), s * Math.sin(t)]);
  }
  return "M" + p.map((q) => q.map((v) => v.toFixed(2)).join(",")).join("L") + "Z";
}

interface LeafData {
  t: string;
  dv: string;
  items: AtlasItem[];
  value: number;
}
interface Tree {
  dv?: string;
  children?: (Tree | LeafData)[];
}

/** What the d3 drawing exposes to the React part. */
interface AtlasMap {
  hexes: d3.Selection<SVGPathElement, AtlasItem, SVGGElement, unknown>;
  deptNodes: d3.HierarchyCircularNode<Tree>[];
  gBadge: d3.Selection<SVGGElement, unknown, null, undefined>;
  applyHover: (h: Hover) => void;
  focusOn: (x: number, y: number) => void;
  zoomBy: (k: number) => void;
  reset: () => void;
}

function drawMap(
  svgEl: SVGSVGElement, tip: HTMLDivElement, mapcard: HTMLDivElement, ITEMS: AtlasItem[], DEPT_ORDER: string[],
  actions: { select: (id: number) => void; toggleTopic: (t: string) => void; toggleDiv: (dv: string) => void; legendHover: (t: string | null) => void },
): AtlasMap {
  const svg = d3.select(svgEl);
  svg.selectAll("*").remove();
  const defs = svg.append("defs");
  const zoomG = svg.append("g");
  const gTerr = zoomG.append("g");
  const gHex = zoomG.append("g");
  zoomG.append("g"); // links
  const gLab = zoomG.append("g");
  const gBadge = zoomG.append("g");
  const tree: Tree = {
    children: DEPT_ORDER.map((dv) => {
      const tops = d3.rollups(ITEMS.filter((i) => i.dv === dv), (v) => v, (i) => i.t).sort((a, c) => c[1].length - a[1].length);
      return { dv, children: tops.map(([t, items]) => ({ t, dv, items, value: items.length })) };
    }),
  };
  const root = d3
    .hierarchy<Tree>(tree)
    .sum((d) => (d as LeafData).value || 0)
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  const packed = d3.pack<Tree>().size([W - 40, H - 40]).padding((d) => (d.depth === 0 ? 74 : 12))(root);
  packed.each((n) => {
    n.x += 20;
    n.y += 20;
  });
  const leaves = packed.leaves();
  const leafOf = (l: d3.HierarchyCircularNode<Tree>) => l.data as LeafData;
  const S = (d3.min(leaves, (l) => l.r * Math.sqrt(Math.PI / ((l.value ?? 1) * 2.598))) ?? 10) * 0.86;
  const HP = hexPath(S * 0.93);
  leaves.forEach((l) => {
    const its = leafOf(l).items.slice().sort((a, b) => a.n.localeCompare(b.n));
    spiral(its.length).forEach(([q, r], k) => {
      const it = its[k];
      it.x = l.x + S * Math.sqrt(3) * (q + r / 2);
      it.y = l.y + S * 1.5 * r;
    });
  });
  const deptNodes = packed.children ?? [];
  const m = 44;
  const x0 = (d3.min(deptNodes, (n) => n.x - n.r) ?? 0) - m;
  const x1 = (d3.max(deptNodes, (n) => n.x + n.r) ?? W) + m;
  const y0 = (d3.min(deptNodes, (n) => n.y - n.r) ?? 0) - m;
  const y1 = (d3.max(deptNodes, (n) => n.y + n.r) ?? H) + 16;
  const VB = [x0, y0, x1 - x0, y1 - y0];
  svg.attr("viewBox", VB.join(" "));
  svgEl.style.aspectRatio = `${VB[2]} / ${VB[3]}`;

  /* spotlight that follows the pointer */
  const spotDef = defs.append("radialGradient").attr("id", "ua-spot");
  spotDef.append("stop").attr("offset", "0%").attr("stop-color", "var(--accent)").attr("stop-opacity", 0.16);
  spotDef.append("stop").attr("offset", "100%").attr("stop-color", "var(--accent)").attr("stop-opacity", 0);
  const gSpot = zoomG.insert("g", () => gHex.node());
  deptNodes.forEach((n) => {
    [26, 16].forEach((o) =>
      gTerr.append("circle").attr("class", "contour").attr("cx", n.x).attr("cy", n.y).attr("r", n.r + 6 + o).attr("stroke-opacity", o > 20 ? 0.35 : 0.6),
    );
    gTerr.append("circle").attr("class", "terr").attr("data-dv", n.data.dv!).attr("cx", n.x).attr("cy", n.y).attr("r", n.r + 6);
    gLab.append("text").attr("class", "buname").attr("data-dv", n.data.dv!).attr("x", n.x).attr("y", n.y - n.r - 14)
      .attr("text-anchor", "middle").text(DEPT[n.data.dv!])
      .attr("paint-order", "stroke").attr("stroke", "var(--surface)").attr("stroke-width", 4);
  });
  const spot = gSpot.append("circle").attr("r", 150).attr("fill", "url(#ua-spot)").attr("opacity", 0).style("pointer-events", "none");
  const placed: number[][] = [];
  leaves.slice().sort((a, b) => (b.value ?? 0) - (a.value ?? 0)).forEach((l) => {
    const { t, dv } = leafOf(l);
    const key = dv + "|" + t;
    gTerr.append("circle").attr("class", "ring").attr("data-k", key).attr("data-t", t).attr("cx", l.x).attr("cy", l.y).attr("r", l.r + 3)
      .style("--tc", cv(TCOL[t]));
    if ((l.value ?? 0) < 2) return;
    const txt = TSHORT[t];
    const w = txt.length * 5.9 + 6;
    const y = l.y + l.r + 11;
    const box = [l.x - w / 2, y - 10, l.x + w / 2, y + 3];
    if (placed.some((b) => !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]))) return;
    placed.push(box);
    gLab.append("text").attr("class", "dlabel").attr("data-k", key).attr("data-t", t).attr("x", l.x).attr("y", y)
      .attr("text-anchor", "middle").text(txt)
      .attr("paint-order", "stroke").attr("stroke", "var(--surface)").attr("stroke-width", 3);
  });

  /* hexes: a group per hexagon so the hexagon itself can scale on hover */
  const hexG = gHex.selectAll<SVGGElement, AtlasItem>("g").data(ITEMS).join("g")
    .attr("transform", (d) => `translate(${d.x.toFixed(1)},${d.y.toFixed(1)})`);
  const hexes = hexG.append("path").attr("class", "hex").attr("d", HP)
    .attr("tabindex", 0).attr("role", "button").attr("aria-label", (d) => `${d.n}, ${DEPT[d.dv]}, ${TOPIC[d.t]}`);
  // entrance: clusters bloom outward from each centre
  hexes.style("animation-delay", (d) => `${Math.min(900, Math.hypot(d.x - VB[0] - VB[2] / 2, d.y - VB[1] - VB[3] / 2) * 1.6)}ms`).classed("enter", true);

  function showTip(e: PointerEvent, html: string) {
    const r = mapcard.getBoundingClientRect();
    tip.hidden = false;
    tip.innerHTML = html;
    const x = e.clientX - r.left + 16;
    const y = e.clientY - r.top + 16;
    tip.style.left = Math.max(8, Math.min(x, r.width - tip.offsetWidth - 8)) + "px";
    tip.style.top = Math.max(8, Math.min(y, r.height - tip.offsetHeight - 8)) + "px";
  }
  let hover: Hover = NO_HOVER;
  function applyHover(h: Hover) {
    hover = h;
    const on = hover.t || hover.dv;
    svg.classed("hovering", !!on);
    hexes.classed("echo", (d) => !!on && (hover.t ? d.t === hover.t : d.dv === hover.dv)).classed("pop", (d) => d.id === hover.id);
    gTerr.selectAll<SVGCircleElement, unknown>(".ring")
      .classed("lit", function () { return !!hover.t && this.dataset.t === hover.t; })
      .classed("home", function () { return !!hover.k && this.dataset.k === hover.k; });
    gLab.selectAll<SVGTextElement, unknown>(".dlabel").classed("lit", function () { return !!hover.t && this.dataset.t === hover.t; });
    gTerr.selectAll<SVGCircleElement, unknown>(".terr").classed("lit", function () { return !!hover.dv && this.dataset.dv === hover.dv; });
    gLab.selectAll<SVGTextElement, unknown>(".buname").classed("lit", function () { return !!hover.dv && this.dataset.dv === hover.dv; });
    actions.legendHover(hover.t);
  }
  const leave = () => {
    applyHover(NO_HOVER);
    tip.hidden = true;
  };
  const move = (e: PointerEvent) => {
    if (!tip.hidden) showTip(e, tip.innerHTML);
  };
  function ripple(key: string) {
    const list = hexes.filter((d) => d.dv + "|" + d.t === key).nodes();
    list.forEach((el, i) => {
      el.classList.remove("rip");
      void el.getBoundingClientRect();
      el.style.setProperty("--rd", i * 35 + "ms");
      el.classList.add("rip");
    });
  }
  hexG
    .on("pointerenter", function (e: PointerEvent, d) {
      d3.select(this).raise();
      const same = ITEMS.filter((o) => o.t === d.t);
      applyHover({ t: d.t, k: d.dv + "|" + d.t, dv: null, id: d.id });
      showTip(e, `<b>${esc(d.n)}</b><span class="tt"><i style="background:${cv(TCOL[d.t])}"></i>${esc(TOPIC[d.t])} · ${esc(DEPT[d.dv])}</span>${d.ds ? `<span class="ts">${snippet(d.ds)}</span>` : ""}<span class="th">${same.length - 1} more on this topic across ${new Set(same.map((o) => o.dv)).size} departments · click to open</span>`);
    })
    .on("pointermove", move)
    .on("pointerleave", leave)
    .on("click", (_e, d) => actions.select(d.id))
    .on("keydown", (e: KeyboardEvent, d) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        actions.select(d.id);
      }
    })
    .on("focusin", (_e, d) => applyHover({ t: d.t, k: d.dv + "|" + d.t, dv: null, id: d.id }))
    .on("focusout", () => applyHover(NO_HOVER));
  gTerr.selectAll<SVGCircleElement, unknown>(".ring")
    .on("pointerenter", function (e: PointerEvent) {
      const k = this.dataset.k!;
      const [dv, t] = k.split("|");
      const l = ITEMS.filter((i) => i.dv === dv && i.t === t);
      const all = ITEMS.filter((i) => i.t === t);
      applyHover({ t, k, dv: null, id: null });
      ripple(k);
      showTip(e, `<b>${esc(TOPIC[t])}</b><span>${l.length} use case${l.length > 1 ? "s" : ""} in ${esc(DEPT[dv])}</span><span class="th">${all.length} in total across ${new Set(all.map((i) => i.dv)).size} departments · click to show them all</span>`);
    })
    .on("pointermove", move)
    .on("pointerleave", leave)
    .on("click", function () { actions.toggleTopic(this.dataset.t!); });
  gTerr.selectAll<SVGCircleElement, unknown>(".terr")
    .on("pointerenter", function (e: PointerEvent) {
      const dv = this.dataset.dv!;
      const l = ITEMS.filter((i) => i.dv === dv);
      const ts = d3.rollups(l, (v) => v.length, (i) => i.t).sort((a, b) => b[1] - a[1]);
      applyHover({ t: null, k: null, dv, id: null });
      showTip(e, `<b>${esc(DEPT[dv])}</b><span>${l.length} use cases in ${ts.length} topics</span><span class="tbars">${ts.slice(0, 5).map(([t, n]) => `<span><i style="background:${cv(TCOL[t])};width:${8 + n * 6}px"></i>${esc(TSHORT[t])} ${n}</span>`).join("")}</span>`);
    })
    .on("pointermove", move)
    .on("pointerleave", leave)
    .on("click", function () { actions.toggleDiv(this.dataset.dv!); });
  svg
    .on("pointermove.spot", (e: PointerEvent) => {
      const [x, y] = d3.pointer(e, zoomG.node());
      spot.attr("cx", x).attr("cy", y).attr("opacity", 1);
    })
    .on("pointerleave.spot", () => spot.attr("opacity", 0));

  /* zoom */
  const extent: [[number, number], [number, number]] = [[VB[0], VB[1]], [VB[0] + VB[2], VB[1] + VB[3]]];
  const zoom = d3.zoom<SVGSVGElement, unknown>().extent(extent).scaleExtent([1, 6]).translateExtent(extent).on("zoom", (e) => {
    zoomG.attr("transform", e.transform);
    const k = Math.pow(e.transform.k, 0.75);
    gLab.selectAll(".buname").style("font-size", 13 / k + "px").attr("stroke-width", 4 / k);
    gLab.selectAll(".dlabel").style("font-size", 10 / k + "px").attr("stroke-width", 3 / k);
  });
  const s = svg as unknown as d3.Selection<SVGSVGElement, unknown, null, undefined>;
  s.call(zoom).on("dblclick.zoom", null);
  return {
    hexes, deptNodes, gBadge, applyHover,
    zoomBy: (k) => s.transition().duration(300).call(zoom.scaleBy, k),
    reset: () => s.transition().duration(400).call(zoom.transform, d3.zoomIdentity),
    focusOn: (x, y) => {
      const k = 1.6;
      s.transition().duration(600).call(zoom.transform, d3.zoomIdentity.translate(VB[0] + VB[2] / 2 - x * k, VB[1] + VB[3] / 2 - y * k).scale(k));
    },
  };
}

const WHY = { text: "Mentions the word", dept: "In the department" } as const;

/** Innovator exploration: the use case atlas. */
export function ExploreView() {
  const { all } = useApp();
  const ITEMS = useMemo(() => {
    const items = atlasItems(all);
    prepare(items);
    return items;
  }, [all]);
  const cnt = (f: (i: AtlasItem) => boolean) => ITEMS.filter(f).length;
  const TOPIC_ORDER = useMemo(
    () => Object.keys(TOPIC).filter((t) => t !== "other").sort((a, b) => cnt((i) => i.t === b) - cnt((i) => i.t === a)).concat(["other"]),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ITEMS],
  );
  const DEPT_ORDER = useMemo(
    () => Object.keys(DEPT).filter((d) => cnt((i) => i.dv === d))
      .sort((a, b) => +(a === "unassigned") - +(b === "unassigned") || +(a === "general") - +(b === "general") || cnt((i) => i.dv === b) - cnt((i) => i.dv === a)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ITEMS],
  );
  const suggestions = useMemo(() => SUGGESTIONS.map((w) => [w, ITEMS.filter((i) => queryMatch(i, [w])).length] as const), [ITEMS]);

  const [f, setF] = useState<Filters>({ q: "", topic: null, div: null, sel: null });
  const [legendLit, setLegendLit] = useState<string | null>(null);
  const [contacted, setContacted] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const qRef = useRef<HTMLInputElement>(null);
  const mapRef = useRef<AtlasMap | null>(null);
  useFullBleed();

  const select = (id: number | null) => {
    setF((s) => ({ ...s, sel: id }));
    setContacted(false);
    if (id != null) mapRef.current?.focusOn(ITEMS[id].x, ITEMS[id].y);
  };

  useEffect(() => {
    mapRef.current = drawMap(svgRef.current!, tipRef.current!, cardRef.current!, ITEMS, DEPT_ORDER, {
      select: (id) => {
        setF((s) => ({ ...s, sel: id }));
        setContacted(false);
        mapRef.current?.focusOn(ITEMS[id].x, ITEMS[id].y);
      },
      toggleTopic: (t) => setF((s) => ({ ...s, topic: s.topic === t ? null : t, div: null, sel: null })),
      toggleDiv: (dv) => setF((s) => ({ ...s, div: s.div === dv ? null : dv, topic: null, sel: null })),
      legendHover: setLegendLit,
    });
  }, [ITEMS, DEPT_ORDER]);

  const { active, words, exp, matches } = useMemo(() => {
    const words = parseQ(f.q);
    const expansions: string[] = [];
    const active = !!(words.length || f.topic || f.div);
    ITEMS.forEach((i) => {
      i.match = queryMatch(i, words, expansions) && (!f.topic || i.t === f.topic) && (!f.div || i.dv === f.div);
    });
    return { active, words, exp: [...new Set(expansions)], matches: ITEMS.filter((i) => i.match) };
  }, [ITEMS, f.q, f.topic, f.div]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.hexes.style("--f", (d) => cv(TCOL[d.t])).classed("dim", (d) => active && !d.match)
      .classed("hit", (d) => active && d.match && words.length > 0).classed("sel", (d) => d.id === f.sel);
    map.gBadge.selectAll("*").remove();
    if (active)
      map.deptNodes.forEach((n) => {
        const c = matches.filter((i) => i.dv === n.data.dv).length;
        if (!c) return;
        const t = String(c);
        const w = 14 + t.length * 8;
        const g = map.gBadge.append("g").attr("class", "ua-badge").attr("transform", `translate(${n.x + n.r * 0.72},${n.y - n.r * 0.72})`);
        g.append("rect").attr("x", -w / 2).attr("y", -11).attr("width", w).attr("height", 22).attr("rx", 11);
        g.append("text").attr("text-anchor", "middle").attr("y", 4.5).text(t);
      });
  }, [active, words, matches, f.sel, ITEMS]);

  const setQ = (q: string) => setF((s) => ({ ...s, q }));
  const clear = () => {
    setF((s) => ({ ...s, q: "", topic: null, div: null }));
    qRef.current?.focus();
  };
  const filt = [f.div && DEPT[f.div], f.topic && TOPIC[f.topic]].filter(Boolean);
  const sw = (t: string) => <i className="tdot" style={{ background: cv(TCOL[t]) }} />;
  const rowBtn = (i: AtlasItem, extra?: ReactNode) => (
    <button key={i.id} type="button" className="row" onClick={() => select(i.id)}>
      <span className="n">{i.n}</span>
      <span />
      <span className="m">{extra ?? `${DEPT[i.dv]} · ${TOPIC[i.t]}`}</span>
    </button>
  );

  function rail() {
    const out: ReactNode[] = [];
    const sel = f.sel != null ? ITEMS[f.sel] : null;
    if (sel) {
      const sib = ITEMS.filter((o) => o.id !== sel.id && o.dv === sel.dv && o.t === sel.t && o.n !== sel.n);
      const elsewhere = ITEMS.filter((o) => o.t === sel.t && o.dv !== sel.dv);
      out.push(
        <div key="sel" className="ua-card ua-detail">
          <h4>Selected use case</h4>
          <div className="n">{sel.n}</div>
          <dl className="ua-facts">
            <dt>Topic</dt>
            <dd>{sw(sel.t)}{TOPIC[sel.t]}</dd>
            <dt>Department</dt>
            <dd>{DEPT[sel.dv]}</dd>
            <dt>Team</dt>
            <dd>{sel.d} · {sel.bu}</dd>
          </dl>
          {sel.ds ? <p className="desc">{sel.ds}</p> : <div className="sub">No description yet.</div>}
          <div className="btnrow">
            <button type="button" className={contacted ? "btn primary done" : "btn primary"} onClick={() => setContacted(true)}>
              {contacted ? "Request sent (demo)" : "Contact the team"}
            </button>
            <button type="button" className="btn" onClick={() => { select(null); mapRef.current?.reset(); }}>
              Close
            </button>
          </div>
          {sib.length ? (
            <>
              <h4>Same cluster</h4>
              <div className="sim">{sib.map((o) => rowBtn(o, o.d))}</div>
            </>
          ) : (
            <div className="sub">The only use case on this topic in {DEPT[sel.dv]}.</div>
          )}
          {elsewhere.length > 0 && (
            <button type="button" className="btn" onClick={() => { setF((s) => ({ ...s, topic: sel.t, div: null, sel: null })); mapRef.current?.reset(); }}>
              Show all {elsewhere.length + sib.length + 1} on {TOPIC[sel.t]}
            </button>
          )}
        </div>,
      );
    }
    if (active) {
      const why = (i: AtlasItem) => (words.length && i.why ? <> · <span className="why">{WHY[i.why]}</span></> : null);
      const deptHit = words.length ? DEPT_ORDER.filter((d) => matches.some((i) => i.dv === d && i.why === "dept")) : [];
      const by = [...deptHit, ...DEPT_ORDER.filter((d) => !deptHit.includes(d))]
        .map((d) => [d, matches.filter((i) => i.dv === d)] as const).filter((x) => x[1].length);
      const one = by.length === 1;
      const groups = one ? TOPIC_ORDER.map((k) => [k, matches.filter((i) => i.t === k)] as const).filter((x) => x[1].length) : by;
      const head = one
        ? `${matches.length} use case${matches.length === 1 ? "" : "s"} in ${DEPT[by[0][0]]}`
        : `${matches.length} use cases in ${by.length} departments`;
      const note = words.length ? (
        <div className="sub">
          Search looks at the name and description of each use case, and at the name of its department.{" "}
          {deptHit.length
            ? `“${f.q.trim()}” names the ${deptHit.map((d) => DEPT[d]).join(" and ")} department, so its whole area lights up. Matches in other areas mention the word in their name or description.`
            : "Each use case sits in the area of the department that owns it, so matches can appear anywhere on the map."}
        </div>
      ) : one ? (
        <div className="sub">Grouped by topic. All {matches.length} are listed.</div>
      ) : null;
      out.push(
        <div key="results" className="ua-card" aria-label="Results">
          <h2>{head}</h2>
          {note}
          <div className="list">
            {groups.length ? (
              groups.map(([g, l]) => (
                <div key={g} className="lgroup-wrap">
                  <div className="lgroup">
                    {one ? <>{sw(g)}{TOPIC[g]}</> : DEPT[g]}
                    <span className="n">{l.length}</span>
                  </div>
                  {l.slice().sort((a, c) => TOPIC_ORDER.indexOf(a.t) - TOPIC_ORDER.indexOf(c.t) || a.n.localeCompare(c.n))
                    .map((i) => rowBtn(i, <>{one ? i.d : <>{sw(i.t)}{TOPIC[i.t]}</>}{why(i)}</>))}
                </div>
              ))
            ) : (
              <div className="sub">Nothing found yet. Your idea may be new to the group.</div>
            )}
          </div>
        </div>,
      );
    } else if (!sel) {
      out.push(
        <div key="topics" className="ua-card">
          <h2>Topics by department</h2>
          <div className="sub">Select a topic to highlight it on the map.</div>
          <div className="fp">
            {DEPT_ORDER.map((d) => {
              const ts = d3.rollups(ITEMS.filter((i) => i.dv === d), (v) => v.length, (i) => i.t).sort((a, b) => b[1] - a[1]);
              return (
                <div key={d} className="fpu">
                  <div className="h">{DEPT[d]}</div>
                  <div className="kw">
                    {ts.map(([t]) => (
                      <button key={t} type="button" onClick={() => setF((s) => ({ ...s, topic: t, div: d }))}>
                        {sw(t)}{TSHORT[t]}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>,
        <div key="how" className="ua-card">
          <h4>How to explore</h4>
          <div className="sub">
            Type a keyword or pick a suggestion to light up matches. Hover a hexagon for its name and select it to read more. Drag to pan and use +
            and − to zoom.
          </div>
        </div>,
      );
    }
    return out;
  }

  return (
    <div className="atlas">
      <div className="ua-page">
        <section className="hero">
          <div>
            <div className="crumb">Explore / Use case atlas</div>
            <h1>Find use cases related to your idea</h1>
            <p>
              Every hexagon is one AI use case. Each area is a business department, and the clusters inside it are topics. Search by keyword to
              light up matching use cases, then select one to read what it is about and see what else sits in the same cluster.
            </p>
          </div>
          <div className="ua-kpis">
            {[[ITEMS.length, "use cases"], [DEPT_ORDER.length, "departments"], [TOPIC_ORDER.length, "topics"]].map(([v, l]) => (
              <div key={l} className="ua-kpi">
                <div className="v">{v}</div>
                <div className="l">{l}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="searchband" aria-label="Search and filters">
          <div className="sbox">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
            <input
              ref={qRef}
              className="q"
              type="text"
              autoComplete="off"
              placeholder="Search keywords, e.g. forecast, contract, chatbot, substation"
              aria-label="Search use cases by keyword"
              value={f.q}
              onChange={(e) => setQ(e.target.value)}
            />
            <button type="button" className="clear" aria-label="Clear search" hidden={!(f.q || f.topic || f.div)} onClick={clear}>
              ×
            </button>
          </div>
          <div className="controls">
            <div className="group" aria-label="Suggested keywords">
              <span className="glabel">Try</span>
              {suggestions.map(([w, n]) => (
                <button key={w} type="button" className="ua-chip" aria-pressed={words.length === 1 && words[0] === w} onClick={() => setQ(w)}>
                  {w}
                  <span className="n">{n}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="also" aria-live="polite" data-testid="atlas-also">
            {active && (
              <>
                <b>{matches.length}</b> of {ITEMS.length} use cases
                {filt.length > 0 && <> in <b>{filt.join(" · ")}</b></>}
                {exp.length > 0 && <> · also matched related words: <b>{exp.join(", ")}</b></>}
              </>
            )}
          </div>
        </section>

        <section className="main">
          <div className="mapcard" ref={cardRef}>
            <svg ref={svgRef} className="map" viewBox="0 0 900 774" role="img" aria-label="Map of AI use cases by business department and topic" />
            <div className="maptools">
              <button type="button" aria-label="Zoom in" onClick={() => mapRef.current?.zoomBy(1.5)}>+</button>
              <button type="button" aria-label="Zoom out" onClick={() => mapRef.current?.zoomBy(1 / 1.5)}>−</button>
              <button type="button" aria-label="Reset view" onClick={() => mapRef.current?.reset()}>⟲</button>
            </div>
            <div className="ua-legend" onPointerLeave={() => mapRef.current?.applyHover(NO_HOVER)}>
              {TOPIC_ORDER.map((k) => (
                <button
                  key={k}
                  type="button"
                  className={legendLit === k ? "lit" : undefined}
                  aria-pressed={f.topic === k}
                  style={{ "--lc": cv(TCOL[k]) } as CSSProperties}
                  onPointerOver={() => legendLit !== k && mapRef.current?.applyHover({ ...NO_HOVER, t: k })}
                  onClick={() => setF((s) => ({ ...s, topic: s.topic === k ? null : k, div: null, sel: null }))}
                >
                  <i style={{ background: cv(TCOL[k]) }} />
                  {TOPIC[k]}
                </button>
              ))}
            </div>
            <div className="tip" ref={tipRef} hidden />
          </div>
          <aside className="rail" aria-live="polite" aria-label="Use cases">
            {rail()}
          </aside>
        </section>

        <p className="foot">
          Data: gold layer of the AI Cockpit pipeline, table AssessedInitiatives ({ITEMS.length} active use cases). Topics come from the Topic
          column in gold, derived in the silver_to_gold step from the silver name and description by keyword rules. Areas are the department of
          the owner linked from gold (Owner.Department), grouped by function, for example Infra in 50Hertz and ETB. Use cases without an owner sit
          in “No owner yet”. Search matches words in names, descriptions and department names.
        </p>
      </div>
    </div>
  );
}
