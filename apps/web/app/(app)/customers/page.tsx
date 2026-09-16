"use client";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column, type FilterSpec, type FormField } from "@/components/DataTable";
import { api } from "@/lib/api";
import { money } from "@/lib/format";

const STATUS = ["ACTIVE", "INACTIVE", "PROSPECT", "ARCHIVED"];
const TYPES = ["RETAIL", "WHOLESALE", "TRADE", "OTHER"];

const formFields: FormField[] = [
  { key: "name", label: "Name", required: true },
  { key: "location", label: "Location" },
  { key: "contact_email", label: "Email" },
  { key: "contact_phone", label: "Phone" },
  { key: "customer_type", label: "Type", type: "select", options: TYPES.map((v) => ({ value: v, label: v })) },
  { key: "status", label: "Status", type: "select", options: STATUS.map((v) => ({ value: v, label: v })) },
  { key: "credit_limit", label: "Credit limit (₦)", type: "number" },
  { key: "payment_terms_days", label: "Payment terms (days)", type: "number" },
];

type Row = Record<string, unknown>;
const columns: Column<Row>[] = [
  { key: "code", header: "Code", sortable: true },
  { key: "name", header: "Name", sortable: true },
  { key: "location", header: "Location", sortable: true },
  { key: "customer_type", header: "Type", sortable: true },
  { key: "status", header: "Status", sortable: true },
  {
    key: "lifetime_revenue",
    header: "Lifetime Rev.",
    sortable: true,
    render: (r) => money(r.lifetime_revenue as number),
  },
];

const filters: FilterSpec[] = [
  {
    key: "status",
    label: "Status",
    options: ["ACTIVE", "INACTIVE", "PROSPECT", "ARCHIVED"].map((v) => ({ value: v, label: v })),
  },
  {
    key: "customer_type",
    label: "Type",
    options: ["RETAIL", "WHOLESALE", "TRADE", "OTHER"].map((v) => ({ value: v, label: v })),
  },
];

export default function CustomersPage() {
  return (
    <div>
      <PageHeader title="Customers" subtitle="Customer master records. Click a customer to see what they owe and their invoices." />
      <ResourceTable<Row>
        resource="customers"
        columns={columns}
        filters={filters}
        formFields={formFields}
        entityLabel="customer"
        viewable
        renderExtra={(row) => <CustomerReceivable customerId={Number(row.id)} />}
      />
    </div>
  );
}

const naira = (n: number | null | undefined) =>
  n == null ? "—" : "₦" + Math.round(n).toLocaleString("en-NG");

const STATUS_STYLE: Record<string, string> = {
  PAID: "text-green-700 dark:text-green-300",
  PARTIAL: "text-yellow-700 dark:text-yellow-300",
  UNPAID: "text-red-700 dark:text-red-300",
};

interface CustInvoice {
  id: number;
  invoice_number: string;
  invoice_date: string;
  total: number;
  balance: number;
  payment_status: string;
}

// The receivables section inside a customer's view modal: what they owe overall
// and each invoice's balance/status.
function CustomerReceivable({ customerId }: { customerId: number }) {
  const [invoices, setInvoices] = useState<CustInvoice[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .list<CustInvoice>("invoices", `?customer_id=${customerId}&limit=100&sort=invoice_date&sort_dir=desc`)
      .then((r) => alive && setInvoices(r.items))
      .catch((e) => alive && setError(e instanceof Error ? e.message : "Could not load invoices"));
    return () => {
      alive = false;
    };
  }, [customerId]);

  if (error) return <div className="text-xs text-red-700">{error}</div>;
  if (!invoices) return <div className="text-xs text-muted">Loading invoices…</div>;

  const owing = invoices
    .filter((i) => i.payment_status !== "PAID")
    .reduce((s, i) => s + (i.balance || 0), 0);

  return (
    <div className="rounded border border-line p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-medium">Owes now</span>
        <span className={`text-sm font-semibold ${owing > 0 ? "text-red-600" : "text-green-600"}`}>
          {naira(owing)}
        </span>
      </div>
      {invoices.length === 0 ? (
        <div className="text-xs text-muted">No invoices yet.</div>
      ) : (
        <div className="max-h-56 space-y-1 overflow-y-auto">
          {invoices.map((i) => (
            <div key={i.id} className="flex items-center gap-2 text-xs">
              <span className="w-28 shrink-0 truncate font-mono">{i.invoice_number}</span>
              <span className="w-20 shrink-0 text-muted">{i.invoice_date}</span>
              <span className="flex-1 text-right">{naira(i.total)}</span>
              <span className={`w-16 shrink-0 text-right ${STATUS_STYLE[i.payment_status] ?? ""}`}>
                {i.payment_status === "PAID" ? "paid" : naira(i.balance)}
              </span>
            </div>
          ))}
        </div>
      )}
      {owing > 0 && (
        <a href="/receivables" className="mt-2 inline-block text-xs text-ink underline decoration-dotted">
          Record a payment →
        </a>
      )}
    </div>
  );
}
