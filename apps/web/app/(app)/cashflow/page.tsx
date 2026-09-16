"use client";
import { useCallback, useEffect, useState } from "react";
import { api, type CashFlow, type PayablesSummary } from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card } from "@/components/ui";

// The owner's daily glance: money in vs out recently, the net, and what's owed
// both ways (to us and by us) with the net position.

const naira = (n: number | null | undefined) =>
  n == null ? "—" : "₦" + Math.round(n).toLocaleString("en-NG");

export default function CashFlowPage() {
  const [cf, setCf] = useState<CashFlow | null>(null);
  const [pay, setPay] = useState<PayablesSummary | null>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (window: number) => {
    setLoading(true);
    setError(null);
    try {
      const [c, p] = await Promise.all([
        api.cashFlow(window),
        api.payablesSummary().catch(() => null),
      ]);
      setCf(c);
      setPay(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load cash flow");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(days);
  }, [load, days]);

  const netPositive = (cf?.net_cash_flow ?? 0) >= 0;

  return (
    <div>
      <PageHeader
        title="Cash Flow"
        subtitle="Money coming in vs going out, and what's owed both ways — the quickest read on your cash."
      />

      <div className="mb-4 flex items-center gap-2">
        {[7, 30, 90].map((d) => (
          <button
            key={d}
            onClick={() => setDays(d)}
            className={`rounded border px-3 py-1.5 text-sm ${
              days === d ? "border-ink bg-ink text-paper" : "border-line hover:bg-wash"
            }`}
          >
            Last {d} days
          </button>
        ))}
        {loading && <span className="text-sm text-muted">Loading…</span>}
      </div>

      {error && <div className="mb-4 text-sm text-red-700">{error}</div>}

      {/* In / Out / Net over the window */}
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Card className="p-4">
          <div className="text-[11px] text-muted">Money in (last {days}d)</div>
          <div className="text-lg font-semibold text-green-600">{naira(cf?.money_in)}</div>
          <div className="mt-1 text-[11px] text-muted">Payments from customers</div>
        </Card>
        <Card className="p-4">
          <div className="text-[11px] text-muted">Money out (last {days}d)</div>
          <div className="text-lg font-semibold text-red-600">{naira(cf?.money_out)}</div>
          <div className="mt-1 text-[11px] text-muted">
            Suppliers {naira(cf?.money_out_breakdown.supplier_payments)} · Expenses{" "}
            {naira(cf?.money_out_breakdown.expenses)}
          </div>
        </Card>
        <Card className={`p-4 ${netPositive ? "" : "border-red-500/40"}`}>
          <div className="text-[11px] text-muted">Net cash flow</div>
          <div className={`text-lg font-semibold ${netPositive ? "text-green-600" : "text-red-600"}`}>
            {naira(cf?.net_cash_flow)}
          </div>
          <div className="mt-1 text-[11px] text-muted">
            {netPositive ? "Collecting more than spending" : "Spending more than collecting"}
          </div>
        </Card>
      </div>

      {/* What's owed both ways */}
      <Card className="mb-4 p-4">
        <div className="mb-3 text-sm font-medium">What's owed</div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded border border-line p-3">
            <div className="text-[11px] text-muted">Owed to you (receivables)</div>
            <div className="text-base font-semibold text-green-700 dark:text-green-300">
              {naira(cf?.owed_to_us)}
            </div>
          </div>
          <div className="rounded border border-line p-3">
            <div className="text-[11px] text-muted">You owe suppliers (payables)</div>
            <div className="text-base font-semibold text-red-700 dark:text-red-300">
              {naira(cf?.we_owe)}
            </div>
          </div>
          <div className="rounded border border-line p-3">
            <div className="text-[11px] text-muted">Net position</div>
            <div className="text-base font-semibold">{naira(cf?.net_position)}</div>
            <div className="mt-1 text-[11px] text-muted">Owed to you minus what you owe</div>
          </div>
        </div>
      </Card>

      {/* Who you owe */}
      {pay && pay.creditors.length > 0 && (
        <Card className="p-4">
          <div className="mb-2 text-sm font-medium">Top suppliers you owe</div>
          <div className="space-y-1">
            {pay.creditors.slice(0, 8).map((c) => (
              <div
                key={`${c.supplier_id}-${c.supplier_name}`}
                className="flex items-center justify-between rounded px-2 py-1.5 text-sm"
              >
                <span className="min-w-0 flex-1 truncate">{c.supplier_name}</span>
                <span className="font-medium">{naira(c.owed)}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {cf && (
        <p className="mt-3 text-[11px] text-muted">{cf.note}</p>
      )}
    </div>
  );
}
