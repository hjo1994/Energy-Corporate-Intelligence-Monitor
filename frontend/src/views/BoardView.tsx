import { useState } from "react";
import type { Initiative } from "../api/types";
import { BusinessUnitChips } from "../components/FilterChips";
import { DetailDialog } from "../components/DetailDialog";
import { Avatar, EffortMeter, ValueMeter } from "../components/small";
import { STAGE_ORDER, stageColor } from "../domain/stage";
import { sortInitiatives } from "../domain/filters";
import { useApp } from "../store";

const ALWAYS_SHOWN = ["Idea", "Exploration", "PoC", "MVP", "Implementation", "Production"];

export function BoardView() {
  const { all, visible } = useApp();
  const [open, setOpen] = useState<Initiative | null>(null);

  const columns = STAGE_ORDER.map((stage) => ({
    stage,
    items: sortInitiatives(
      visible.filter((i) => i.stage === stage),
      "potential",
      "desc",
    ),
  })).filter((c) => ALWAYS_SHOWN.includes(c.stage) || c.items.length > 0);

  return (
    <>
      <div className="filter-row">
        <BusinessUnitChips all={all} />
      </div>
      <div className="board">
        {columns.map(({ stage, items }) => (
          <section key={stage} className="col" style={{ "--c": stageColor(stage) } as React.CSSProperties} aria-label={stage}>
            <header className="col-head">
              <span className="col-title">
                <span className="dot" />
                {stage}
              </span>
              <span className="mono muted">{items.length}</span>
            </header>
            {items.length === 0 && <p className="empty small">No initiatives</p>}
            {items.map((i) => (
              <button type="button" key={i.id} className="kcard" onClick={() => setOpen(i)}>
                <span className="kcard-top">
                  <span className="kcard-name">{i.name}</span>
                  {i.value_type && i.value_type.name !== "-" && <span className="tag">{i.value_type.name}</span>}
                </span>
                {i.description && <span className="kcard-desc">{i.description}</span>}
                <span className="kcard-bottom">
                  <span className="kcard-owner">
                    {i.owner ? (
                      <>
                        <Avatar name={i.owner.name} size={20} />
                        <span className="truncate">{i.owner.department ?? i.owner.name}</span>
                      </>
                    ) : (
                      <span className="missing">no owner</span>
                    )}
                  </span>
                  <span className="kcard-scores">
                    <EffortMeter score={i.solution_complexity_score} />
                    <ValueMeter eur={i.potential_value_eur} />
                  </span>
                </span>
              </button>
            ))}
          </section>
        ))}
      </div>
      {open && <DetailDialog initiative={open} onClose={() => setOpen(null)} />}
    </>
  );
}
