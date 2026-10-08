import type { Initiative } from "../api/types";
import { summarize } from "../domain/filters";

function Tile({ label, value, note, accent }: { label: string; value: string; note: string; accent?: boolean }) {
  return (
    <div className="card kpi">
      <span className="kpi-label">{label}</span>
      <span className="mono kpi-value" style={accent ? { color: "var(--accent)" } : undefined}>
        {value}
      </span>
      <span className="kpi-note">{note}</span>
    </div>
  );
}

export function Kpis({ items }: { items: Initiative[] }) {
  const s = summarize(items);
  return (
    <section className="kpis" aria-label="Key figures">
      <Tile label="Initiatives" value={String(s.total)} note="matching the filters" />
      <Tile label="In progress" value={String(s.inProgress)} note="PoC, MVP, Implementation" accent />
      <Tile
        label="Avg. value"
        value={s.averageValue === null ? "–" : s.averageValue.toFixed(1)}
        note={`out of 10, ${s.withValue} of ${s.total} rated`}
      />
      <Tile label="Without value" value={String(s.withoutValue)} note="no score in the source" />
    </section>
  );
}
