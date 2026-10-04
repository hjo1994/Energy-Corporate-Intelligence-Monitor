import { useState } from "react";
import type { Initiative } from "../api/types";
import { DetailDialog } from "../components/DetailDialog";
import { EffortMeter, OwnerCell, StatusBadge, ValueMeter } from "../components/small";
import { Chip } from "../components/small";
import { flagshipLabel, formatQuarter } from "../domain/format";
import {
  businessUnitsIn,
  countBy,
  businessUnitOf,
  flagshipOf,
  flagshipsIn,
  NO_BUSINESS_UNIT,
  NO_BUSINESS_UNIT_LABEL,
  sortInitiatives,
  statusesIn,
  toggle,
  type SortKey,
} from "../domain/filters";
import { statusColor } from "../domain/status";
import { useApp } from "../store";

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "name", label: "Initiative" },
  { key: "owner", label: "Owner" },
  { key: "status", label: "Status" },
  { key: "effort", label: "Aufwand" },
  { key: "value", label: "Mehrwert" },
  { key: "delivery", label: "Lieferung" },
];

function FilterGroup({
  title,
  options,
  selected,
  counts,
  onToggle,
  dot,
}: {
  title: string;
  options: { value: string; label: string }[];
  selected: string[];
  counts: Map<string, number>;
  onToggle: (v: string) => void;
  dot?: (v: string) => string;
}) {
  return (
    <fieldset className="filter-group">
      <legend>{title}</legend>
      {options.map((o) => (
        <label key={o.value} className="filter-row-item">
          <input type="checkbox" checked={selected.includes(o.value)} onChange={() => onToggle(o.value)} />
          {dot && <span className="dot" style={{ background: dot(o.value) }} />}
          <span className="grow">{o.label}</span>
          <span className="mono muted">{counts.get(o.value) ?? 0}</span>
        </label>
      ))}
    </fieldset>
  );
}

export function ListView() {
  const { all, visible, filters, setFilters } = useApp();
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({ key: "value", dir: "desc" });
  const [open, setOpen] = useState<Initiative | null>(null);

  const rows = sortInitiatives(visible, sort.key, sort.dir);

  return (
    <div className="split">
      <aside className="card filter-side" aria-label="Filter">
        <FilterGroup
          title="Status"
          options={statusesIn(all).map((s) => ({ value: s, label: s }))}
          selected={filters.statuses}
          counts={countBy(all, (i) => i.status)}
          onToggle={(v) => setFilters((f) => ({ ...f, statuses: toggle(f.statuses, v) }))}
          dot={statusColor}
        />
        <FilterGroup
          title="Business Unit"
          options={businessUnitsIn(all).map((b) => ({
            value: b,
            label: b === NO_BUSINESS_UNIT ? NO_BUSINESS_UNIT_LABEL : b,
          }))}
          selected={filters.businessUnits}
          counts={countBy(all, businessUnitOf)}
          onToggle={(v) => setFilters((f) => ({ ...f, businessUnits: toggle(f.businessUnits, v) }))}
        />
        <FilterGroup
          title="Flagship"
          options={flagshipsIn(all).map((v) => ({ value: v, label: flagshipLabel(v) }))}
          selected={filters.flagships}
          counts={countBy(all, flagshipOf)}
          onToggle={(v) => setFilters((f) => ({ ...f, flagships: toggle(f.flagships, v) }))}
        />
      </aside>

      <section className="card list-card" aria-label="Initiativen">
        <div className="list-head">
          <span className="muted">
            {rows.length} von {all.length} Initiativen
          </span>
          <Chip
            onClick={() => setSort((s) => ({ ...s, dir: s.dir === "asc" ? "desc" : "asc" }))}
            active
          >
            Sortierung: {COLUMNS.find((c) => c.key === sort.key)?.label} {sort.dir === "asc" ? "↑" : "↓"}
          </Chip>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {COLUMNS.map((c) => (
                  <th
                    key={c.key}
                    aria-sort={sort.key === c.key ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
                  >
                    <button
                      type="button"
                      className="th-btn"
                      onClick={() =>
                        setSort((s) =>
                          s.key === c.key
                            ? { key: c.key, dir: s.dir === "asc" ? "desc" : "asc" }
                            : { key: c.key, dir: c.key === "name" || c.key === "owner" ? "asc" : "desc" },
                        )
                      }
                    >
                      {c.label}
                      {sort.key === c.key && <span aria-hidden="true"> {sort.dir === "asc" ? "↑" : "↓"}</span>}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((i) => (
                <tr key={i.id}>
                  <td className="cell-name">
                    <button type="button" className="link-btn" onClick={() => setOpen(i)}>
                      {i.name}
                    </button>
                    <span className="truncate muted">{i.description}</span>
                  </td>
                  <td>
                    <OwnerCell initiative={i} />
                  </td>
                  <td>
                    <StatusBadge status={i.status} />
                  </td>
                  <td>
                    <EffortMeter score={i.solution_complexity_score} />
                  </td>
                  <td>
                    <ValueMeter score={i.value_score} />
                  </td>
                  <td className="muted">{formatQuarter(i.date_delivery)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <p className="empty">Keine Initiativen für diese Filter.</p>}
        </div>
      </section>

      {open && <DetailDialog initiative={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
