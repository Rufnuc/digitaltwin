"use client";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column, type FilterSpec, type FormField } from "@/components/DataTable";
import { api, type Purchase, type SupplierPaymentRow, type SupplierTrace } from "@/lib/api";
import { PurchaseDocuments } from "@/components/PurchaseDocuments";

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

// Show an amount in its own currency: ₦ for naira, otherwise a "USD 1,200" style code.
const money = (n: number | null | undefined, ccy?: string | null) => {
  if (n == null) return "—";
  const v = Math.round(n).toLocaleString("en-NG");
  return !ccy || ccy.toUpperCase() === "NGN" ? "₦" + v : `${ccy.toUpperCase()} ${v}`;
};
const CURRENCIES = ["NGN", "USD", "CNY", "EUR", "GBP", "AED"];
const day = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("en-NG", { dateStyle: "medium" }) : "—";
const stamp = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("en-NG", { dateStyle: "medium", timeStyle: "short" }) : "—";

type TraceTab = "statement" | "products" | "shipments" | "payments" | "slow";

function SupplierTraceSection({ supplierId }: { supplierId: number }) {
  const [data, setData] = useState<SupplierTrace | null>(null);
  const [tab, setTab] = useState<TraceTab>("statement");
  const [error, setError] = useState<string | null>(null);
  const [supplyId, setSupplyId] = useState<number | null>(null);

  const load = useCallback(() => {
    api
      .supplierTrace(supplierId)
      .then((r) => setData(r))
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load supplier"));
  }, [supplierId]);

  useEffect(() => { load(); }, [load]);

  if (error) return <div className="border-t border-line pt-3 text-xs text-red-700">{error}</div>;
  if (!data) return <div className="border-t border-line pt-3 text-xs text-muted">Loading…</div>;

  const notSold = data.slow_movers.filter((m) => m.sold === 0 && m.on_hand > 0).length;
  // Bought/sold figures per product (from the lot ledger) to draw the mini chart.
  const movement = new Map(data.slow_movers.map((m) => [m.product_id, m]));

  return (
    <div className="border-t border-line pt-3">
      <div className="mb-3 grid grid-cols-3 gap-2 text-center">
        <Stat label="We owe" value={money(data.we_owe, data.currency)} />
        <Stat label="Paid to date" value={money(data.total_paid, data.currency)} />
        <Stat label="Not selling" value={String(notSold)} />
      </div>

      <div className="mb-2 flex flex-wrap gap-1.5">
        {([
          ["statement", `Statement (${data.statement.length})`],
          ["products", `Products (${data.products.length})`],
          ["shipments", `Shipments (${groupShipments(data.shipments).length})`],
          ["payments", `Payments (${data.payments.length})`],
          ["slow", `Slow movers (${data.slow_movers.length})`],
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
        {tab === "statement" &&
          (data.statement.length === 0 ? (
            <Empty>No supplies from this supplier yet.</Empty>
          ) : (
            data.statement.map((s) => (
              <button key={s.id} onClick={() => setSupplyId(s.id)}
                className="flex w-full items-start gap-2 rounded border border-line px-2 py-1.5 text-left text-xs hover:bg-wash">
                <span className="min-w-0 flex-1">
                  <span className="font-medium">{s.reference}</span>
                  <span className="text-muted"> · {s.status} · open →</span>
                  <span className="block text-muted">
                    {day(s.purchase_date)} · total {money(s.total, s.currency)}
                  </span>
                </span>
                <span className="shrink-0 text-right">
                  <span className={`block font-medium ${s.balance > 0 ? "text-red-700 dark:text-red-300" : "text-green-700 dark:text-green-300"}`}>
                    {s.balance > 0 ? `owe ${money(s.balance, s.currency)}` : "Settled"}
                  </span>
                </span>
              </button>
            ))
          ))}

        {tab === "slow" &&
          (data.slow_movers.length === 0 ? (
            <Empty>Nothing supplied yet to rank.</Empty>
          ) : (
            data.slow_movers.map((m) => (
              <Line key={m.product_id}>
                <span className="min-w-0 flex-1 truncate">
                  <span className="font-medium">{m.product_name ?? "—"}</span>
                  {m.product_code ? <span className="text-muted"> · {m.product_code}</span> : null}
                </span>
                <span className="shrink-0 text-right text-muted">
                  <span className={m.sold === 0 && m.on_hand > 0 ? "text-red-700 dark:text-red-300 font-medium" : ""}>
                    sold {m.sold}
                  </span>
                  {" · "}on hand {m.on_hand} of {m.received}
                </span>
              </Line>
            ))
          ))}

        {tab === "products" &&
          (data.products.length === 0 ? (
            <Empty>No products received from this supplier yet.</Empty>
          ) : (
            data.products.map((p) => {
              const m = movement.get(p.product_id);
              const bought = m?.received ?? p.total_received;
              const sold = m?.sold ?? 0;
              return (
                <div key={p.product_id}
                  className="rounded border border-line px-2 py-1.5 text-xs">
                  <div className="mb-1 flex items-baseline gap-2">
                    <span className="min-w-0 flex-1 truncate font-medium">{p.product_name ?? "—"}</span>
                    <span className="shrink-0 text-muted">{day(p.last_received)}</span>
                  </div>
                  <BoughtSoldBar bought={bought} sold={sold} />
                </div>
              );
            })
          ))}

        {tab === "shipments" &&
          (data.shipments.length === 0 ? (
            <Empty>No shipments recorded.</Empty>
          ) : (
            groupShipments(data.shipments).map((g) => (
              <button key={g.key}
                onClick={() => g.purchase_id != null && setSupplyId(g.purchase_id)}
                className={`flex w-full items-start gap-2 rounded border border-line px-2 py-1.5 text-left text-xs ${
                  g.purchase_id != null ? "hover:bg-wash" : "cursor-default"
                }`}>
                <span className="min-w-0 flex-1">
                  <span className="font-medium">{g.label}</span>
                  {g.purchase_id != null && <span className="text-muted"> · open supply →</span>}
                  <span className="block text-muted">
                    {g.items} item{g.items === 1 ? "" : "s"} · {day(g.date)}
                    {g.warehouses.length ? ` · ${g.warehouses.join(", ")}` : ""}
                  </span>
                </span>
                <span className="shrink-0 text-right">
                  <span className="block">{g.units.toLocaleString("en-NG")} units</span>
                </span>
              </button>
            ))
          ))}

        {tab === "payments" &&
          (data.payments.length === 0 ? (
            <Empty>No payments recorded.</Empty>
          ) : (
            data.payments.map((p, i) => (
              <Line key={i}>
                <span className="min-w-0 flex-1">
                  <span className="font-medium">{money(p.amount, p.currency)}</span>
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

      {supplyId != null && (
        <SupplyGroupModal
          purchaseId={supplyId}
          defaultCurrency={data.currency ?? "NGN"}
          onClose={() => setSupplyId(null)}
          onChanged={load}
        />
      )}
    </div>
  );
}

// A small two-bar chart: how much of a product was bought (received) vs sold.
function BoughtSoldBar({ bought, sold }: { bought: number; sold: number }) {
  const scale = Math.max(bought, sold, 1);
  const pct = (n: number) => `${Math.round((n / scale) * 100)}%`;
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <span className="w-12 shrink-0 text-[10px] uppercase tracking-wide text-muted">Bought</span>
        <span className="h-2 flex-1 overflow-hidden rounded bg-wash">
          <span className="block h-full rounded bg-blue-500/70" style={{ width: pct(bought) }} />
        </span>
        <span className="w-10 shrink-0 text-right tabular-nums">{bought.toLocaleString("en-NG")}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="w-12 shrink-0 text-[10px] uppercase tracking-wide text-muted">Sold</span>
        <span className="h-2 flex-1 overflow-hidden rounded bg-wash">
          <span className="block h-full rounded bg-green-500/70" style={{ width: pct(sold) }} />
        </span>
        <span className="w-10 shrink-0 text-right tabular-nums">{sold.toLocaleString("en-NG")}</span>
      </div>
    </div>
  );
}

// Roll a supplier's stock lots up into the supply groups (purchases) they came in on,
// so the user opens one PR at a time to see its lines and attach shipping documents.
type ShipGroup = {
  key: string; purchase_id: number | null; label: string;
  items: number; units: number; date: string | null; warehouses: string[];
};
function groupShipments(shipments: SupplierTrace["shipments"]): ShipGroup[] {
  const map = new Map<string, ShipGroup>();
  for (const s of shipments) {
    const key = s.purchase_id != null ? `p${s.purchase_id}` : `lot${s.lot_code ?? Math.random()}`;
    let g = map.get(key);
    if (!g) {
      g = {
        key, purchase_id: s.purchase_id,
        label: s.purchase_ref ?? (s.purchase_id != null ? `Purchase #${s.purchase_id}` : (s.product ?? "Direct receipt")),
        items: 0, units: 0, date: s.received_date, warehouses: [],
      };
      map.set(key, g);
    }
    g.items += 1;
    g.units += s.quantity;
    if (s.received_date && (!g.date || s.received_date > g.date)) g.date = s.received_date;
    if (s.warehouse && !g.warehouses.includes(s.warehouse)) g.warehouses.push(s.warehouse);
  }
  return Array.from(map.values());
}

// A supply group opened as a full modal: the goods on that supply, the payments
// made against it (with an inline "add payment" form), and its shipping documents.
function SupplyGroupModal({ purchaseId, defaultCurrency, onClose, onChanged }: {
  purchaseId: number; defaultCurrency: string; onClose: () => void; onChanged: () => void;
}) {
  const [p, setP] = useState<Purchase | null>(null);
  const [payments, setPayments] = useState<SupplierPaymentRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    api.getPurchase(purchaseId)
      .then(setP)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load supply"));
    api.purchasePayments(purchaseId).then((r) => setPayments(r.items)).catch(() => setPayments([]));
  }, [purchaseId]);

  useEffect(() => { reload(); }, [reload]);

  const owed = p ? Math.max(0, (p.total || 0) - (p.amount_paid || 0)) : 0;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4"
      onMouseDown={onClose}>
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-line bg-paper p-4 shadow-xl"
        onMouseDown={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-lg font-semibold">{p?.reference ?? "Supply"}</h2>
          {p && <span className="text-xs text-muted">{p.status}</span>}
          <button onClick={onClose} className="ml-auto text-muted hover:text-ink">✕</button>
        </div>
        {error && <div className="text-sm text-red-700">{error}</div>}
        {!p && !error && <div className="text-sm text-muted">Loading…</div>}
        {p && (
          <>
            <div className="mb-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
              <span><span className="text-muted">Date:</span> {day(p.purchase_date)}</span>
              <span><span className="text-muted">Total:</span> {money(p.total, p.currency)}</span>
              <span><span className="text-muted">Outstanding:</span>{" "}
                <span className={owed > 0 ? "text-red-700 dark:text-red-300" : "text-green-700 dark:text-green-300"}>
                  {owed > 0 ? money(owed, p.currency) : "Settled"}
                </span>
              </span>
            </div>

            <h3 className="mb-1 text-sm font-semibold">Goods on this supply</h3>
            <div className="overflow-x-auto rounded border border-line">
              <table className="w-full text-sm">
                <thead className="border-b border-line text-left text-xs text-muted">
                  <tr><th className="px-2 py-1.5">Item</th><th className="px-2 py-1.5">Qty</th>
                  <th className="px-2 py-1.5">Unit cost</th></tr>
                </thead>
                <tbody>
                  {(p.lines ?? []).map((ln, i) => (
                    <tr key={i} className="border-t border-line">
                      <td className="px-2 py-1.5">{ln.product_name ?? ln.description ?? `#${ln.product_id}`}</td>
                      <td className="px-2 py-1.5">{ln.quantity}</td>
                      <td className="px-2 py-1.5">{money(ln.unit_cost, p.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4 border-t border-line pt-3">
              <h3 className="mb-2 text-sm font-semibold">Payments</h3>
              {payments.length > 0 ? (
                <div className="mb-2 space-y-1">
                  {payments.map((pay) => (
                    <PaymentRow key={pay.id} purchaseId={p.id} pay={pay} onChanged={onChanged} />
                  ))}
                </div>
              ) : (
                <div className="mb-2 text-xs text-muted">No payments recorded on this supply yet.</div>
              )}
              <AddPaymentForm
                purchaseId={p.id}
                defaultCurrency={p.currency || defaultCurrency}
                onPaid={() => { reload(); onChanged(); }}
              />
            </div>

            <div className="mt-4 border-t border-line pt-3">
              <h3 className="mb-2 text-sm font-semibold">Shipping documents</h3>
              <PurchaseDocuments purchaseId={p.id} onChanged={onChanged} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// Inline form to record a payment against a supply, with means of payment and
// optional bank/transfer detail. Foreign-currency payments are logged but do not
// net the ₦ balance (rates aren't tracked here).
function AddPaymentForm({ purchaseId, defaultCurrency, onPaid }: {
  purchaseId: number; defaultCurrency: string; onPaid: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState((defaultCurrency || "NGN").toUpperCase());
  const [method, setMethod] = useState("transfer");
  const [reference, setReference] = useState("");
  const [showBank, setShowBank] = useState(false);
  const [fromName, setFromName] = useState("");
  const [toName, setToName] = useState("");
  const [txid, setTxid] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const foreign = currency !== "NGN";
  const currencies = CURRENCIES.includes(currency) ? CURRENCIES : [currency, ...CURRENCIES];

  async function submit() {
    const amt = Number(amount);
    if (!amt || amt <= 0) { setErr("Enter a positive amount"); return; }
    setBusy(true); setErr(null);
    try {
      await api.recordSupplierPayment(purchaseId, {
        amount: amt, currency, method, reference,
        from_name: fromName || undefined, to_name: toName || undefined, txid: txid || undefined,
      });
      setAmount(""); setReference(""); setFromName(""); setToName(""); setTxid("");
      setOpen(false);
      onPaid();
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not record payment"); }
    finally { setBusy(false); }
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
        className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash">
        + Add payment
      </button>
    );
  }

  return (
    <div className="rounded border border-line p-3">
      <div className="mb-2 flex gap-2">
        <label className="block flex-1 text-xs">Amount
          <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)}
            placeholder="0"
            className="mt-1 w-full rounded border border-line bg-paper px-2 py-1.5 text-sm" />
        </label>
        <label className="block w-24 text-xs">Currency
          <select value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())}
            className="mt-1 w-full rounded border border-line bg-paper px-2 py-1.5 text-sm">
            {currencies.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
      </div>
      {foreign && (
        <div className="mb-2 rounded border border-yellow-500/40 bg-yellow-500/10 px-2 py-1 text-[11px] text-yellow-800 dark:text-yellow-200">
          Paying in {currency}: recorded for the trail, but it won’t reduce the ₦ balance shown above.
        </div>
      )}
      <label className="mb-2 block text-xs">Means of payment
        <select value={method} onChange={(e) => setMethod(e.target.value)}
          className="mt-1 w-full rounded border border-line bg-paper px-2 py-1.5 text-sm">
          {["transfer", "cash", "pos", "opay", "moniepoint", "cheque", "other"].map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </label>
      <label className="mb-2 block text-xs">Reference / receipt no.
        <input value={reference} onChange={(e) => setReference(e.target.value)}
          placeholder="bank/txn reference"
          className="mt-1 w-full rounded border border-line bg-paper px-2 py-1.5 text-sm" />
      </label>

      <button onClick={() => setShowBank((v) => !v)}
        className="mb-2 text-[11px] text-muted underline">
        {showBank ? "Hide" : "Add"} bank details
      </button>
      {showBank && (
        <div className="mb-2 space-y-2">
          <label className="block text-xs">Paid from (our account name)
            <input value={fromName} onChange={(e) => setFromName(e.target.value)}
              className="mt-1 w-full rounded border border-line bg-paper px-2 py-1.5 text-sm" />
          </label>
          <label className="block text-xs">Paid to (supplier account name)
            <input value={toName} onChange={(e) => setToName(e.target.value)}
              className="mt-1 w-full rounded border border-line bg-paper px-2 py-1.5 text-sm" />
          </label>
          <label className="block text-xs">Transaction ID
            <input value={txid} onChange={(e) => setTxid(e.target.value)}
              className="mt-1 w-full rounded border border-line bg-paper px-2 py-1.5 text-sm" />
          </label>
        </div>
      )}
      {err && <div className="mb-2 text-sm text-red-700">{err}</div>}
      <div className="flex gap-2">
        <button onClick={submit} disabled={busy}
          className="flex-1 rounded bg-ink px-3 py-2 text-sm font-medium text-paper disabled:opacity-40">
          {busy ? "Recording…" : "Record payment"}
        </button>
        <button onClick={() => setOpen(false)} disabled={busy}
          className="rounded border border-line px-3 py-2 text-sm hover:bg-wash">Cancel</button>
      </div>
    </div>
  );
}

// One payment on a supply, with a collapsible area to attach its receipts
// (the naira payment receipt and the FX-conversion confirmation).
function PaymentRow({ purchaseId, pay, onChanged }: {
  purchaseId: number; pay: SupplierPaymentRow; onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded border border-line px-2 py-1.5 text-xs">
      <div className="flex items-start gap-2">
        <span className="min-w-0 flex-1">
          <span className="font-medium">{money(pay.amount, pay.currency)}</span>
          {pay.method ? <span className="text-muted"> · {pay.method}</span> : null}
          <span className="block text-muted">
            {day(pay.paid_at)}{pay.reference ? ` · ${pay.reference}` : ""}
            {(pay.from_name || pay.to_name) ? ` · ${pay.from_name ?? ""}${pay.to_name ? ` → ${pay.to_name}` : ""}` : ""}
            {pay.txid ? ` · txid ${pay.txid}` : ""}
          </span>
        </span>
        <button onClick={() => setOpen((v) => !v)}
          className="shrink-0 rounded border border-line px-1.5 py-0.5 text-[11px] hover:bg-wash">
          {open ? "Hide receipts" : "Receipts"}
        </button>
      </div>
      {open && (
        <div className="mt-2 border-t border-line pt-2">
          <PurchaseDocuments purchaseId={purchaseId} paymentId={pay.id} onChanged={onChanged} />
        </div>
      )}
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
