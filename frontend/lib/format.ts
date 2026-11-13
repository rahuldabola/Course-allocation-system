export const pct = (fraction: number, digits = 0) => `${(fraction * 100).toFixed(digits)}%`;

export function ordinal(n: number): string {
  const suffix = n % 10 === 1 && n % 100 !== 11 ? "st" : n % 10 === 2 && n % 100 !== 12 ? "nd"
    : n % 10 === 3 && n % 100 !== 13 ? "rd" : "th";
  return `${n}${suffix}`;
}

/** Backend timestamps are naive UTC ("2026-09-22T10:00:00"); render them in local time. */
export function parseServerDate(value: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
}

export function formatDateTime(value: string): string {
  return parseServerDate(value).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function timeAgo(value: string): string {
  const seconds = Math.round((Date.now() - parseServerDate(value).getTime()) / 1000);
  if (seconds < 45) return "just now";
  const units: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, "minute"],
    [24, "hour"],
    [30, "day"],
    [12, "month"],
    [Infinity, "year"],
  ];
  let amount = seconds / 60;
  let unit: Intl.RelativeTimeFormatUnit = "minute";
  for (const [step, name] of units) {
    unit = name;
    if (Math.abs(amount) < step) break;
    amount /= step;
  }
  return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(
    -Math.round(amount),
    unit,
  );
}
