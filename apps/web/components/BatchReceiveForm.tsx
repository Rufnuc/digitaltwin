"use client";
import { useState } from "react";
import { api } from "@/lib/api";

interface Ref {
  id: number;
  name: string;
  code: string;
}
interface BLine {
  key: number;
  product: string; // display text (search or a new name)
  quantity: string;
  unit_cost: string;
}

// One supplier delivery → many products received in a single batch. Products can be
// picked by search or typed as a new name, which creates them (auto-coded) on submit.
export function BatchReceiveForm({
  warehouses,
  suppliers,
  products,
  onClose,
  onDone,
}: {
  warehouses: Ref[];
  suppliers: Ref[];
  products: Ref[];
  onClose: () => void;
  onDone: (msg: string) => void;
}) {
  const [warehouseId, setWarehouseId] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [receivedDate, setReceivedDate] = useState(new Date().toISOString().slice(0, 10));
  const [shipmentRef, setShipmentRef] = useState("");
  const [lines, setLines] = useState<BLine[]>([
    { key: 1, product: "", quantity: "", unit_cost: "" },
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const label = (p: Ref) => `${p.code} — ${p.name}`;

  function setLine(key: number, patch: Partial<BLine>) {
    setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  }

  async function resolveProductId(text: string): Promise<number> {
    const t = text.trim();
    const match = products.find((p) => label(p) === t || p.name.toLowerCase() === t.toLowerCase());
    if (match) return match.id;
    // A new product — create it (auto-coded) so the catalogue stays in sync.
    const created = await api.createResource<Ref>("products", { name: t });
    products.push(created); // keep local list fresh for subsequent lines
    return created.id;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const valid = lines.filter((l) => l.product.trim() && Number(l.quantity) > 0);
    if (!warehouseId) return setError("Choose a warehouse.");
    if (valid.length === 0) return setError("Add at least one product line.");
    setBusy(true);
    try {
      const resolved = [];
      for (const l of valid) {
        resolved.push({
          product_id: await resolveProductId(l.product),
          quantity: Number(l.quantity),
          unit_cost: l.unit_cost ? Number(l.unit_cost) : undefined,
        });
      }
      const res = await api.stockReceiveBatch({
        warehouse_id: Number(warehouseId),
        supplier_id: supplierId ? Number(supplierId) : null,
        received_date: receivedDate || null,
        shipment_ref: shipmentRef || null,
        lines: resolved,
      });
      onDone(`Batch received: ${res.received} lot${res.received === 1 ? "" : "s"} added to stock.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Batch receive failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4"
      onMouseDown={onClose}
    >
      <form
        onMouseDown={(e) => e.stopPropagation()}
        onSubmit={submit}
        className="w-full max-w-2xl rounded-lg border border-line bg-paper p-4 shadow-xl"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">Batch receive from a supplier</h2>
          <button type="button" onClick={onClose} className="text-muted hover:text-ink">
            ✕
          </button>
        </div>

        <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Warehouse *">
            <select value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)} className={inp}>
              <option value="">Choose…</option>
              {warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.code} — {w.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Supplier">
            <select value={supplierId} onChange={(e) => setSupplierId(e.target.value)} className={inp}>
              <option value="">—</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.code} — {s.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Received date">
            <input type="date" value={receivedDate} onChange={(e) => setReceivedDate(e.target.value)} className={inp} />
          </Field>
          <Field label="Shipment / B-L reference">
            <input value={shipmentRef} onChange={(e) => setShipmentRef(e.target.value)} placeholder="MV … · BL-…" className={inp} />
          </Field>
        </div>

        <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">Products</div>
        <datalist id="batch-products">
          {products.map((p) => (
            <option key={p.id} value={label(p)} />
          ))}
        </datalist>
        <div className="space-y-2">
          {lines.map((l) => (
            <div key={l.key} className="grid grid-cols-12 items-center gap-2">
              <input
                list="batch-products"
                value={l.product}
                onChange={(e) => setLine(l.key, { product: e.target.value })}
                placeholder="Search or type a new product"
                className={`col-span-12 sm:col-span-6 ${inp}`}
              />
              <input
                type="number"
                min="1"
                value={l.quantity}
                onChange={(e) => setLine(l.key, { quantity: e.target.value })}
                placeholder="Qty"
                className={`col-span-4 sm:col-span-2 ${inp}`}
              />
              <input
                type="number"
                step="0.01"
                value={l.unit_cost}
                onChange={(e) => setLine(l.key, { unit_cost: e.target.value })}
                placeholder="Cost ₦"
                className={`col-span-6 sm:col-span-3 ${inp}`}
              />
              <button
                type="button"
                onClick={() => setLines((ls) => (ls.length > 1 ? ls.filter((x) => x.key !== l.key) : ls))}
                className="col-span-2 text-muted hover:text-red-700 sm:col-span-1"
                aria-label="Remove"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setLines((ls) => [...ls, { key: Date.now(), product: "", quantity: "", unit_cost: "" }])}
          className="mt-2 text-xs text-muted underline decoration-dotted"
        >
          + Add product
        </button>

        {error && <div className="mt-3 text-sm text-red-700">{error}</div>}
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash">
            Cancel
          </button>
          <button type="submit" disabled={busy} className="rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper disabled:opacity-50">
            {busy ? "Receiving…" : "Receive batch"}
          </button>
        </div>
      </form>
    </div>
  );
}

const inp = "w-full rounded border border-line bg-paper px-3 py-1.5 text-sm outline-none focus:border-ink";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-muted">{label}</label>
      {children}
    </div>
  );
}
