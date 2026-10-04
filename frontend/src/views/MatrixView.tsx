import { useState, type CSSProperties } from "react";
import { BusinessUnitChips, StatusChips } from "../components/FilterChips";
import { DetailBody } from "../components/DetailBody";
import { Kpis } from "../components/Kpis";
import { layoutDots } from "../domain/matrix";
import { STATUS_ORDER, statusColor } from "../domain/status";
import { useApp } from "../store";

const QUADRANTS: [string, string][] = [
  ["tl", "Quick Wins"],
  ["tr", "Strategische Großprojekte"],
  ["bl", "Geringer Nutzen"],
  ["br", "Kritisch prüfen"],
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
        <StatusChips all={all} />
      </div>
      <Kpis items={visible} />

      <div className="split">
        <section className="card matrix-card" aria-label="Aufwand gegen Mehrwert">
          <div className="matrix-head">
            <div>
              <h2>Aufwand vs. Mehrwert</h2>
              <p className="muted">
                Jeder Punkt eine Initiative; eingezeichnet werden nur Initiativen mit erfasstem Aufwand
                und Mehrwert.
              </p>
            </div>
            <ul className="legend">
              {STATUS_ORDER.filter((s) => dots.some((d) => d.initiative.status === s)).map((s) => (
                <li key={s}>
                  <span className="dot" style={{ background: statusColor(s) }} />
                  {s}
                </li>
              ))}
            </ul>
          </div>

          <div className="plot-wrap">
            <span className="axis-y">Mehrwert</span>
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
                    aria-label={`${i.name}, ${i.status}`}
                    aria-pressed={i.id === selectedId}
                    title={i.name}
                    onClick={() => setSelectedId(i.id === selectedId ? null : i.id)}
                    style={
                      {
                        left: `calc(${x}% + ${dx}px)`,
                        top: `calc(${y}% + ${dy}px)`,
                        background: statusColor(i.status),
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
                <span>gering</span>
                <span>Aufwand</span>
                <span>hoch</span>
              </div>
            </div>
          </div>
          {notPlotted > 0 && (
            <p className="note" role="status">
              {notPlotted} von {visible.length} Initiativen sind nicht eingezeichnet, weil Aufwand oder
              Mehrwert in der Quelle fehlt. Sie sind in Liste und Board sichtbar.
            </p>
          )}
        </section>

        <aside className="card side-panel" aria-label="Details">
          {selected ? (
            <DetailBody initiative={selected} />
          ) : (
            <p className="muted">Punkt in der Matrix anklicken, um Details zur Initiative zu sehen.</p>
          )}
        </aside>
      </div>
    </>
  );
}
