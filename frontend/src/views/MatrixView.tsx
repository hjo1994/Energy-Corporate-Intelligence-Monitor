import { useState, type CSSProperties } from "react";
import { BusinessUnitChips, StageChips } from "../components/FilterChips";
import { DetailBody } from "../components/DetailBody";
import { FlagshipWidget } from "../components/FlagshipWidget";
import { Kpis } from "../components/Kpis";
import { layoutDots } from "../domain/matrix";
import { STAGE_ORDER, stageColor } from "../domain/stage";
import { useApp } from "../store";

const QUADRANTS: [string, string][] = [
  ["tl", "Quick wins"],
  ["tr", "Major strategic projects"],
  ["bl", "Low benefit"],
  ["br", "Review critically"],
];

export function MatrixView() {
  const { all, visible } = useApp();
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const dots = layoutDots(visible);
  const notPlotted = visible.length - dots.length;
  const selected = visible.find((i) => i.id === selectedId) ?? null;
  const selectedDot = dots.find((d) => d.initiative.id === selectedId) ?? null;

  return (
    <>
      <div className="filter-row">
        <BusinessUnitChips all={all} />
        <StageChips all={all} />
      </div>
      <Kpis items={visible} />

      <div className="split">
        <section className="card matrix-card" aria-label="Effort versus potential">
          <div className="matrix-head">
            <div>
              <h2>Effort vs. potential</h2>
              <p className="muted">
                Each dot is one initiative; only initiatives with recorded effort are plotted. Potential is
                the estimated value in € per year (log scale, 1k € to 1 M €).
              </p>
            </div>
            <ul className="legend">
              {STAGE_ORDER.filter((s) => dots.some((d) => d.initiative.stage === s)).map((s) => (
                <li key={s}>
                  <span className="dot" style={{ background: stageColor(s) }} />
                  {s}
                </li>
              ))}
            </ul>
          </div>

          <div className="plot-wrap">
            <span className="axis-y">Potential ≈ €/yr</span>
            <div className="plot-col">
              <div className="plot" data-testid="plot">
                <span className="mid-v" />
                <span className="mid-h" />
                {QUADRANTS.map(([pos, label]) => (
                  <span key={pos} className={`quad quad-${pos}`}>
                    {label}
                  </span>
                ))}
                {dots.map(({ initiative: i, x, y, dx, dy }) => (
                  <button
                    key={i.id}
                    type="button"
                    className={`pt${i.id === selectedId ? " sel" : ""}`}
                    aria-label={`${i.name}, ${i.stage}`}
                    aria-pressed={i.id === selectedId}
                    title={i.name}
                    onClick={() => setSelectedId(i.id === selectedId ? null : i.id)}
                    style={
                      {
                        left: `calc(${x}% + ${dx}px)`,
                        top: `calc(${y}% + ${dy}px)`,
                        background: stageColor(i.stage),
                      } as CSSProperties
                    }
                  />
                ))}
                {selectedDot && (
                  <span
                    className="pt-label"
                    style={{
                      left: `calc(${selectedDot.x}% + ${selectedDot.dx + 12}px)`,
                      top: `calc(${selectedDot.y}% + ${selectedDot.dy}px)`,
                    }}
                  >
                    {selectedDot.initiative.name}
                  </span>
                )}
              </div>
              <div className="axis-x">
                <span>low</span>
                <span>Effort</span>
                <span>high</span>
              </div>
            </div>
          </div>
          {notPlotted > 0 && (
            <p className="note" role="status">
              {notPlotted} of {visible.length} initiatives are not plotted because their effort is
              missing in the source. They are visible in the list and board.
            </p>
          )}
        </section>

        <aside className="card side-panel" aria-label="Details">
          {selected ? (
            <DetailBody initiative={selected} />
          ) : (
            <p className="muted">Click a dot in the matrix to see the initiative's details.</p>
          )}
        </aside>
      </div>

      <FlagshipWidget />
    </>
  );
}
