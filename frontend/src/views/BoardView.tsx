import { useState } from "react";
import type { Initiative } from "../api/types";
import { BusinessUnitChips } from "../components/FilterChips";
import { DetailDialog } from "../components/DetailDialog";
import { Avatar, EffortMeter, ValueMeter } from "../components/small";
import { STATUS_ORDER, statusColor } from "../domain/status";
import { sortInitiatives } from "../domain/filters";
import { useApp } from "../store";

const ALWAYS_SHOWN = [
  "Idea",
  "Exploration",
  "PoC",
  "MVP",
  "Implementation",
  "Production",
];

export function BoardView() {
  const { all, visible } = useApp();
  const [open, setOpen] = useState<Initiative | null>(null);

  const columns = STATUS_ORDER.map((status) => ({
    status,
    items: sortInitiatives(
      visible.filter((i) => i.status === status),
      "value",
      "desc",
    ),
  })).filter(
    (c) => ALWAYS_SHOWN.includes(c.status) || c.items.length > 0,
  );

  return (
    <>
      <div className="filter-row">
        <BusinessUnitChips all={all} />
      </div>

      <div className="board">
        {columns.map(({ status, items }) => (
          <section
            key={status}
            className="col"
            style={{ "--c": statusColor(status) } as React.CSSProperties}
            aria-label={status}
          >
            <header className="col-head">
              <span className="col-title">
                <span className="dot" />
                {status}
              </span>

              <span className="mono muted">{items.length}</span>
            </header>

            {items.length === 0 && (
              <p className="empty small">No initiatives</p>
            )}

            {items.map((i) => (
              <button
                type="button"
                key={i.id}
                className="kcard"
                onClick={() => setOpen(i)}
              >
                <span className="kcard-top">
                  <span className="kcard-name">{i.name}</span>

                  {i.value_type &&
                    i.value_type.name !== "-" && (
                      <span className="tag">
                        {i.value_type.name}
                      </span>
                    )}
                </span>

                {i.description && (
                  <span className="kcard-desc">
                    {i.description}
                  </span>
                )}

                <span className="kcard-bottom">
                  <span className="kcard-owner">
                    {i.owner ? (
                      <>
                        <Avatar name={i.owner.name} size={20} />
                        <span className="truncate">
                          {i.owner.department ?? i.owner.name}
                        </span>
                      </>
                    ) : (
                      <span className="missing">
                        no owner
                      </span>
                    )}
                  </span>

                  <span className="kcard-scores">
                    <EffortMeter score={i.solution_complexity_score} />
                    <ValueMeter score={i.value_score} />
                  </span>
                </span>
              </button>
            ))}
          </section>
        ))}
      </div>

      {open && (
        <DetailDialog
          initiative={open}
          onClose={() => setOpen(null)}
        />
      )}
    </>
  );
}