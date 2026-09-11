export const money = (n: number | null | undefined) =>
  n == null
    ? "—"
    : n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export const money2 = (n: number | null | undefined) =>
  n == null ? "—" : n.toLocaleString(undefined, { style: "currency", currency: "USD" });

export const pct = (fraction: number | null | undefined) =>
  fraction == null ? "—" : `${(fraction * 100).toFixed(1)}%`;

export const num = (n: number | null | undefined) =>
  n == null ? "—" : n.toLocaleString();
