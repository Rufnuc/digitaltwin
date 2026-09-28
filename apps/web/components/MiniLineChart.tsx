"use client";

export interface LineSeries {
  label: string;
  color: string;
  points: number[]; // one value per x position
}

/** A compact multi-series line chart (SVG, no deps). Themed via CSS variables;
 * all series share one y-scale. Labels are month keys like "2026-03". */
export function MiniLineChart({
  series,
  xLabels,
  height = 150,
  formatValue = (n) => String(Math.round(n)),
}: {
  series: LineSeries[];
  xLabels: string[];
  height?: number;
  formatValue?: (n: number) => string;
}) {
  const n = xLabels.length;
  const w = 640;
  const h = height;
  const padX = 8;
  const padTop = 12;
  const padBottom = 18;
  const maxY = Math.max(1, ...series.flatMap((s) => s.points));
  const px = (i: number) => padX + (n <= 1 ? 0 : (i / (n - 1)) * (w - padX * 2));
  const py = (v: number) => padTop + (1 - v / maxY) * (h - padTop - padBottom);

  const shortMonth = (label: string) => {
    const m = /^(\d{4})-(\d{2})$/.exec(label);
    if (!m) return label;
    return new Date(Number(m[1]), Number(m[2]) - 1, 1).toLocaleDateString("en-NG", { month: "short" });
  };

  return (
    <div>
      {series.length > 1 && (
        <div className="mb-1 flex flex-wrap gap-3 text-[11px]">
          {series.map((s) => (
            <span key={s.label} className="flex items-center gap-1 text-muted">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
      )}
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" role="img"
        aria-label={series.map((s) => s.label).join(", ")}>
        {/* horizontal gridlines */}
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1={padX} x2={w - padX} y1={py(maxY * f)} y2={py(maxY * f)}
            stroke="var(--line)" strokeWidth={0.5} opacity={0.5} />
        ))}
        <line x1={padX} x2={w - padX} y1={py(0)} y2={py(0)} stroke="var(--line)" />
        {series.map((s) => {
          const path = s.points
            .map((v, i) => `${i === 0 ? "M" : "L"}${px(i).toFixed(1)},${py(v).toFixed(1)}`)
            .join(" ");
          return (
            <g key={s.label}>
              <path d={path} fill="none" stroke={s.color} strokeWidth={1.75}
                strokeLinejoin="round" strokeLinecap="round" />
              {s.points.map((v, i) => (
                <circle key={i} cx={px(i)} cy={py(v)} r={2} fill={s.color}>
                  <title>{`${xLabels[i]} · ${s.label}: ${formatValue(v)}`}</title>
                </circle>
              ))}
            </g>
          );
        })}
        <text x={padX} y={10} fontSize={10} className="fill-muted">max {formatValue(maxY)}</text>
        {/* sparse x labels */}
        {xLabels.map((lab, i) =>
          i % 2 === 0 || n <= 6 ? (
            <text key={i} x={px(i)} y={h - 4} fontSize={9} textAnchor="middle" className="fill-muted">
              {shortMonth(lab)}
            </text>
          ) : null,
        )}
      </svg>
    </div>
  );
}
