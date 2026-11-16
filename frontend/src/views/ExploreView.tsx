import { useEffect, useMemo, useState, type CSSProperties } from "react";
import type { Initiative } from "../api/types";
import { groupByDepartment, NO_DEPARTMENT_LABEL } from "../domain/departments";
import { flagshipLabel } from "../domain/format";
import { canonicalStage } from "../domain/path";
import { STAGE_ORDER, stageColor } from "../domain/stage";
import { useApp } from "../store";

type WithColor = CSSProperties & { "--c"?: string };

const topicOf = (i: Initiative): string | null => (i.value_type ? flagshipLabel(i.value_type.name) : null);
const departmentOf = (i: Initiative): string => i.owner?.department?.trim() || NO_DEPARTMENT_LABEL;

function matches(i: Initiative, q: string): boolean {
  if (q === "") return true;
  return [i.name, i.description, i.owner?.department, topicOf(i)].some((t) => (t ?? "").toLowerCase().includes(q));
}

function Hex({ i, selected, onSelect }: { i: Initiative; selected: boolean; onSelect: () => void }) {
  const stage = canonicalStage(i.stage);
  return (
    <button
      type="button"
      className="ex-hex"
      style={{ "--c": stageColor(stage) } as WithColor}
      aria-label={`${i.name} · ${stage}`}
      aria-pressed={selected}
      title={`${i.name} · ${stage}`}
      onClick={onSelect}
    >
      <svg viewBox="0 0 20 22" aria-hidden="true">
        <polygon points="10,1 19,6 19,16 10,21 1,16 1,6" />
      </svg>
    </button>
  );
}

function Detail({ i, onClose }: { i: Initiative; onClose: () => void }) {
  const stage = canonicalStage(i.stage);
  return (
    <aside className="card ex-detail" aria-label="Use case details">
      <div className="ex-detail-top">
        <span className="badge" style={{ "--c": stageColor(stage) } as WithColor}>
          <span className="dot" />
          {stage}
        </span>
        <button type="button" className="drawer-close" aria-label="Close details" onClick={onClose}>
          ×
        </button>
      </div>
      <h2>{i.name}</h2>
      <dl className="ex-facts">
        <div><dt>Department</dt><dd>{departmentOf(i)}</dd></div>
        <div><dt>Topic</dt><dd>{topicOf(i) ?? "–"}</dd></div>
        <div><dt>Owner</dt><dd>{i.owner?.name ?? "–"}</dd></div>
      </dl>
      <p className={i.description ? undefined : "missing"}>{i.description || "No description yet."}</p>
    </aside>
  );
}

/** Innovator exploration: every use case as a hexagon, grouped by department, coloured by stage. */
export function ExploreView() {
  const { all } = useApp();
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const q = search.trim().toLowerCase();
  const groups = useMemo(
    () => groupByDepartment(all).map((g) => ({ ...g, items: g.items.filter((i) => matches(i, q)) })).filter((g) => g.items.length > 0),
    [all, q],
  );
  const shown = groups.reduce((n, g) => n + g.items.length, 0);
  const selected = all.find((i) => i.id === selectedId) ?? null;
  const stages = useMemo(() => {
    const present = new Set(all.map((i) => canonicalStage(i.stage)));
    return STAGE_ORDER.filter((s) => present.has(s));
  }, [all]);

  useEffect(() => {
    if (selectedId === null) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setSelectedId(null);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selectedId]);

  return (
    <div className="ex view-enter">
      <header className="ex-head">
        <div>
          <h1>Exploration</h1>
          <p className="muted">
            {all.length} use cases, grouped by department. Each hexagon is one use case, coloured by its stage.
          </p>
        </div>
        <label className="search ex-search">
          <span className="sr-only">Search use cases</span>
          <input
            type="search"
            placeholder="Search name, department, topic …"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </header>

      <ul className="ex-legend" aria-label="Stages">
        {stages.map((s) => (
          <li key={s}>
            <span className="dot" style={{ "--c": stageColor(s) } as WithColor} />
            {s}
          </li>
        ))}
      </ul>

      <div className={selected ? "ex-layout ex-layout-open" : "ex-layout"}>
        <div className="ex-grid">
          {groups.map((g) => (
            <section key={g.key} className="card ex-dept" aria-label={g.label}>
              <header>
                <h2>{g.label}</h2>
                <span className="mono muted">{g.items.length}</span>
              </header>
              <div className="ex-hexes">
                {g.items.map((i) => (
                  <Hex key={i.id} i={i} selected={i.id === selectedId} onSelect={() => setSelectedId(i.id === selectedId ? null : i.id)} />
                ))}
              </div>
            </section>
          ))}
          {shown === 0 && <p className="empty">No use cases match “{search.trim()}”.</p>}
        </div>
        {selected && <Detail i={selected} onClose={() => setSelectedId(null)} />}
      </div>
    </div>
  );
}
