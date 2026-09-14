"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PageHeader } from "@/components/Shell";
import { Card } from "@/components/ui";
import { EntityForm, type FormField } from "@/components/EntityForm";
import { api, getRole } from "@/lib/api";
import { money2 } from "@/lib/format";
import { roleAtLeast } from "@/lib/roles";

interface Ref {
  id: number;
  name: string;
  code: string;
}
interface CustomerRef extends Ref {
  location?: string | null;
  customer_type?: string | null;
  contact_phone?: string | null;
}
interface Line {
  key: number;
  product_id: string;
  quantity: string;
  unit_price: string;
}

const todayIso = () => new Date().toISOString().slice(0, 10);

export default function SellPage() {
  const router = useRouter();
  const [customers, setCustomers] = useState<CustomerRef[]>([]);
  const [warehouses, setWarehouses] = useState<Ref[]>([]);
  const [products, setProducts] = useState<Ref[]>([]);
  const [suppliers, setSuppliers] = useState<Ref[]>([]);

  const [invoiceNumber, setInvoiceNumber] = useState(`INV-${Date.now().toString().slice(-6)}`);
  const [invoiceDate, setInvoiceDate] = useState(todayIso());
  const [customerId, setCustomerId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [lines, setLines] = useState<Line[]>([{ key: 1, product_id: "", quantity: "1", unit_price: "" }]);
  const [tax, setTax] = useState("0");
  const [discount, setDiscount] = useState("0");

  // available[productId][warehouseId] = qty on hand
  const [available, setAvailable] = useState<Record<number, Record<number, number>>>({});
  const [showReceive, setShowReceive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const canSell = roleAtLeast(getRole(), "STAFF");

  useEffect(() => {
    api.list<CustomerRef>("customers", "?limit=200").then((r) => setCustomers(r.items)).catch(() => {});
    api.list<Ref>("warehouses", "?limit=200").then((r) => setWarehouses(r.items)).catch(() => {});
    api.list<Ref>("products", "?limit=200").then((r) => setProducts(r.items)).catch(() => {});
    api.list<Ref>("suppliers", "?limit=200").then((r) => setSuppliers(r.items)).catch(() => {});
  }, []);

  const fetchAvail = useCallback(async (productId: number) => {
    try {
      const r = await api.productOnHand(productId);
      const map: Record<number, number> = {};
      for (const w of r.by_warehouse) map[w.warehouse_id] = w.on_hand;
      setAvailable((prev) => ({ ...prev, [productId]: map }));
    } catch {
      /* ignore */
    }
  }, []);

  const productName = (id: string) => products.find((p) => String(p.id) === id);
  const selectedCustomer = customers.find((c) => String(c.id) === customerId);
  const wid = Number(warehouseId) || 0;

  function availFor(productId: string): number | null {
    const pid = Number(productId);
    if (!pid || !wid) return null;
    return available[pid]?.[wid] ?? null;
  }

  function setLine(key: number, patch: Partial<Line>) {
    setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  }
  function addLine() {
    setLines((ls) => [...ls, { key: Date.now(), product_id: "", quantity: "1", unit_price: "" }]);
  }
  function removeLine(key: number) {
    setLines((ls) => (ls.length > 1 ? ls.filter((l) => l.key !== key) : ls));
  }

  const subtotal = lines.reduce(
    (s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_price) || 0),
    0,
  );
  const total = subtotal + (Number(tax) || 0) - (Number(discount) || 0);

  // Validation: every line needs a product + qty, and qty must be in stock.
  const problems: string[] = [];
  if (!warehouseId) problems.push("Choose a warehouse to sell from.");
  lines.forEach((l, i) => {
    if (!l.product_id) return; // empty rows ignored on submit
    const q = Number(l.quantity);
    if (!q || q <= 0) problems.push(`Line ${i + 1}: quantity must be positive.`);
    const avail = availFor(l.product_id);
    if (avail != null && q > avail)
      problems.push(`Line ${i + 1}: only ${avail} of ${productName(l.product_id)?.name} in stock.`);
  });
  const validLines = lines.filter((l) => l.product_id && Number(l.quantity) > 0);
  const canSubmit = canSell && warehouseId && validLines.length > 0 && problems.length === 0 && !busy;

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      const res = await api.invoiceSell({
        invoice_number: invoiceNumber,
        invoice_date: invoiceDate,
        warehouse_id: Number(warehouseId),
        customer_id: customerId ? Number(customerId) : null,
        currency: "NGN",
        tax: Number(tax) || 0,
        discount: Number(discount) || 0,
        lines: validLines.map((l) => ({
          product_id: Number(l.product_id),
          quantity: Number(l.quantity),
          unit_price: Number(l.unit_price) || 0,
        })),
      });
      const inv = res.invoice as { invoice_number?: string };
      setDone(`Sale recorded: ${inv.invoice_number}. Stock drawn from the warehouse and each unit traced to the buyer.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sale failed");
    } finally {
      setBusy(false);
    }
  }

  // Quick receive — for an item bought from another seller to resell.
  const receiveFields: FormField[] = [
    { key: "product_id", label: "Product", type: "select", required: true,
      options: products.map((p) => ({ value: String(p.id), label: `${p.code} — ${p.name}` })) },
    { key: "quantity", label: "Quantity bought", type: "number", required: true },
    { key: "unit_cost", label: "What you paid per unit (₦)", type: "number", step: "0.01", required: true },
    { key: "supplier_id", label: "Seller (if a saved supplier)", type: "select",
      options: suppliers.map((s) => ({ value: String(s.id), label: `${s.code} — ${s.name}` })) },
    { key: "shipment_ref", label: "Shipment / reference", placeholder: "receipt, B-L, or vessel" },
    { key: "note", label: "Seller / reference note", placeholder: "e.g. bought from Musa Auto, Ladipo",
      help: "Use this if the seller isn't a saved supplier." },
  ];

  if (done) {
    return (
      <div>
        <PageHeader title="New Sale" />
        <Card className="p-6">
          <div className="mb-3 rounded border border-green-500/30 bg-green-500/15 px-3 py-2 text-sm text-green-700 dark:text-green-300">
            ✓ {done}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => router.push("/invoices")}
              className="rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper"
            >
              View invoices
            </button>
            <button
              onClick={() => window.location.reload()}
              className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash"
            >
              New sale
            </button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="New Sale"
        subtitle="Bill a customer and draw the goods from a warehouse — stock decrements FIFO and every unit is traced to the buyer. Bought something from another seller to resell? Add it to stock first."
      />

      {!canSell && (
        <Card className="p-4 text-sm text-muted">You need STAFF access or higher to record a sale.</Card>
      )}

      {canSell && (
        <div className="space-y-4">
          <Card className="p-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Labelled label="Invoice number">
                <input value={invoiceNumber} onChange={(e) => setInvoiceNumber(e.target.value)} className={inp} />
              </Labelled>
              <Labelled label="Date">
                <input type="date" value={invoiceDate} onChange={(e) => setInvoiceDate(e.target.value)} className={inp} />
              </Labelled>
              <Labelled label="Customer">
                <select value={customerId} onChange={(e) => setCustomerId(e.target.value)} className={inp}>
                  <option value="">Walk-in / none</option>
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.code} — {c.name}
                    </option>
                  ))}
                </select>
              </Labelled>
              <Labelled label="Sell from warehouse">
                <select
                  value={warehouseId}
                  onChange={(e) => {
                    setWarehouseId(e.target.value);
                    lines.forEach((l) => l.product_id && fetchAvail(Number(l.product_id)));
                  }}
                  className={inp}
                >
                  <option value="">Choose…</option>
                  {warehouses.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.code} — {w.name}
                    </option>
                  ))}
                </select>
              </Labelled>
            </div>
            {selectedCustomer && (
              <div className="mt-2 text-[11px] text-muted">
                {selectedCustomer.customer_type ?? ""}
                {selectedCustomer.location ? ` · ${selectedCustomer.location}` : ""}
                {selectedCustomer.contact_phone ? ` · ${selectedCustomer.contact_phone}` : ""}
              </div>
            )}
          </Card>

          <Card className="p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-medium">Items</span>
              <button
                onClick={() => setShowReceive(true)}
                className="rounded border border-line px-2 py-1 text-xs hover:bg-wash"
              >
                + Item from another seller
              </button>
            </div>

            <div className="space-y-2">
              {lines.map((l, i) => {
                const avail = availFor(l.product_id);
                const q = Number(l.quantity) || 0;
                const short = avail != null && q > avail;
                return (
                  <div key={l.key} className="grid grid-cols-12 items-center gap-2">
                    <select
                      value={l.product_id}
                      onChange={(e) => {
                        const pid = e.target.value;
                        const prod = products.find((p) => String(p.id) === pid);
                        setLine(l.key, { product_id: pid });
                        if (pid) fetchAvail(Number(pid));
                        // Prefill price from the product's selling price if empty.
                        if (prod && !l.unit_price) {
                          const sp = (prod as unknown as { selling_price?: number }).selling_price;
                          if (sp) setLine(l.key, { product_id: pid, unit_price: String(sp) });
                        }
                      }}
                      className={`col-span-12 sm:col-span-5 ${inp}`}
                    >
                      <option value="">Product…</option>
                      {products.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.code} — {p.name}
                        </option>
                      ))}
                    </select>
                    <input
                      type="number"
                      min="1"
                      value={l.quantity}
                      onChange={(e) => setLine(l.key, { quantity: e.target.value })}
                      placeholder="Qty"
                      className={`col-span-3 sm:col-span-2 ${inp} ${short ? "border-red-500" : ""}`}
                    />
                    <input
                      type="number"
                      step="0.01"
                      value={l.unit_price}
                      onChange={(e) => setLine(l.key, { unit_price: e.target.value })}
                      placeholder="Unit ₦"
                      className={`col-span-4 sm:col-span-2 ${inp}`}
                    />
                    <div className="col-span-4 text-right text-xs tabular-nums text-muted sm:col-span-2">
                      {l.product_id ? (avail != null ? `${avail} in stock` : "—") : ""}
                    </div>
                    <button
                      onClick={() => removeLine(l.key)}
                      aria-label="Remove line"
                      className="col-span-1 text-muted hover:text-red-700"
                    >
                      ✕
                    </button>
                    {short && (
                      <div className="col-span-12 text-[11px] text-red-700">
                        Line {i + 1}: only {avail} in stock — receive more or reduce the quantity.
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <button onClick={addLine} className="mt-2 text-xs text-muted underline decoration-dotted">
              + Add line
            </button>
          </Card>

          <Card className="p-4">
            <div className="grid grid-cols-2 gap-3 sm:max-w-sm">
              <Labelled label="Tax (₦)">
                <input type="number" step="0.01" value={tax} onChange={(e) => setTax(e.target.value)} className={inp} />
              </Labelled>
              <Labelled label="Discount (₦)">
                <input type="number" step="0.01" value={discount} onChange={(e) => setDiscount(e.target.value)} className={inp} />
              </Labelled>
            </div>
            <div className="mt-3 space-y-1 text-sm">
              <Row label="Subtotal" value={money2(subtotal)} />
              <Row label="Tax" value={money2(Number(tax) || 0)} />
              <Row label="Discount" value={`- ${money2(Number(discount) || 0)}`} />
              <div className="flex justify-between border-t border-line pt-1 text-base font-semibold">
                <span>Total</span>
                <span className="tabular-nums">{money2(total)}</span>
              </div>
            </div>
          </Card>

          {problems.length > 0 && (
            <div className="rounded border border-yellow-500/40 bg-yellow-500/10 p-2 text-xs text-yellow-700 dark:text-yellow-300">
              {problems.map((p, i) => (
                <div key={i}>• {p}</div>
              ))}
            </div>
          )}
          {error && <div className="text-sm text-red-700">Error: {error}</div>}

          <div className="sticky bottom-0 flex items-center justify-between gap-3 bg-wash py-2">
            <span className="text-sm text-muted">
              {validLines.length} item{validLines.length === 1 ? "" : "s"} · {money2(total)}
            </span>
            <button
              onClick={submit}
              disabled={!canSubmit}
              className="rounded bg-ink px-4 py-2 text-sm font-medium text-paper disabled:opacity-40"
            >
              {busy ? "Recording…" : "Record sale & draw stock"}
            </button>
          </div>
        </div>
      )}

      {showReceive && (
        <EntityForm
          title="Add stock from another seller"
          submitLabel="Add to stock"
          fields={receiveFields}
          onClose={() => setShowReceive(false)}
          onSubmit={async (v) => {
            if (!warehouseId) throw new Error("Choose a warehouse first.");
            const body: Record<string, unknown> = {
              product_id: Number(v.product_id),
              warehouse_id: Number(warehouseId),
              quantity: Number(v.quantity),
              unit_cost: v.unit_cost != null ? Number(v.unit_cost) : undefined,
              shipment_ref: v.shipment_ref,
              note: v.note,
            };
            if (v.supplier_id) body.supplier_id = Number(v.supplier_id);
            await api.stockReceive(body);
            await fetchAvail(Number(v.product_id));
            // Add a sale line for the just-received item if not already present.
            setLines((ls) => {
              if (ls.some((l) => l.product_id === String(v.product_id))) return ls;
              const empty = ls.find((l) => !l.product_id);
              if (empty) {
                return ls.map((l) =>
                  l.key === empty.key
                    ? { ...l, product_id: String(v.product_id), quantity: String(v.quantity) }
                    : l,
                );
              }
              return [...ls, { key: Date.now(), product_id: String(v.product_id), quantity: String(v.quantity), unit_price: "" }];
            });
            setShowReceive(false);
          }}
        />
      )}
    </div>
  );
}

const inp = "w-full rounded border border-line bg-paper px-3 py-1.5 text-sm outline-none focus:border-ink";

function Labelled({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-muted">{label}</label>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-muted">
      <span>{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  );
}
