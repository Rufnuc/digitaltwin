"use client";
import { useCallback, useEffect, useState } from "react";
import { api, type TaxSummary } from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card } from "@/components/ui";

// A plain tax estimate — how much VAT and income tax you'd owe for a period,
// derived from your recorded sales, purchases and expenses. Not tax advice.

const naira = (n: number | null | undefined) =>
  n == null ? "—" : "₦" + Math.round(n).toLocaleString("en-NG");
const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

function isoDaysAgo(days: number) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export default function TaxPage() {
  const [tax, setTax] = useState<TaxSummary | null>(null);
  const [range, setRange] = useState<"365" | "90" | "30">("365");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (r: string) => {
    setLoading(true);
    setError(null);
    try {
      const q = `?start=${isoDaysAgo(Number(r))}&end=${new Date().toISOString().slice(0, 10)}`;
      setTax(await api.taxSummary(q));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load tax estimate");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(range);
  }, [load, range]);

  return (
    <div>
      <PageHeader
        title="Tax estimate"
        subtitle="Roughly what you'd owe — VAT and company income tax — from your recorded sales, purchases and expenses."
      />

      <div className="mb-4 flex items-center gap-2">
        {(["365", "90", "30"] as const).map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            className={`rounded border px-3 py-1.5 text-sm ${
              range === r ? "border-ink bg-ink text-paper" : "border-line hover:bg-wash"
            }`}
          >
            {r === "365" ? "Last 12 months" : `Last ${r} days`}
          </button>
        ))}
        {loading && <span className="text-sm text-muted">Loading…</span>}
      </div>

      {error && <div className="mb-4 text-sm text-red-700">{error}</div>}

      {tax && (
        <>
          {/* Headline total */}
          <Card className="mb-4 border-ink/30 p-4">
            <div className="text-[11px] uppercase tracking-wide text-muted">
              Estimated tax for the period
            </div>
            <div className="text-2xl font-semibold">{naira(tax.total_estimated_tax)}</div>
            <div className="mt-1 text-xs text-muted">
              {tax.period.start} → {tax.period.end} · on revenue {naira(tax.revenue)}
            </div>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* VAT */}
            <Card className="p-4">
              <div className="mb-2 text-sm font-medium">VAT ({pct(tax.vat.rate)})</div>
              <Line label="VAT collected on sales (output)" value={naira(tax.vat.output_vat)} />
              <Line label="VAT paid on purchases (input)" value={`− ${naira(tax.vat.input_vat)}`} />
              <div className="mt-2 flex items-center justify-between border-t border-line pt-2 text-sm font-semibold">
                <span>VAT to remit</span>
                <span className={tax.vat.vat_payable >= 0 ? "text-red-600" : "text-green-600"}>
                  {naira(tax.vat.vat_payable)}
                </span>
              </div>
              {tax.vat.vat_payable < 0 && (
                <div className="mt-1 text-[11px] text-muted">Negative = you have a VAT credit.</div>
              )}
            </Card>

            {/* Income tax */}
            <Card className="p-4">
              <div className="mb-2 text-sm font-medium">Company income tax</div>
              <Line label="Revenue" value={naira(tax.revenue)} />
              <Line label="Cost of goods sold" value={`− ${naira(tax.income_tax.cost_of_goods_sold)}`} />
              <Line label="Operating expenses" value={`− ${naira(tax.income_tax.operating_expenses)}`} />
              <div className="mt-1 flex items-center justify-between border-t border-line pt-1 text-sm">
                <span className="font-medium">Taxable profit</span>
                <span className="font-medium">{naira(tax.income_tax.taxable_profit)}</span>
              </div>
              <div className="mt-2 text-xs text-muted">
                Rate {pct(tax.income_tax.cit_rate)} · {tax.income_tax.cit_band}
              </div>
              <div className="mt-1 flex items-center justify-between text-sm font-semibold">
                <span>Income tax</span>
                <span className="text-red-600">{naira(tax.income_tax.income_tax)}</span>
              </div>
            </Card>
          </div>

          <p className="mt-4 rounded border border-yellow-500/40 bg-yellow-500/10 p-3 text-xs text-yellow-700 dark:text-yellow-300">
            {tax.disclaimer}
          </p>
        </>
      )}
    </div>
  );
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-0.5 text-sm">
      <span className="text-muted">{label}</span>
      <span>{value}</span>
    </div>
  );
}
