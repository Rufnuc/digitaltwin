"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getRole, type AlertItem, type CashFlow, type DashboardSummary } from "@/lib/api";
import { money, num, pct } from "@/lib/format";
import { isSalesgirl } from "@/lib/roles";
import { PageHeader } from "@/components/Shell";
import { Card, DemoBanner, Kpi, LineChart, ProvenanceBadge } from "@/components/ui";

export default function DashboardPage() {
  const router = useRouter();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [series, setSeries] = useState<{ period: string; revenue: number }[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [cash, setCash] = useState<CashFlow | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.dashboardSummary().then(setSummary).catch((e) => setError(e.message));
    api.revenueSeries().then((r) => setSeries(r.series)).catch(() => {});
    api.alerts().then((r) => setAlerts(r.items)).catch(() => {});
    api.cashFlow(30).then(setCash).catch(() => {}); // MANAGER+; ignored if not permitted
  }, []);

  if (error) return <div className="text-sm text-red-700">Error: {error}</div>;
  if (!summary) return <div className="text-sm text-muted">Loading…</div>;

  const k = summary.kpis;
  const netPositive = (cash?.net_cash_flow ?? 0) >= 0;
  // Front desk sees operational counts only — never money in/out or totals.
  const sales = isSalesgirl(getRole());
  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Headline metrics computed from stored transactions. Tap a card to open the feature."
      />
      {summary.data_status.is_demo_only && <DemoBanner />}

      {/* Money row — links to the money features (hidden for the front desk) */}
      {cash && !sales && (
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Link href="/receivables">
            <Kpi label="Owed to you" value={money(cash.owed_to_us)} sub="receivables →" />
          </Link>
          <Link href="/cashflow">
            <Kpi label="You owe" value={money(cash.we_owe)} sub="payables →" />
          </Link>
          <Link href="/cashflow">
            <Kpi
              label="Net cash flow (30d)"
              value={money(cash.net_cash_flow)}
              sub={netPositive ? "in > out →" : "out > in →"}
            />
          </Link>
          <Link href="/cashflow">
            <Kpi label="Net position" value={money(cash.net_position)} sub="cash flow →" />
          </Link>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4">
        {!sales && <Link href="/analytics"><Kpi label="Revenue" value={money(k.revenue)} sub="trailing period" /></Link>}
        {!sales && <Link href="/analytics"><Kpi label="Gross Profit" value={money(k.gross_profit)} sub={`margin ${pct(k.gross_margin)}`} /></Link>}
        {!sales && <Link href="/analytics"><Kpi label="Net Profit" value={money(k.net_profit)} sub={`net margin ${pct(k.net_margin)}`} /></Link>}
        <Link href="/invoices"><Kpi label="Orders" value={num(k.orders)} sub={`${num(k.units_sold)} units`} /></Link>
        <Link href="/customers"><Kpi label="Active Customers" value={num(k.active_customers)} /></Link>
        {!sales && <Link href="/analytics"><Kpi label="COGS" value={money(k.cogs)} /></Link>}
        {!sales && <Link href="/expenses"><Kpi label="Operating Expenses" value={money(k.operating_expenses)} /></Link>}
        {!sales && <Link href="/stock"><Kpi label="Inventory Value" value={money(k.inventory_value)} /></Link>}
      </div>

      {!sales && (
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="p-4 lg:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-sm font-medium">Revenue over time</div>
            <ProvenanceBadge origin={summary.provenance} />
          </div>
          <LineChart data={series} />
        </Card>
        <Card className="p-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-sm font-medium">Alerts</div>
            <Link href="/suggestions" className="text-xs text-muted underline decoration-dotted">
              Action list →
            </Link>
          </div>
          {alerts.length === 0 ? (
            <div className="text-sm text-muted">No active alerts.</div>
          ) : (
            <ul className="space-y-2">
              {alerts.map((a) => (
                <li
                  key={a.id}
                  onClick={() => router.push("/suggestions")}
                  className="cursor-pointer rounded border border-line p-2 text-sm hover:bg-wash"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{a.title}</span>
                    <ProvenanceBadge origin={a.data_origin} />
                  </div>
                  {a.body && <div className="mt-0.5 text-xs text-muted">{a.body}</div>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      )}

      <p className="mt-4 text-xs text-muted">
        All figures are model outputs computed from the underlying records — never invented.
        Insufficient data is reported as such rather than estimated silently.
      </p>
    </div>
  );
}
