import type { Initiative } from "../api/types";
import {
  businessUnitsIn,
  NO_BUSINESS_UNIT,
  NO_BUSINESS_UNIT_LABEL,
  statusesIn,
  toggle,
} from "../domain/filters";
import { statusColor } from "../domain/status";
import { useApp } from "../store";
import { Chip } from "./small";

export function BusinessUnitChips({ all }: { all: Initiative[] }) {
  const { filters, setFilters } = useApp();
  return (
    <div className="chip-group" role="group" aria-label="Business Unit">
      <span className="group-label">Business Unit</span>
      <Chip active={filters.businessUnits.length === 0} onClick={() => setFilters((f) => ({ ...f, businessUnits: [] }))}>
        All
      </Chip>
      {businessUnitsIn(all).map((bu) => (
        <Chip
          key={bu}
          active={filters.businessUnits.includes(bu)}
          onClick={() => setFilters((f) => ({ ...f, businessUnits: toggle(f.businessUnits, bu) }))}
        >
          {bu === NO_BUSINESS_UNIT ? NO_BUSINESS_UNIT_LABEL : bu}
        </Chip>
      ))}
    </div>
  );
}

export function StatusChips({ all }: { all: Initiative[] }) {
  const { filters, setFilters } = useApp();
  return (
    <div className="chip-group" role="group" aria-label="Status">
      <span className="group-label">Status</span>
      <Chip active={filters.statuses.length === 0} onClick={() => setFilters((f) => ({ ...f, statuses: [] }))}>
        All
      </Chip>
      {statusesIn(all).map((s) => (
        <Chip
          key={s}
          dot={statusColor(s)}
          active={filters.statuses.includes(s)}
          onClick={() => setFilters((f) => ({ ...f, statuses: toggle(f.statuses, s) }))}
        >
          {s}
        </Chip>
      ))}
    </div>
  );
}
