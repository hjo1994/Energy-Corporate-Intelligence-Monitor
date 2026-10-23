import type { Initiative } from "../api/types";
import {
  businessUnitsIn,
  NO_BUSINESS_UNIT,
  NO_BUSINESS_UNIT_LABEL,
  stagesIn,
  toggle,
} from "../domain/filters";
import { stageColor } from "../domain/stage";
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

export function StageChips({ all }: { all: Initiative[] }) {
  const { filters, setFilters } = useApp();
  return (
    <div className="chip-group" role="group" aria-label="Stage">
      <span className="group-label">Stage</span>
      <Chip active={filters.stages.length === 0} onClick={() => setFilters((f) => ({ ...f, stages: [] }))}>
        All
      </Chip>
      {stagesIn(all).map((s) => (
        <Chip
          key={s}
          dot={stageColor(s)}
          active={filters.stages.includes(s)}
          onClick={() => setFilters((f) => ({ ...f, stages: toggle(f.stages, s) }))}
        >
          {s}
        </Chip>
      ))}
    </div>
  );
}
