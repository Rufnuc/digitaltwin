"use client";
import { useCallback, useEffect, useState } from "react";
import { api, type Purchase } from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card } from "@/components/ui";

const naira = (n: number | null | undefined) =>
  n == null ? "—" : "₦" + Math.round(n).toLocaleString("en-NG");
const day = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("en-NG", { dateStyle: "medium" }) : "—";

const STATUS_STYLE: Record<string, string> = {
  REQUEST: "bg-yellow-500/15 text-yellow-700 dark:text-yellow-300 border-yellow-500/30",
  ORDERED: "bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/30",
  RECEIVED: "bg-green-500/15 text-green-700 dark:text-green-300 border-green-500/30",
  CANCELLED: "bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/30",
};
const STATUSES = ["REQUEST", "ORDERED", "RECEIVED", "CANCELLED"];

function Badge({ status }: { status: string }) {
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[11px] font-medium ${STATUS_STYLE[status] ?? ""}`}>
      {status}
    </span>
  );
}

type SupplierPick = { id: number; code: string; name: string };
type ProductPick = { id: number; code: string; name: string; purchase_cost: number | null };
type WarehousePick = { id: number; code: string; name: string };
type DraftLine = { product_id: number; product_code: string; product_name: string; quantity: number; unit_cost: number };

export default function ProcurementPage() {
  const [rows, setRows] = useState<Purchase[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState<Purchase | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    const qs = statusFilter ? `?status=${statusFilter}` : "";
    api.listPurchases(qs).then((r) => setRows(r.items)).catch(() => setRows([])).finally(() => setLoading(false));
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  async function openDetail(id: number) {
    try { setSelected(await api.getPurchase(id)); } catch { /* ignore */ }
  }

  return (
    <div>
      <PageHeader
        title="Procurement"
        subtitle="Raise a request list for a supplier, order it, then receive it into stock — transport cost rolls into landed cost."
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded border border-line bg-paper px-3 py-1.5 text-sm">
          <option value="">Status: all</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <button onClick={() => setCreating(true)}
          className="ml-auto rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper">
          + New request
        </button>
      </div>

      <Card className="overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="border-b border-line text-left text-xs text-muted">
            <tr>
              <th className="px-3 py-2">Reference</th>
              <th className="px-3 py-2">Supplier</th>
              <th className="px-3 py-2">Items</th>
              <th className="px-3 py-2">Total</th>
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={6} className="px-3 py-6 text-center text-muted">Loading…</td></tr>}
            {!loading && rows.length === 0 && <tr><td colSpan={6} className="px-3 py-6 text-center text-muted">No requests yet.</td></tr>}
            {rows.map((p) => (
              <tr key={p.id} onClick={() => openDetail(p.id)}
                className="cursor-pointer border-t border-line hover:bg-wash">
                <td className="px-3 py-2 font-medium">{p.reference}</td>
                <td className="px-3 py-2">{p.supplier_name ?? "—"}</td>
                <td className="px-3 py-2">{p.line_count}</td>
                <td className="px-3 py-2">{naira(p.total)}</td>
                <td className="px-3 py-2 text-muted">{day(p.purchase_date)}</td>
                <td className="px-3 py-2"><Badge status={p.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {selected && (
        <PurchaseDrawer purchase={selected} onClose={() => setSelected(null)}
          onChanged={(p) => { setSelected(p); load(); }} />
      )}
      {creating && (
        <NewRequestModal onClose={() => setCreating(false)}
          onCreated={(p) => { setCreating(false); setSelected(p); load(); }} />
      )}
    </div>
  );
}

function PurchaseDrawer({ purchase, onClose, onChanged }: {
  purchase: Purchase; onClose: () => void; onChanged: (p: Purchase) => void;
}) {
  const [p, setP] = useState(purchase);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [receiving, setReceiving] = useState(false);

  async function act(fn: () => Promise<Purchase>) {
    setBusy(true); setErr(null);
    try { const u = await fn(); setP(u); onChanged(u); }
    catch (e) { setErr(e instanceof Error ? e.message : "Failed"); }
    finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-line bg-paper p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-lg font-semibold">{p.reference}</h2>
          <Badge status={p.status} />
          <button onClick={onClose} className="ml-auto text-muted hover:text-ink">✕</button>
        </div>
        <div className="mb-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <span><span className="text-muted">Supplier:</span> {p.supplier_name ?? "—"}</span>
          <span><span className="text-muted">Date:</span> {day(p.purchase_date)}</span>
          <span><span className="text-muted">Payment:</span> {p.payment_status}</span>
        </div>

        <div className="overflow-x-auto rounded border border-line">
          <table className="w-full text-sm">
            <thead className="border-b border-line text-left text-xs text-muted">
              <tr><th className="px-2 py-1.5">Item</th><th className="px-2 py-1.5">Qty</th>
              <th className="px-2 py-1.5">Unit cost</th><th className="px-2 py-1.5">Line total</th></tr>
            </thead>
            <tbody>
              {(p.lines ?? []).map((ln, i) => (
                <tr key={i} className="border-t border-line">
                  <td className="px-2 py-1.5">{ln.product_name ?? ln.description ?? `#${ln.product_id}`}
                    {ln.product_code ? <span className="text-muted"> · {ln.product_code}</span> : null}</td>
                  <td className="px-2 py-1.5">{ln.quantity}</td>
                  <td className="px-2 py-1.5">{naira(ln.unit_cost)}</td>
                  <td className="px-2 py-1.5">{naira(ln.line_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-2 space-y-0.5 text-right text-sm">
          <div><span className="text-muted">Goods:</span> {naira(p.subtotal)}</div>
          {p.transport_cost > 0 && <div><span className="text-muted">Transport:</span> {naira(p.transport_cost)}</div>}
          <div className="font-semibold"><span className="text-muted">Total:</span> {naira(p.total)}</div>
        </div>

        {err && <div className="mt-2 text-sm text-red-700">{err}</div>}

        <div className="mt-3 flex flex-wrap gap-2">
          {p.status === "REQUEST" && (
            <button onClick={() => act(() => api.setPurchaseStatus(p.id, "ORDERED"))} disabled={busy}
              className="rounded border border-blue-500/40 px-3 py-1.5 text-sm text-blue-700 hover:bg-blue-500/10">
              Mark ordered
            </button>
          )}
          {(p.status === "REQUEST" || p.status === "ORDERED") && (
            <button onClick={() => setReceiving(true)} disabled={busy}
              className="rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper">
              Receive into stock
            </button>
          )}
          <button onClick={() => printRequest(p)}
            className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash">Print request</button>
          {p.status !== "RECEIVED" && p.status !== "CANCELLED" && (
            <button onClick={() => act(() => api.setPurchaseStatus(p.id, "CANCELLED"))} disabled={busy}
              className="ml-auto rounded border border-red-500/40 px-3 py-1.5 text-sm text-red-700 hover:bg-red-500/10">
              Cancel
            </button>
          )}
        </div>
        {p.status === "RECEIVED" && (
          <p className="mt-2 text-xs text-green-700 dark:text-green-300">✓ Received — stock is in the warehouse and traced to this supplier.</p>
        )}

        {receiving && (
          <ReceiveModal purchase={p} onClose={() => setReceiving(false)}
            onReceived={(u) => { setReceiving(false); setP(u); onChanged(u); }} />
        )}
      </div>
    </div>
  );
}

function ReceiveModal({ purchase, onClose, onReceived }: {
  purchase: Purchase; onClose: () => void; onReceived: (p: Purchase) => void;
}) {
  const [warehouses, setWarehouses] = useState<WarehousePick[]>([]);
  const [warehouseId, setWarehouseId] = useState<number | "">("");
  const [transport, setTransport] = useState("0");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.list<WarehousePick>("warehouses", "?limit=100").then((r) => {
      setWarehouses(r.items);
      if (r.items.length === 1) setWarehouseId(r.items[0].id);
    }).catch(() => {});
  }, []);

  async function receive() {
    if (!warehouseId) { setErr("Pick a warehouse"); return; }
    setBusy(true); setErr(null);
    try {
      onReceived(await api.receivePurchase(purchase.id, {
        warehouse_id: warehouseId, transport_cost: Number(transport) || 0,
      }));
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not receive"); setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="w-full max-w-sm rounded-lg border border-line bg-paper p-4 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center"><h3 className="font-semibold">Receive {purchase.reference}</h3>
          <button onClick={onClose} className="ml-auto text-muted hover:text-ink">✕</button></div>
        <label className="mb-2 block">
          <span className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Warehouse</span>
          <select value={warehouseId} onChange={(e) => setWarehouseId(Number(e.target.value))}
            className="w-full rounded border border-line bg-paper px-2 py-1.5 text-sm">
            <option value="">Select…</option>
            {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </label>
        <label className="mb-3 block">
          <span className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Transport cost (₦)</span>
          <input type="number" value={transport} onChange={(e) => setTransport(e.target.value)}
            className="w-full rounded border border-line bg-paper px-2 py-1.5 text-sm" />
          <span className="mt-1 block text-[11px] text-muted">Spread across units into landed cost.</span>
        </label>
        {err && <div className="mb-2 text-sm text-red-700">{err}</div>}
        <button onClick={receive} disabled={busy}
          className="w-full rounded bg-ink px-3 py-2 text-sm font-medium text-paper disabled:opacity-40">
          {busy ? "Receiving…" : "Receive into stock"}
        </button>
      </div>
    </div>
  );
}

function NewRequestModal({ onClose, onCreated }: {
  onClose: () => void; onCreated: (p: Purchase) => void;
}) {
  const [suppliers, setSuppliers] = useState<SupplierPick[]>([]);
  const [supplierId, setSupplierId] = useState<number | "">("");
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [pq, setPq] = useState("");
  const [matches, setMatches] = useState<ProductPick[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.list<SupplierPick>("suppliers", "?limit=200").then((r) => setSuppliers(r.items)).catch(() => {});
  }, []);

  async function searchProducts() {
    try {
      const r = await api.list<ProductPick>("products", `?q=${encodeURIComponent(pq)}&limit=10`);
      setMatches(r.items);
    } catch { /* ignore */ }
  }
  function addLine(pr: ProductPick) {
    if (lines.some((l) => l.product_id === pr.id)) return;
    setLines([...lines, { product_id: pr.id, product_code: pr.code, product_name: pr.name,
      quantity: 1, unit_cost: pr.purchase_cost ?? 0 }]);
    setMatches([]); setPq("");
  }
  function setLine(i: number, k: "quantity" | "unit_cost", v: number) {
    setLines(lines.map((l, j) => (j === i ? { ...l, [k]: v } : l)));
  }

  async function submit() {
    if (lines.length === 0) { setErr("Add at least one item"); return; }
    setBusy(true); setErr(null);
    try {
      onCreated(await api.createRequest({
        supplier_id: supplierId || null,
        lines: lines.map((l) => ({ product_id: l.product_id, quantity: l.quantity, unit_cost: l.unit_cost })),
      }));
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not create"); setBusy(false); }
  }

  const total = lines.reduce((s, l) => s + l.quantity * l.unit_cost, 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-line bg-paper p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center"><h2 className="text-lg font-semibold">New request</h2>
          <button onClick={onClose} className="ml-auto text-muted hover:text-ink">✕</button></div>

        <label className="mb-3 block">
          <span className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Supplier</span>
          <select value={supplierId} onChange={(e) => setSupplierId(Number(e.target.value))}
            className="w-full rounded border border-line bg-paper px-2 py-1.5 text-sm">
            <option value="">Select supplier…</option>
            {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.code})</option>)}
          </select>
        </label>

        <div className="mb-2 flex gap-2">
          <input value={pq} onChange={(e) => setPq(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && searchProducts()}
            placeholder="Search product to add…"
            className="flex-1 rounded border border-line bg-paper px-2 py-1.5 text-sm outline-none focus:border-ink" />
          <button onClick={searchProducts} className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash">Find</button>
        </div>
        {matches.length > 0 && (
          <div className="mb-2 max-h-40 space-y-1 overflow-y-auto rounded border border-line p-1">
            {matches.map((m) => (
              <button key={m.id} onClick={() => addLine(m)}
                className="block w-full rounded px-2 py-1 text-left text-sm hover:bg-wash">
                {m.name} <span className="text-muted">· {m.code}</span>
              </button>
            ))}
          </div>
        )}

        {lines.length > 0 && (
          <div className="mb-2 overflow-x-auto rounded border border-line">
            <table className="w-full text-sm">
              <thead className="border-b border-line text-left text-xs text-muted">
                <tr><th className="px-2 py-1.5">Item</th><th className="px-2 py-1.5 w-16">Qty</th>
                <th className="px-2 py-1.5 w-24">Unit cost</th><th className="px-2 py-1.5"></th></tr>
              </thead>
              <tbody>
                {lines.map((l, i) => (
                  <tr key={i} className="border-t border-line">
                    <td className="px-2 py-1.5">{l.product_name}<span className="text-muted"> · {l.product_code}</span></td>
                    <td className="px-2 py-1"><input type="number" value={l.quantity}
                      onChange={(e) => setLine(i, "quantity", Number(e.target.value))}
                      className="w-14 rounded border border-line bg-paper px-1 py-0.5 text-sm" /></td>
                    <td className="px-2 py-1"><input type="number" value={l.unit_cost}
                      onChange={(e) => setLine(i, "unit_cost", Number(e.target.value))}
                      className="w-20 rounded border border-line bg-paper px-1 py-0.5 text-sm" /></td>
                    <td className="px-2 py-1 text-right"><button onClick={() => setLines(lines.filter((_, j) => j !== i))}
                      className="text-muted hover:text-red-700">✕</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mb-3 text-right text-sm font-medium">Estimated: {naira(total)}</div>

        {err && <div className="mb-2 text-sm text-red-700">{err}</div>}
        <button onClick={submit} disabled={busy}
          className="w-full rounded bg-ink px-3 py-2 text-sm font-medium text-paper disabled:opacity-40">
          {busy ? "Creating…" : "Create request"}
        </button>
      </div>
    </div>
  );
}

// Printable request list to send the supplier.
function printRequest(p: Purchase) {
  const rows = (p.lines ?? []).map((l, i) =>
    `<tr><td style="padding:4px 10px">${i + 1}</td>
     <td style="padding:4px 10px">${l.product_name ?? l.description ?? ""}${l.product_code ? " (" + l.product_code + ")" : ""}</td>
     <td style="padding:4px 10px;text-align:right">${l.quantity}</td></tr>`).join("");
  const html = `<!doctype html><html><head><title>${p.reference}</title>
<style>body{font-family:system-ui,Arial,sans-serif;padding:32px;color:#111}
h1{font-size:20px;margin:0 0 2px}.sub{color:#666;margin-bottom:16px}
table{border-collapse:collapse;width:100%;max-width:560px}
th,td{border-bottom:1px solid #eee;font-size:14px}
th{text-align:left;padding:6px 10px;color:#666}</style></head><body>
<h1>PURCHASE REQUEST ${p.reference}</h1>
<div class="sub">Supplier: ${p.supplier_name ?? "—"} · Date: ${day(p.purchase_date)}</div>
<table><thead><tr><th>#</th><th>Item</th><th style="text-align:right">Qty</th></tr></thead>
<tbody>${rows}</tbody></table>
<p style="margin-top:32px;color:#666;font-size:12px">Please quote availability and price for the above.</p>
</body></html>`;
  const win = window.open("", "_blank", "width=680,height=800");
  if (!win) return;
  win.document.write(html); win.document.close(); win.focus(); win.print();
}
