// Nigerian Naira (₦). en-NG renders the ₦ symbol.
export const money = (n: number | null | undefined) =>
  n == null
    ? "—"
    : n.toLocaleString("en-NG", { style: "currency", currency: "NGN", maximumFractionDigits: 0 });

export const money2 = (n: number | null | undefined) =>
  n == null ? "—" : n.toLocaleString("en-NG", { style: "currency", currency: "NGN" });

export const pct = (fraction: number | null | undefined) =>
  fraction == null ? "—" : `${(fraction * 100).toFixed(1)}%`;

export const num = (n: number | null | undefined) =>
  n == null ? "—" : n.toLocaleString();
