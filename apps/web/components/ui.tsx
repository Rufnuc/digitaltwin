"use client";
import React from "react";

// Provenance badge — the visual expression of the platform's core rule that
// every value declares its epistemic status (REAL / DEMO / MODEL_OUTPUT / ...).
// Uses translucent accent backgrounds + theme-aware text so it reads in both
// light and dark themes (a solid light chip would wash out in dark mode).
const ORIGIN_STYLES: Record<string, string> = {
  REAL: "bg-ink text-paper",
  DEMO: "bg-yellow-500/15 text-yellow-700 dark:text-yellow-300 border border-yellow-500/40",
  ESTIMATED: "bg-muted/10 text-muted border border-line",
  MISSING: "bg-muted/10 text-muted border border-dashed border-line",
  ASSUMPTION: "bg-muted/10 text-ink border border-line",
  MODEL_OUTPUT: "bg-blue-500/15 text-blue-700 dark:text-blue-300 border border-blue-500/30",
  FORECAST: "bg-purple-500/15 text-purple-700 dark:text-purple-300 border border-purple-500/30",
  AI_INTERPRETATION: "bg-muted/10 text-muted border border-line",
};

export function ProvenanceBadge({ origin }: { origin: string }) {
  const style = ORIGIN_STYLES[origin] ?? "bg-wash text-muted border border-line";
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-mono tracking-wide ${style}`}>
      {origin}
    </span>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`rounded-lg border border-line bg-paper ${className}`}>{children}</div>;
}

// A table that adapts to screen width: on tablet+ it renders a normal table; on
// phones each row becomes a stacked card (header → value pairs) so no column is
// pushed off-screen and hidden behind a horizontal scroll. Pass cells as
// ReactNodes so callers keep their own formatting/colours.
export function ResponsiveTable({
  headers,
  rows,
  empty = "No records.",
}: {
  headers: React.ReactNode[];
  rows: React.ReactNode[][];
  empty?: string;
}) {
  return (
    <>
      {/* Phones: one card per row. */}
      <div className="space-y-2 sm:hidden">
        {rows.length === 0 ? (
          <div className="rounded-lg border border-line px-3 py-6 text-sm text-muted">{empty}</div>
        ) : (
          rows.map((cells, i) => (
            <div key={i} className="rounded-lg border border-line bg-paper p-3">
              {cells.map((cell, j) => (
                <div key={j} className="flex items-start justify-between gap-3 py-0.5 text-sm">
                  <span className="shrink-0 text-xs uppercase tracking-wide text-muted">
                    {headers[j]}
                  </span>
                  <span className="min-w-0 break-words text-right tabular-nums">{cell}</span>
                </div>
              ))}
            </div>
          ))
        )}
      </div>

      {/* Tablet and up: the full table (scrolls only if genuinely wide). */}
      <div className="hidden overflow-x-auto rounded-lg border border-line sm:block">
        <table className="min-w-full text-sm">
          <thead className="bg-wash text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              {headers.map((h, j) => (
                <th key={j} className="px-3 py-2 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td className="px-3 py-6 text-muted" colSpan={headers.length}>
                  {empty}
                </td>
              </tr>
            ) : (
              rows.map((cells, i) => (
                <tr key={i} className="border-t border-line tabular-nums">
                  {cells.map((cell, j) => (
                    <td key={j} className="px-3 py-1.5">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function Kpi({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <Card className="min-w-0 p-4">
      <div className="truncate text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 break-words text-xl font-semibold leading-tight tabular-nums sm:text-2xl">
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </Card>
  );
}

export function DemoBanner() {
  return (
    <div className="mb-4 flex items-center gap-2 rounded-lg border border-yellow-500/50 bg-yellow-500/10 px-4 py-2 text-sm text-ink">
      <span className="font-mono text-xs font-bold text-yellow-700 dark:text-yellow-300">
        DEMO DATA
      </span>
      <span className="text-muted">
        This workspace contains synthetic demo data only — no real business records yet.
      </span>
    </div>
  );
}

// Tiny dependency-free monochrome line chart.
export function LineChart({
  data,
  height = 160,
}: {
  data: { period: string; revenue: number }[];
  height?: number;
}) {
  if (!data.length) return <div className="text-sm text-muted">No data.</div>;
  const w = 640;
  const h = height;
  const pad = 28;
  const xs = data.map((_, i) => i);
  const ys = data.map((d) => d.revenue);
  const maxY = Math.max(...ys, 1);
  const minX = 0;
  const maxX = Math.max(...xs, 1);
  const px = (i: number) => pad + ((i - minX) / (maxX - minX || 1)) * (w - pad * 2);
  const py = (v: number) => h - pad - (v / maxY) * (h - pad * 2);
  const path = data.map((d, i) => `${i === 0 ? "M" : "L"}${px(i).toFixed(1)},${py(d.revenue).toFixed(1)}`).join(" ");
  return (
    // stroke/fill use theme variables so the line stays visible in dark mode.
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full text-ink" role="img" aria-label="Revenue over time">
      <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke="var(--line)" />
      <path d={path} fill="none" stroke="var(--ink)" strokeWidth={1.5} />
      {data.map((d, i) => (
        <circle key={i} cx={px(i)} cy={py(d.revenue)} r={2} fill="var(--ink)" />
      ))}
      <text x={pad} y={14} className="fill-muted" fontSize={10}>
        max {Math.round(maxY).toLocaleString()}
      </text>
    </svg>
  );
}
