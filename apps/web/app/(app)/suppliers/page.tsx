"use client";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column, type FilterSpec, type FormField } from "@/components/DataTable";
import { api, type SupplierTrace } from "@/lib/api";

type Row = Record<string, unknown>;

const formFields: FormField[] = [
  { key: "code", label: "Code", required: true, placeholder: "SUP-001" },
  { key: "name", label: "Name", required: true },
  { key: "location", label: "Location", placeholder: "Import — China / Lagos" },
  { key: "currency", label: "Currency", placeholder: "NGN / USD / CNY" },
  { key: "payment_terms", label: "Payment terms" },
  { key: "lead_time_days", label: "Lead time (days)", type: "number" },
  {
    key: "status",
    label: "Status",
    type: "select",
    options: ["ACTIVE", "INACTIVE", "ARCHIVED"].map((v) => ({ value: v, label: v })),
  },
];
const columns: Column<Row>[] = [
  { key: "code", header: "Code", sortable: true },
  { key: "name", header: "Name", sortable: true },
  { key: "location", header: "Location", sortable: true },
  { key: "currency", header: "Currency", sortable: true },
  { key: "lead_time_days", header: "Lead (days)", sortable: true },
  { key: "reliability_score", header: "Reliability", sortable: true },
];

const filters: FilterSpec[] = [
  {
    key: "status",
    label: "Status",
    options: ["ACTIVE", "INACTIVE", "ARCHIVED"].map((v) => ({ value: v, label: v })),
  },
];

export default function SuppliersPage() {
  return (
    <div>
      <PageHeader
        title="Suppliers"
        subtitle="Supplier records and reliability. Click a supplier for its products, shipments and payments."
      />
      <ResourceTable<Row>
        resource="suppliers"
        columns={columns}
        filters={filters}
        formFields={formFields}
        entityLabel="supplier"
        viewable
        renderExtra={(row) => <SupplierTraceSection supplierId={Number(row.id)} />}
      />
    </div>
  );
}

const naira = (n: number | null | undefined) =>
  n == null ? "—" : "₦" + Math.round(n).toLocaleString("en-NG");
const day = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("en-NG", { dateStyle: "medium" }) : "—";
const stamp = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("en-NG", { dateStyle: "medium", timeStyle: "short" }) : "—";

type TraceTab = "products" | "shipments" | "payments";

function SupplierTraceSection({ supplierId }: { supplierId: number }) {
  const [data, setData] = useState<SupplierTrace | null>(null);
  const [tab, setTab] = useState<TraceTab>("products");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .supplierTrace(supplierId)
      .then((r) => alive && setData(r))
      .catch((e) => alive && setError(e instanceof Error ? e.message : "Could not load supplier"));
    return () => {
      alive = false;
    };
  }, [supplierId]);

  if (error) return <div className="border-t border-line pt-3 text-xs text-red-700">{error}</div>;
  if (!data) return <div className="border-t border-line pt-3 text-xs text-muted">Loading…</div>;

  return (
    <div className="border-t border-line pt-3">
      <div className="mb-3 grid grid-cols-3 gap-2 text-center">
        <Stat label="We owe" value={naira(data.we_owe)} />
        <Stat label="Products" value={String(data.products.length)} />
        <Stat label="Warehouses" value={String(data.warehouses.length)} />
      </div>

      <div className="mb-2 flex gap-1.5">
        {([
          ["products", `Products (${data.products.length})`],
          ["shipments", `Shipments (${data.shipments.length})`],
          ["payments", `Payments (${data.payments.length})`],
        ] as [TraceTab, string][]).map(([t, label]) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded border px-2 py-1 text-xs ${
              tab === t ? "border-ink bg-ink text-paper" : "border-line hover:bg-wash"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="max-h-72 space-y-1 overflow-y-auto">
        {tab === "products" &&
          (data.products.length === 0 ? (
            <Empty>No products received from this supplier yet.</Empty>
          ) : (
            data.products.map((p) => (
              <Line key={p.product_id}>
                <span className="min-w-0 flex-1 truncate">
                  <span className="font-medium">{p.product_name ?? "—"}</span>
                  {p.product_code ? <span className="text-muted"> · {p.product_code}</span> : null}
                </span>
                <span className="shrink-0 text-right text-muted">
                  {p.total_received.toLocaleString("en-NG")} units · {day(p.last_received)}
                </span>
              </Line>
            ))
          ))}

        {tab === "shipments" &&
          (data.shipments.length === 0 ? (
            <Empty>No shipments recorded.</Empty>
          ) : (
            data.shipments.map((s, i) => (
              <Line key={i}>
                <span className="min-w-0 flex-1">
                  <span className="font-medium">{s.product ?? "—"}</span>
                  <span className="block text-muted">
                    {day(s.received_date)}
                    {s.warehouse ? ` · ${s.warehouse}` : ""}
                    {s.shipment_ref ? ` · ${s.shipment_ref}` : ""}
                    {s.vessel_mmsi ? ` · vessel ${s.vessel_mmsi}` : ""}
                  </span>
                </span>
                <span className="shrink-0 text-right">
                  <span className="block">{s.quantity.toLocaleString("en-NG")} units</span>
                  <span className="block text-muted">@ {naira(s.unit_cost)}</span>
                </span>
              </Line>
            ))
          ))}

        {tab === "payments" &&
          (data.payments.length === 0 ? (
            <Empty>No payments recorded.</Empty>
          ) : (
            data.payments.map((p, i) => (
              <Line key={i}>
                <span className="min-w-0 flex-1">
                  <span className="font-medium">{naira(p.amount)}</span>
                  {p.method ? <span className="text-muted"> · {p.method}</span> : null}
                  <span className="block text-muted">
                    {stamp(p.paid_at)}
                    {p.reference ? ` · ${p.reference}` : ""}
                  </span>
                  {(p.from_name || p.to_name || p.txid) && (
                    <span className="block text-muted">
                      {p.from_name ? `${p.from_name}` : ""}
                      {p.from_account ? ` (${p.from_account})` : ""}
                      {p.to_name ? ` → ${p.to_name}` : ""}
                      {p.to_account ? ` (${p.to_account})` : ""}
                      {p.txid ? ` · txid ${p.txid}` : ""}
                    </span>
                  )}
                </span>
              </Line>
            ))
          ))}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-line p-2">
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div className="text-sm font-semibold">{value}</div>
    </div>
  );
}

function Line({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded border border-line px-2 py-1.5 text-xs">{children}</div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="text-xs text-muted">{children}</div>;
}
