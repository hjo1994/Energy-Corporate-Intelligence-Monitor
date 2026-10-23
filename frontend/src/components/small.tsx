import type { CSSProperties, ReactNode } from "react";
import type { Initiative } from "../api/types";
import { formatEur, formatScore, initials, scoreBars, valueFraction } from "../domain/format";
import { stageColor } from "../domain/stage";

type WithColor = CSSProperties & { "--c"?: string };

export function StageBadge({ stage }: { stage: string }) {
  return (
    <span className="badge" style={{ "--c": stageColor(stage) } as WithColor}>
      <span className="dot" />
      {stage}
    </span>
  );
}

const RISK_COLOR = ["#2f6b3a", "#6b8f3a", "#b9792e", "#a8483e", "#6e1f1a"];

/** Risk level 1-5 of the Rahmenbetriebsvereinbarung KI (an estimate, not a formal classification). */
export function RiskBadge({ risk }: { risk: Initiative["risk_classification"] }) {
  if (!risk) return <span className="missing">not classified</span>;
  return (
    <span className="badge" title={`${risk.name} (estimated)`} style={{ "--c": RISK_COLOR[risk.id - 1] ?? "#888" } as WithColor}>
      {risk.id} · {risk.name}
    </span>
  );
}

export function Avatar({ name, size = 26 }: { name: string; size?: number }) {
  return (
    <span
      className="avatar"
      aria-hidden="true"
      style={{ width: size, height: size, fontSize: Math.round(size * 0.38) }}
    >
      {initials(name)}
    </span>
  );
}

/** 5 bars for the 1–10 effort score; a missing score is shown as such, not as zero. */
export function EffortMeter({ score }: { score: number | null }) {
  if (score === null) return <span className="missing">not recorded</span>;
  const on = scoreBars(score);
  return (
    <span className="effort" title={`Effort ${formatScore(score)} of 10`}>
      <span className="effort-seg" aria-hidden="true">
        {[1, 2, 3, 4, 5].map((n) => (
          <span key={n} className={n <= on ? "on" : ""} style={{ height: 6 + n * 3 }} />
        ))}
      </span>
      <span className="mono">{formatScore(score)}</span>
    </span>
  );
}

/** Estimated potential in EUR per year; the bar uses a log scale (1k–1M €). */
export function ValueMeter({ eur }: { eur: number | null }) {
  if (eur === null) return <span className="missing">not estimated</span>;
  return (
    <span className="value-meter" title={`Potential ${formatEur(eur)} per year (estimate)`}>
      <span className="mono">{formatEur(eur)}</span>
      <span className="track" aria-hidden="true">
        <span style={{ width: `${valueFraction(eur) * 100}%` }} />
      </span>
    </span>
  );
}

export function OwnerCell({ initiative }: { initiative: Initiative }) {
  const owner = initiative.owner;
  if (!owner) return <span className="missing">no owner</span>;
  return (
    <span className="owner-cell">
      <Avatar name={owner.name} />
      <span>
        <span className="owner-name">{owner.name}</span>
        <span className="owner-dept">{owner.department ?? "–"}</span>
      </span>
    </span>
  );
}

export function Chip({
  children,
  active,
  onClick,
  dot,
}: {
  children: ReactNode;
  active?: boolean;
  onClick?: () => void;
  dot?: string;
}) {
  return (
    <button type="button" className={`chip${active ? " active" : ""}`} aria-pressed={active} onClick={onClick}>
      {dot && <span className="dot" style={{ background: dot }} />}
      {children}
    </button>
  );
}
