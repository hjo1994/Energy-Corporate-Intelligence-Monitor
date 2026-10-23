import type { Initiative } from "../api/types";
import { ELEVATED_RISK_FROM, summarize } from "../domain/filters";
import { formatEur } from "../domain/format";

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
        label="Potential per year"
        value={formatEur(s.totalPotential)}
        note={`estimate, ${s.withPotential} of ${s.total} estimated · cost ${formatEur(s.totalAnnualCost)}/yr`}
      />
      <Tile
        label={`Risk level ${ELEVATED_RISK_FROM}+`}
        value={String(s.elevatedRisk)}
        note="estimated; works council involvement"
      />
    </section>
  );
}
