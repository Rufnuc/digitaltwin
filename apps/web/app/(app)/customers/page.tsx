"use client";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column, type FilterSpec, type FormField } from "@/components/DataTable";
import { api, getRole, newIdempotencyKey, type CustomerAnalytics } from "@/lib/api";
import { money } from "@/lib/format";
import { isSalesgirl } from "@/lib/roles";
import { Modal } from "@/components/Modal";
import { MiniLineChart } from "@/components/MiniLineChart";

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
  const sg = isSalesgirl(getRole());
  // Front desk: no lifetime-revenue column (money), and the list stays hidden
  // until they search. They can add and edit, but not delete.
  const cols = sg ? columns.filter((c) => c.key !== "lifetime_revenue") : columns;
  return (
    <div>
      <PageHeader
        title="Customers"
        subtitle={sg
          ? "Search for a customer to see their invoices, or add a new one."
          : "Customer master records. Click a customer to see what they owe and their invoices."}
      />
      <ResourceTable<Row>
        resource="customers"
        columns={cols}
        filters={sg ? [] : filters}
        formFields={formFields}
        entityLabel="customer"
        writeAllow={["SALESGIRL"]}
        requireSearch={sg}
        viewable
        renderExtra={(row) => (
          <>
            {!sg && <CustomerInsightsButton customerId={Number(row.id)} name={String(row.name ?? "")} />}
            <CustomerReceivable customerId={Number(row.id)} />
          </>
        )}
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

const dayShort = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("en-NG", { dateStyle: "medium" }) : "—";

// A button in the customer's view drawer that opens a roomy insights popup.
function CustomerInsightsButton({ customerId, name }: { customerId: number; name: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-t border-line pt-3">
      <button onClick={() => setOpen(true)}
        className="w-full rounded border border-line px-3 py-2 text-sm font-medium hover:bg-wash">
        📊 Sales insights &amp; history
      </button>
      {open && <CustomerInsightsModal customerId={customerId} name={name} onClose={() => setOpen(false)} />}
    </div>
  );
}

// Sales charts + behaviour signals (returning, cadence, recency, top products)
// for one customer — all computed from their real invoices.
function CustomerInsightsModal({ customerId, name, onClose }: {
  customerId: number; name: string; onClose: () => void;
}) {
  const [data, setData] = useState<CustomerAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.customerAnalytics(customerId)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load insights"));
  }, [customerId]);

  return (
    <Modal title={`${name || "Customer"} · insights`} size="xl" onClose={onClose}>
      {error && <div className="text-sm text-red-700">{error}</div>}
      {!data && !error && <div className="text-sm text-muted">Loading…</div>}
      {data && data.orders === 0 && (
        <div className="text-sm text-muted">No sales yet — insights appear once this customer has invoices.</div>
      )}
      {data && data.orders > 0 && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 text-center sm:grid-cols-4">
            <Stat label="Lifetime sales" value={naira(data.revenue)} />
            <Stat label="Orders" value={String(data.orders)} />
            <Stat label="Avg order" value={naira(data.avg_order_value)} />
            <Stat label="Status" value={data.returning ? "Returning" : "One-off"}
              tone={data.returning ? "good" : "muted"} />
          </div>

          <div className="mb-4 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
            <span>First order {dayShort(data.first_order)}</span>
            <span>Last order {dayShort(data.last_order)}</span>
            {data.days_since_last != null && <span>{data.days_since_last}d since last</span>}
            {data.avg_days_between_orders != null && <span>~{data.avg_days_between_orders}d between orders</span>}
            <span>{data.orders_last_90d} in last 90 days</span>
          </div>

          <div className="mb-4 rounded-lg border border-line p-3">
            <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Sales — last 12 months</div>
            <MiniLineChart
              xLabels={data.monthly.map((m) => m.month)}
              formatValue={(v) => naira(v)}
              series={[{ label: "Revenue", color: "#2563eb", points: data.monthly.map((m) => m.revenue) }]}
            />
          </div>

          {data.top_products.length > 0 && (
            <div>
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Top products bought</div>
              <div className="space-y-1">
                {data.top_products.map((p) => (
                  <div key={p.product_id ?? p.name} className="flex items-center gap-2 rounded border border-line px-3 py-1.5 text-sm">
                    <span className="min-w-0 flex-1 truncate">
                      <span className="font-medium">{p.name ?? "—"}</span>
                      {p.code ? <span className="text-muted"> · {p.code}</span> : null}
                    </span>
                    <span className="shrink-0 text-right text-muted">
                      {Math.round(p.quantity).toLocaleString("en-NG")} units · {naira(p.revenue)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </Modal>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "good" | "muted" }) {
  return (
    <div className="rounded border border-line p-2">
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`text-sm font-semibold ${
        tone === "good" ? "text-green-700 dark:text-green-300" : ""
      }`}>{value}</div>
    </div>
  );
}

// The receivables section inside a customer's view modal: what they owe overall
// and each invoice's balance/status. Click an owing invoice to record a payment
// against it right here — no need to go back to the invoices section.
function CustomerReceivable({ customerId }: { customerId: number }) {
  const [invoices, setInvoices] = useState<CustInvoice[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paying, setPaying] = useState<CustInvoice | null>(null);

  const load = useCallback(() => {
    api
      .list<CustInvoice>("invoices", `?customer_id=${customerId}&limit=100&sort=invoice_date&sort_dir=desc`)
      .then((r) => setInvoices(r.items))
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load invoices"));
  }, [customerId]);

  useEffect(() => {
    load();
  }, [load]);

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
        <>
          <div className="max-h-56 space-y-1 overflow-y-auto">
            {invoices.map((i) => {
              const unpaid = i.payment_status !== "PAID";
              return (
                <div
                  key={i.id}
                  onClick={() => unpaid && setPaying(i)}
                  className={`flex items-center gap-2 rounded px-1 py-1 text-xs ${
                    unpaid ? "cursor-pointer hover:bg-wash" : ""
                  }`}
                  title={unpaid ? "Record a payment" : "Fully paid"}
                >
                  <span className="w-28 shrink-0 truncate font-mono">{i.invoice_number}</span>
                  <span className="w-20 shrink-0 text-muted">{i.invoice_date}</span>
                  <span className="flex-1 text-right">{naira(i.total)}</span>
                  <span className={`w-16 shrink-0 text-right ${STATUS_STYLE[i.payment_status] ?? ""}`}>
                    {i.payment_status === "PAID" ? "paid" : naira(i.balance)}
                  </span>
                </div>
              );
            })}
          </div>
          {owing > 0 && (
            <div className="mt-1 text-[11px] text-muted">Tap an owing invoice to record a payment.</div>
          )}
        </>
      )}
      {paying && (
        <InvoicePaymentModal
          invoice={paying}
          onClose={() => setPaying(null)}
          onDone={() => {
            setPaying(null);
            load();
          }}
        />
      )}
    </div>
  );
}

const METHODS = ["cash", "transfer", "pos", "opay", "moniepoint", "cheque", "other"];

function InvoicePaymentModal({
  invoice,
  onClose,
  onDone,
}: {
  invoice: CustInvoice;
  onClose: () => void;
  onDone: () => void;
}) {
  const [amount, setAmount] = useState(String(invoice.balance));
  const [method, setMethod] = useState("transfer");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [idemKey] = useState(() => newIdempotencyKey());

  async function submit() {
    const amt = Number(amount);
    if (!amt || amt <= 0) {
      setErr("Enter a positive amount");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api.recordPayment(invoice.id, { amount: amt, method, reference }, idemKey);
      onDone();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not record payment");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
      onMouseDown={onClose}
    >
      <div className="w-full max-w-sm" onMouseDown={(e) => e.stopPropagation()}>
        <div className="rounded-lg border border-line bg-paper p-4 shadow-xl">
          <div className="mb-1 text-sm font-medium">Record payment</div>
          <div className="mb-3 text-xs text-muted">
            {invoice.invoice_number} · balance {naira(invoice.balance)}
          </div>
          <label className="mb-2 block text-xs">
            Amount (₦)
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="mt-1 w-full rounded border border-line px-3 py-2 text-sm"
            />
          </label>
          <label className="mb-2 block text-xs">
            Method
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value)}
              className="mt-1 w-full rounded border border-line bg-paper px-3 py-2 text-sm"
            >
              {METHODS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <label className="mb-3 block text-xs">
            Reference (optional)
            <input
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              placeholder="bank/txn reference"
              className="mt-1 w-full rounded border border-line px-3 py-2 text-sm"
            />
          </label>
          {err && <div className="mb-2 text-xs text-red-700">{err}</div>}
          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash">
              Cancel
            </button>
            <button
              onClick={submit}
              disabled={busy}
              className="rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper disabled:opacity-40"
            >
              {busy ? "Saving…" : "Record"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
