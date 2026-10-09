import type { CSSProperties, ReactNode } from "react";
import type { Initiative } from "../api/types";
import { formatScore, initials, scoreBars } from "../domain/format";
import { statusColor } from "../domain/status";

type WithColor = CSSProperties & { "--c"?: string };

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className="badge" style={{ "--c": statusColor(status) } as WithColor}>
      <span className="dot" />
      {status}
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

export function ValueMeter({ score }: { score: number | null }) {
  if (score === null) return <span className="missing">not recorded</span>;

  return (
    <span className="value-meter" title={`Value ${formatScore(score)} of 10`}>
      <span className="mono">{formatScore(score)}</span>
      <span className="track" aria-hidden="true">
        <span style={{ width: `${Math.min(100, score * 10)}%` }} />
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