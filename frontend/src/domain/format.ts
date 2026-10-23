export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

export function formatScore(score: number | null): string {
  return score === null ? "–" : score.toFixed(1);
}

// 1–10 score -> 0–5 bars (a missing score has no bars at all).
export function scoreBars(score: number | null): number {
  if (score === null) return 0;
  return Math.min(5, Math.max(1, Math.ceil(score / 2)));
}

// Money values are estimates, so they are always shown rounded and marked with "≈".
export function formatEur(value: number | null): string {
  if (value === null) return "–";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `≈ ${(value / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)} M €`;
  if (abs >= 1_000) return `≈ ${Math.round(value / 1_000)}k €`;
  return `≈ ${Math.round(value)} €`;
}

// Potential values span about three orders of magnitude, so meters and the
// matrix use a log scale: 1k €/year -> 0, 1 M €/year -> 1 (clamped).
export const VALUE_SCALE_MIN_EUR = 1_000;
export const VALUE_SCALE_MAX_EUR = 1_000_000;
export function valueFraction(value: number): number {
  const f =
    (Math.log10(Math.max(value, 1)) - Math.log10(VALUE_SCALE_MIN_EUR)) /
    (Math.log10(VALUE_SCALE_MAX_EUR) - Math.log10(VALUE_SCALE_MIN_EUR));
  return Math.min(1, Math.max(0, f));
}

export const formatFactor = (f: number | null): string => (f === null ? "–" : `× ${f.toFixed(2)}`);

// The source only knows quarters; the backend turns them into the first day
// of the quarter. Shown as "Q3 2026" — parsed from the string, no time zones.
export function formatQuarter(iso: string | null): string {
  if (!iso) return "–";
  const m = /^(\d{4})-(\d{2})/.exec(iso);
  if (!m) return "–";
  return `Q${Math.floor((Number(m[2]) - 1) / 3) + 1} ${m[1]}`;
}

// The Flagship catalog has a literal "-" entry meaning "no flagship".
export const NO_FLAGSHIP_LABEL = "No flagship";
export const flagshipLabel = (name: string): string => (name === "-" ? NO_FLAGSHIP_LABEL : name);
