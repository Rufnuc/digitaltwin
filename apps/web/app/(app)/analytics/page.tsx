"use client";
import { useEffect, useState } from "react";
import {
  api,
  type CustomerIntel,
  type FinancialRow,
  type ProductIntel,
  type SupplierIntel,
} from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card, Kpi, LineChart, ProvenanceBadge } from "@/components/ui";
import { money, num, pct } from "@/lib/format";

type Tab = "financials" | "customers" | "products" | "suppliers";
const TABS: { id: Tab; label: string }[] = [
  { id: "financials", label: "Financials" },
  { id: "customers", label: "Customers" },
  { id: "products", label: "Products" },
  { id: "suppliers", label: "Suppliers" },
];

export default function AnalyticsPage() {
  const [tab, setTab] = useState<Tab>("financials");
  return (
    <div>
      <PageHeader
        title="Analytics"
        subtitle="Customer, product, supplier and financial intelligence — all computed from stored records."
      />
      <div className="mb-4 flex gap-1 border-b border-line">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              tab === t.id ? "border-ink font-medium" : "border-transparent text-muted"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "financials" && <Financials />}
      {tab === "customers" && <Customers />}
      {tab === "products" && <Products />}
      {tab === "suppliers" && <Suppliers />}
    </div>
  );
}

function useAsync<T>(fn: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fn().then(setData).catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return { data, error };
}

function Financials() {
  const { data, error } = useAsync<{ series: FinancialRow[] }>(() => api.financials());
  if (error) return <Err msg={error} />;
  if (!data) return <Loading />;
  const s = data.series;
  const last = s[s.length - 1];
  return (
    <div>
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4">
        <Kpi label="Latest month" value={last?.period ?? "—"} />
        <Kpi label="Revenue (mo)" value={money(last?.revenue)} />
        <Kpi label="Net profit (mo)" value={money(last?.net_profit)} sub={pct(last?.net_margin)} />
        <Kpi label="Gross margin (mo)" value={pct(last?.gross_margin)} />
      </div>
      <Card className="mb-4 p-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium">Net profit by month</span>
          <ProvenanceBadge origin="MODEL_OUTPUT" />
        </div>
        <LineChart data={s.map((r) => ({ period: r.period, revenue: r.net_profit }))} />
      </Card>
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="min-w-full text-sm">
          <thead className="bg-wash text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              {["Period", "Revenue", "COGS", "Gross", "Opex", "Net", "Net %"].map((h) => (
                <th key={h} className="px-3 py-2 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {s.map((r) => (
              <tr key={r.period} className="border-t border-line tabular-nums">
                <td className="px-3 py-1.5">{r.period}</td>
                <td className="px-3 py-1.5">{money(r.revenue)}</td>
                <td className="px-3 py-1.5">{money(r.cogs)}</td>
                <td className="px-3 py-1.5">{money(r.gross_profit)}</td>
                <td className="px-3 py-1.5">{money(r.operating_expenses)}</td>
                <td className={`px-3 py-1.5 ${r.net_profit < 0 ? "text-red-700" : ""}`}>
                  {money(r.net_profit)}
                </td>
                <td className="px-3 py-1.5">{pct(r.net_margin)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Customers() {
  const { data, error } = useAsync<CustomerIntel>(() => api.analyticsCustomers());
  if (error) return <Err msg={error} />;
  if (!data) return <Loading />;
  return (
    <div>
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4">
        <Kpi label="Customers w/ sales" value={num(data.summary.customers_with_sales)} />
        <Kpi label="At churn risk" value={num(data.summary.at_risk_count)} />
        <Kpi label="Top-1 rev. share" value={pct(data.summary.top1_revenue_share)} />
        <Kpi label="Top-5 rev. share" value={pct(data.summary.top5_revenue_share)} />
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <div className="mb-2 text-sm font-medium">Top customers by gross profit</div>
          <MiniTable
            head={["Customer", "Revenue", "Gross", "Orders"]}
            rows={data.top_by_profit.map((m) => [
              m.name,
              money(m.revenue),
              money(m.gross_profit),
              String(m.orders),
            ])}
          />
        </Card>
        <Card className="p-4">
          <div className="mb-2 text-sm font-medium">Churn-risk customers (evidence-based)</div>
          {data.at_risk.length === 0 ? (
            <div className="text-sm text-muted">None flagged.</div>
          ) : (
            <ul className="space-y-2 text-sm">
              {data.at_risk.map((m) => (
                <li key={m.customer_id} className="rounded border border-line p-2">
                  <div className="font-medium">{m.name}</div>
                  <div className="text-xs text-muted">{m.churn_reason}</div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

function Products() {
  const { data, error } = useAsync<ProductIntel>(() => api.analyticsProducts());
  if (error) return <Err msg={error} />;
  if (!data) return <Loading />;
  return (
    <div>
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4">
        <Kpi label="Products sold" value={num(data.summary.products_sold)} />
        <Kpi label="Dead stock lines" value={num(data.summary.dead_stock_count)} />
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <div className="mb-2 text-sm font-medium">Best sellers (revenue)</div>
          <MiniTable
            head={["Product", "Revenue", "Units"]}
            rows={data.best_sellers.map((p) => [p.name, money(p.revenue), num(p.units)])}
          />
        </Card>
        <Card className="p-4">
          <div className="mb-2 text-sm font-medium">Most profitable (margin)</div>
          <MiniTable
            head={["Product", "Margin", "Gross"]}
            rows={data.most_profitable.map((p) => [p.name, pct(p.gross_margin), money(p.gross_profit)])}
          />
        </Card>
      </div>
    </div>
  );
}

function Suppliers() {
  const { data, error } = useAsync<SupplierIntel>(() => api.analyticsSuppliers());
  if (error) return <Err msg={error} />;
  if (!data) return <Loading />;
  return (
    <div>
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4">
        <Kpi label="Suppliers" value={num(data.summary.supplier_count)} />
        <Kpi label="Total spend" value={money(data.summary.total_spend)} />
      </div>
      <Card className="p-4">
        <MiniTable
          head={["Supplier", "Products", "Spend", "Lead (d)", "Reliability"]}
          rows={data.suppliers.map((s) => [
            s.name,
            String(s.product_count),
            money(s.spend),
            s.lead_time_days == null ? "—" : String(s.lead_time_days),
            s.reliability_score == null ? "—" : String(s.reliability_score),
          ])}
        />
      </Card>
    </div>
  );
}

function MiniTable({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-muted">
          <tr>
            {head.map((h) => (
              <th key={h} className="px-2 py-1.5 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line tabular-nums">
              {r.map((c, j) => (
                <td key={j} className="px-2 py-1.5">
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const Loading = () => <div className="text-sm text-muted">Loading…</div>;
const Err = ({ msg }: { msg: string }) => <div className="text-sm text-red-700">Error: {msg}</div>;
