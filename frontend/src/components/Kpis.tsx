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
    <section className="kpis" aria-label="Kennzahlen">
      <Tile label="Initiativen" value={String(s.total)} note="entsprechend der Filter" />
      <Tile label="In Umsetzung" value={String(s.inProgress)} note="PoC, MVP, Implementation" accent />
      <Tile
        label="Ø Mehrwert"
        value={s.averageValue === null ? "–" : s.averageValue.toFixed(1)}
        note={`von 10, bei ${s.withValue} von ${s.total} erfasst`}
      />
      <Tile label="Ohne Mehrwert" value={String(s.withoutValue)} note="kein Score in der Quelle" />
    </section>
  );
}
