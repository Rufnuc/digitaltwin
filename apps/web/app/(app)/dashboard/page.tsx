"use client";
import { useEffect, useState } from "react";
import { api, type AlertItem, type DashboardSummary } from "@/lib/api";
import { money, num, pct } from "@/lib/format";
import { PageHeader } from "@/components/Shell";
import { Card, DemoBanner, Kpi, LineChart, ProvenanceBadge } from "@/components/ui";

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [series, setSeries] = useState<{ period: string; revenue: number }[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.dashboardSummary().then(setSummary).catch((e) => setError(e.message));
    api.revenueSeries().then((r) => setSeries(r.series)).catch(() => {});
    api.alerts().then((r) => setAlerts(r.items)).catch(() => {});
  }, []);

  if (error) return <div className="text-sm text-red-700">Error: {error}</div>;
  if (!summary) return <div className="text-sm text-muted">Loading…</div>;

  const k = summary.kpis;
  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Headline metrics computed from stored transactions (24 months)."
      />
      {summary.data_status.is_demo_only && <DemoBanner />}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Kpi label="Revenue" value={money(k.revenue)} sub="trailing period" />
        <Kpi label="Gross Profit" value={money(k.gross_profit)} sub={`margin ${pct(k.gross_margin)}`} />
        <Kpi
          label="Net Profit"
          value={money(k.net_profit)}
          sub={`net margin ${pct(k.net_margin)}`}
        />
        <Kpi label="Orders" value={num(k.orders)} sub={`${num(k.units_sold)} units`} />
        <Kpi label="Active Customers" value={num(k.active_customers)} />
        <Kpi label="COGS" value={money(k.cogs)} />
        <Kpi label="Operating Expenses" value={money(k.operating_expenses)} />
        <Kpi label="Inventory Value" value={money(k.inventory_value)} />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="p-4 lg:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-sm font-medium">Revenue over time</div>
            <ProvenanceBadge origin={summary.provenance} />
          </div>
          <LineChart data={series} />
        </Card>
        <Card className="p-4">
          <div className="mb-2 text-sm font-medium">Alerts</div>
          {alerts.length === 0 ? (
            <div className="text-sm text-muted">No active alerts.</div>
          ) : (
            <ul className="space-y-2">
              {alerts.map((a) => (
                <li key={a.id} className="rounded border border-line p-2 text-sm">
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

      <p className="mt-4 text-xs text-muted">
        All figures are model outputs computed from the underlying records — never invented.
        Insufficient data is reported as such rather than estimated silently.
      </p>
    </div>
  );
}
