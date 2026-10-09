import { applyFilters, toggle } from "../domain/filters";
import { flagshipStats } from "../domain/flagship";
import { formatScore } from "../domain/format";
import { useApp } from "../store";

/** Initiatives and average value per strategic pillar; a click filters by that flagship. */
export function FlagshipWidget() {
  const { all, filters, setFilters } = useApp();

  // Every filter except the flagship one, otherwise picking a row would make all others vanish.
  const stats = flagshipStats(applyFilters(all, { ...filters, flagships: [] }));
  const largest = Math.max(1, ...stats.map((s) => s.count));

  return (
    <section className="card flagships" aria-label="Flagships">
      <h2>Flagships</h2>
      <p className="muted">
        Initiatives and average value per strategic pillar. Click a row to filter by it; the average
        is only as reliable as the number of ratings behind it.
      </p>
      {stats.length === 0 && <p className="empty small">No initiatives match the filters.</p>}
      <div className="flag-list">
        {stats.map((s) => (
          <button
            key={s.key}
            type="button"
            className="flag-row"
            aria-pressed={filters.flagships.includes(s.key)}
            onClick={() => setFilters((f) => ({ ...f, flagships: toggle(f.flagships, s.key) }))}
          >
            <span className="flag-line">
              <span>{s.label}</span>
              <span className="muted">
                {s.count} · {s.averageValue === null ? "no value rated" : `avg. ${formatScore(s.averageValue)}`}
                {s.averageValue !== null && ` (${s.rated} of ${s.count} rated)`}
              </span>
            </span>
            <span className="flag-bar" style={{ width: `${(s.count / largest) * 100}%` }} />
          </button>
        ))}
      </div>
    </section>
  );
}
