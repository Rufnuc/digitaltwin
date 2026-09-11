"use client";
import { useEffect, useState } from "react";
import { api, type DataQuality } from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card, Kpi } from "@/components/ui";
import { num } from "@/lib/format";

const SEV_STYLE: Record<string, string> = {
  high: "bg-red-50 text-red-800 border-red-200",
  medium: "bg-yellow-50 text-yellow-800 border-yellow-300",
  low: "bg-wash text-muted border-line",
};

export default function DataQualityPage() {
  const [dq, setDq] = useState<DataQuality | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.dataQuality().then(setDq).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="text-sm text-red-700">Error: {error}</div>;
  if (!dq) return <div className="text-sm text-muted">Loading…</div>;

  return (
    <div>
      <PageHeader
        title="Data Quality"
        subtitle="Transparent checks over the dataset — problems are surfaced, never hidden or auto-corrected."
      />
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Kpi label="Quality score" value={`${dq.score}`} sub={`grade ${dq.grade}`} />
        <Kpi label="Invoices" value={num(dq.totals.invoices)} />
        <Kpi label="Invoice lines" value={num(dq.totals.invoice_lines)} />
        <Kpi label="Products" value={num(dq.totals.products)} />
      </div>

      <Card className="p-4">
        <div className="mb-3 text-sm font-medium">Issues</div>
        {dq.issues.length === 0 ? (
          <div className="rounded border border-green-200 bg-green-50 p-3 text-sm text-green-800">
            No data-quality issues detected. ✓
          </div>
        ) : (
          <ul className="space-y-2">
            {dq.issues.map((i) => (
              <li key={i.category} className="rounded border border-line p-3">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{i.description}</span>
                  <span
                    className={`rounded border px-1.5 py-0.5 text-[10px] font-mono uppercase ${
                      SEV_STYLE[i.severity] ?? SEV_STYLE.low
                    }`}
                  >
                    {i.severity}
                  </span>
                </div>
                <div className="mt-1 text-xs text-muted">
                  <span className="font-mono">{i.category}</span> · {i.count} record
                  {i.count === 1 ? "" : "s"}
                  {i.sample_ids.length > 0 && (
                    <> · sample ids: {i.sample_ids.slice(0, 8).join(", ")}</>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <p className="mt-3 text-xs text-muted">
        Score = 100 × (1 − weighted issue penalty ÷ records checked). High-severity checks
        (arithmetic errors, duplicates) weigh most.
      </p>
    </div>
  );
}
