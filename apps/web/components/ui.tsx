"use client";
import React from "react";

// Provenance badge — the visual expression of the platform's core rule that
// every value declares its epistemic status (REAL / DEMO / MODEL_OUTPUT / ...).
const ORIGIN_STYLES: Record<string, string> = {
  REAL: "bg-ink text-paper",
  DEMO: "bg-yellow-200 text-ink border border-yellow-500",
  ESTIMATED: "bg-wash text-muted border border-line",
  MISSING: "bg-wash text-muted border border-dashed border-line",
  ASSUMPTION: "bg-wash text-ink border border-line",
  MODEL_OUTPUT: "bg-blue-50 text-blue-800 border border-blue-200",
  FORECAST: "bg-purple-50 text-purple-800 border border-purple-200",
  AI_INTERPRETATION: "bg-wash text-muted border border-line",
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
    <Card className="p-4">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </Card>
  );
}

export function DemoBanner() {
  return (
    <div className="mb-4 flex items-center gap-2 rounded-lg border border-yellow-500 bg-yellow-50 px-4 py-2 text-sm text-ink">
      <span className="font-mono text-xs font-bold">DEMO DATA</span>
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
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" role="img" aria-label="Revenue over time">
      <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke="#e5e7eb" />
      <path d={path} fill="none" stroke="#0a0a0a" strokeWidth={1.5} />
      {data.map((d, i) => (
        <circle key={i} cx={px(i)} cy={py(d.revenue)} r={2} fill="#0a0a0a" />
      ))}
      <text x={pad} y={14} className="fill-muted" fontSize={10}>
        max {Math.round(maxY).toLocaleString()}
      </text>
    </svg>
  );
}
