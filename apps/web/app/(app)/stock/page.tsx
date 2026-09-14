"use client";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/Shell";
import { Card, ProvenanceBadge } from "@/components/ui";
import { EntityForm, type FormField } from "@/components/EntityForm";
import { InventoryTabs } from "@/components/InventoryTabs";
import { BatchReceiveForm } from "@/components/BatchReceiveForm";
import { api, getRole, type StockLot, type StockLotDetail } from "@/lib/api";
import { money2, num } from "@/lib/format";
import { roleAtLeast } from "@/lib/roles";

type Opt = { value: string; label: string };

export default function StockPage() {
  const [lots, setLots] = useState<StockLot[]>([]);
  const [warehouses, setWarehouses] = useState<{ id: number; name: string; code: string }[]>([]);
  const [products, setProducts] = useState<{ id: number; name: string; code: string }[]>([]);
  const [suppliers, setSuppliers] = useState<{ id: number; name: string; code: string }[]>([]);
  const [warehouseId, setWarehouseId] = useState("");
  const [inStockOnly, setInStockOnly] = useState(true);
  const [detail, setDetail] = useState<StockLotDetail | null>(null);
  const [modal, setModal] = useState<null | "receive" | "transfer" | "batch">(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [adjustLot, setAdjustLot] = useState<StockLot | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canWrite = roleAtLeast(getRole(), "STAFF");
  const canAdjust = roleAtLeast(getRole(), "MANAGER");

  const load = useCallback(async () => {
    try {
      const params =
        `?limit=300` +
        (warehouseId ? `&warehouse_id=${warehouseId}` : "") +
        (inStockOnly ? `&in_stock_only=true` : "");
      const r = await api.stockLots(params);
      setLots(r.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }, [warehouseId, inStockOnly]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api.list<{ id: number; name: string; code: string }>("warehouses", "?limit=200")
      .then((r) => setWarehouses(r.items))
      .catch(() => {});
    api.list<{ id: number; name: string; code: string }>("products", "?limit=200")
      .then((r) => setProducts(r.items))
      .catch(() => {});
    api.list<{ id: number; name: string; code: string }>("suppliers", "?limit=200")
      .then((r) => setSuppliers(r.items))
      .catch(() => {});
  }, []);

  const whOpts: Opt[] = warehouses.map((w) => ({ value: String(w.id), label: `${w.code} — ${w.name}` }));
  const prodOpts: Opt[] = products.map((p) => ({ value: String(p.id), label: `${p.code} — ${p.name}` }));
  const supplierOpts: Opt[] = suppliers.map((s) => ({ value: String(s.id), label: `${s.code} — ${s.name}` }));

  async function openTrace(lot: StockLot) {
    setDetail(null);
    const d = await api.stockLot(lot.id);
    setDetail(d);
  }

  const receiveFields: FormField[] = [
    { key: "product_id", label: "Product", type: "select", options: prodOpts, required: true },
    { key: "warehouse_id", label: "Warehouse", type: "select", options: whOpts, required: true },
    { key: "supplier_id", label: "Supplier / source", type: "select", options: supplierOpts },
    { key: "quantity", label: "Quantity", type: "number", required: true },
    { key: "unit_cost", label: "Landed unit cost (₦)", type: "number", step: "0.01",
      help: "Leave blank to use the product's purchase cost." },
    { key: "received_date", label: "Received date", type: "date" },
    { key: "shipment_ref", label: "Shipment / B-L reference", placeholder: "MV EVER GIVEN · BL-12345" },
    { key: "vessel_mmsi", label: "Vessel MMSI (optional)", type: "number",
      help: "If the ship is on the shipping monitor, the marker links to its live voyage." },
    { key: "note", label: "Note", type: "textarea" },
  ];

  const transferFields: FormField[] = [
    { key: "product_id", label: "Product", type: "select", options: prodOpts, required: true },
    { key: "from_warehouse_id", label: "From warehouse", type: "select", options: whOpts, required: true },
    { key: "to_warehouse_id", label: "To warehouse", type: "select", options: whOpts, required: true },
    { key: "quantity", label: "Quantity", type: "number", required: true },
    { key: "note", label: "Note", type: "textarea" },
  ];

  const coerceIds = (v: Record<string, unknown>) => {
    const out = { ...v };
    for (const k of ["product_id", "warehouse_id", "from_warehouse_id", "to_warehouse_id",
                     "supplier_id", "vessel_mmsi"]) {
      if (out[k] != null) out[k] = Number(out[k]);
    }
    return out;
  };

  return (
    <div>
      <PageHeader
        title="Stock &amp; Markers"
        subtitle="Every intake becomes a lot (marker) — scannable code, warehouse, date in, source and landed cost. Trace any marker to see who bought it and everywhere it moved."
      />
      <InventoryTabs active="stock" />

      {notice && (
        <div className="mb-3 flex items-center justify-between rounded border border-green-500/30 bg-green-500/15 px-3 py-2 text-sm text-green-700 dark:text-green-300">
          <span>✓ {notice}</span>
          <button onClick={() => setNotice(null)} className="text-xs underline">
            dismiss
          </button>
        </div>
      )}
      {error && <div className="mb-3 text-sm text-red-700">Error: {error}</div>}

      <div className="mb-3 flex flex-wrap items-center gap-3">
        <select
          value={warehouseId}
          onChange={(e) => setWarehouseId(e.target.value)}
          className="rounded border border-line bg-paper px-2 py-1.5 text-sm"
        >
          <option value="">All warehouses</option>
          {whOpts.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={inStockOnly} onChange={(e) => setInStockOnly(e.target.checked)} />
          In stock only
        </label>
        {canWrite && (
          <div className="ml-auto flex gap-2">
            <button
              onClick={() => setModal("receive")}
              className="rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper"
            >
              + Receive stock
            </button>
            <button
              onClick={() => setModal("batch")}
              className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash"
            >
              Batch receive
            </button>
            <button
              onClick={() => setModal("transfer")}
              className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash"
            >
              Transfer
            </button>
          </div>
        )}
      </div>

      <Card className="p-0">
        <div className="flex items-center justify-between border-b border-line px-4 py-2">
          <span className="text-sm font-medium">{lots.length} lots</span>
          <ProvenanceBadge origin="REAL" />
        </div>

        {/* Mobile cards */}
        <div className="space-y-2 p-3 sm:hidden">
          {lots.length === 0 ? (
            <div className="px-1 py-4 text-sm text-muted">No lots. Receive stock to create one.</div>
          ) : (
            lots.map((l) => (
              <div key={l.id} className="rounded-lg border border-line bg-paper p-3">
                <div className="mb-1 flex items-center justify-between">
                  <span className="font-mono text-sm font-medium">{l.lot_code}</span>
                  <StatusChip status={l.status} />
                </div>
                <LotRow label="Product" value={l.product} />
                <LotRow label="Warehouse" value={l.warehouse} />
                <LotRow label="Received" value={l.received_date} />
                <LotRow label="Remaining" value={`${num(l.quantity_remaining)} / ${num(l.quantity_received)}`} />
                <LotRow label="Unit cost" value={l.unit_cost != null ? money2(l.unit_cost) : "—"} />
                <div className="mt-1 flex justify-end gap-3 border-t border-line pt-1.5 text-xs">
                  <button onClick={() => openTrace(l)} className="text-muted underline">Trace</button>
                  {canAdjust && (
                    <button onClick={() => setAdjustLot(l)} className="text-muted underline">Adjust</button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Desktop table */}
        <div className="hidden overflow-x-auto sm:block">
          <table className="min-w-full text-sm">
            <thead className="bg-wash text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                {["Lot code", "Product", "Warehouse", "Received", "Remaining", "Unit cost", "Status", ""].map(
                  (h) => (
                    <th key={h} className="px-3 py-2 font-medium">{h}</th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {lots.length === 0 ? (
                <tr>
                  <td className="px-3 py-6 text-muted" colSpan={8}>
                    No lots. Receive stock to create one.
                  </td>
                </tr>
              ) : (
                lots.map((l) => (
                  <tr key={l.id} className="border-t border-line hover:bg-wash">
                    <td className="px-3 py-2 font-mono text-xs">{l.lot_code}</td>
                    <td className="px-3 py-2">{l.product}</td>
                    <td className="px-3 py-2">{l.warehouse}</td>
                    <td className="px-3 py-2 tabular-nums">{l.received_date}</td>
                    <td className="px-3 py-2 tabular-nums">
                      {num(l.quantity_remaining)} / {num(l.quantity_received)}
                    </td>
                    <td className="px-3 py-2 tabular-nums">
                      {l.unit_cost != null ? money2(l.unit_cost) : "—"}
                    </td>
                    <td className="px-3 py-2"><StatusChip status={l.status} /></td>
                    <td className="whitespace-nowrap px-3 py-2 text-right">
                      <button onClick={() => openTrace(l)} className="text-xs text-muted underline hover:text-ink">
                        Trace
                      </button>
                      {canAdjust && (
                        <button onClick={() => setAdjustLot(l)} className="ml-3 text-xs text-muted underline hover:text-ink">
                          Adjust
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {modal === "receive" && (
        <EntityForm
          title="Receive stock"
          submitLabel="Receive"
          fields={receiveFields}
          onClose={() => setModal(null)}
          onSubmit={async (v) => {
            await api.stockReceive(coerceIds(v));
            setModal(null);
            load();
          }}
        />
      )}
      {modal === "transfer" && (
        <EntityForm
          title="Transfer stock"
          submitLabel="Transfer"
          fields={transferFields}
          onClose={() => setModal(null)}
          onSubmit={async (v) => {
            await api.stockTransfer(coerceIds(v));
            setModal(null);
            load();
          }}
        />
      )}
      {modal === "batch" && (
        <BatchReceiveForm
          warehouses={warehouses}
          suppliers={suppliers}
          products={products}
          onClose={() => setModal(null)}
          onDone={(msg) => {
            setModal(null);
            setNotice(msg);
            load();
          }}
        />
      )}
      {adjustLot && (
        <EntityForm
          title={`Adjust ${adjustLot.lot_code}`}
          submitLabel="Apply"
          fields={[
            { key: "delta", label: "Change (+/- units)", type: "number", required: true,
              help: `Currently ${adjustLot.quantity_remaining} remaining.` },
            { key: "reason", label: "Reason", required: true, placeholder: "stock count / damage / loss" },
          ]}
          onClose={() => setAdjustLot(null)}
          onSubmit={async (v) => {
            await api.stockAdjust({ lot_id: adjustLot.id, delta: Number(v.delta), reason: v.reason });
            setAdjustLot(null);
            load();
          }}
        />
      )}

      {detail && <TraceDrawer detail={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

function LotRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex items-start justify-between gap-3 py-0.5 text-sm">
      <span className="shrink-0 text-xs uppercase tracking-wide text-muted">{label}</span>
      <span className="min-w-0 break-words text-right tabular-nums">{value ?? "—"}</span>
    </div>
  );
}

function StatusChip({ status }: { status: string }) {
  const ok = status === "IN_STOCK";
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[10px] ${
        ok
          ? "bg-green-500/15 text-green-700 dark:text-green-300"
          : "bg-muted/15 text-muted"
      }`}
    >
      {status}
    </span>
  );
}

function TraceDrawer({ detail, onClose }: { detail: StockLotDetail; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onMouseDown={onClose}>
      <div
        className="h-full w-full max-w-md overflow-y-auto border-l border-line bg-paper p-4 shadow-xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-mono text-sm font-semibold">{detail.lot_code}</h2>
          <button onClick={onClose} aria-label="Close" className="text-muted hover:text-ink">✕</button>
        </div>

        <div className="mb-4 grid grid-cols-2 gap-2 text-sm">
          <Field label="Product" value={detail.product} />
          <Field label="Warehouse" value={detail.warehouse} />
          <Field label="Brought in" value={detail.received_date} />
          <Field label="Source" value={detail.supplier ?? "—"} />
          <Field label="Received" value={num(detail.quantity_received)} />
          <Field label="Remaining" value={num(detail.quantity_remaining)} />
          <Field label="Unit cost" value={detail.unit_cost != null ? money2(detail.unit_cost) : "—"} />
          <Field label="Status" value={detail.status} />
        </div>

        {(detail.shipment_ref || detail.vessel) && (
          <div className="mb-4 rounded-lg border border-line bg-wash p-3 text-sm">
            <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">
              How it arrived
            </div>
            {detail.shipment_ref && <div>Shipment: {detail.shipment_ref}</div>}
            {detail.vessel && (
              <div className="mt-1 text-xs text-muted">
                {detail.vessel.tracked ? (
                  <>
                    Vessel {detail.vessel.name ?? detail.vessel.mmsi}
                    {detail.vessel.region ? ` · ${detail.vessel.region}` : ""}
                    {detail.vessel.arrived_nigeria
                      ? " · ✓ arrived Nigeria"
                      : detail.vessel.bound_for_nigeria
                        ? " · → Nigeria"
                        : ""}
                    {detail.vessel.last_seen
                      ? ` · seen ${new Date(detail.vessel.last_seen).toLocaleString()}`
                      : ""}
                  </>
                ) : (
                  <>Vessel MMSI {detail.vessel.mmsi} (not currently on the shipping monitor)</>
                )}
              </div>
            )}
          </div>
        )}

        {detail.sold_to.length > 0 && (
          <div className="mb-4 rounded-lg border border-line bg-wash p-3 text-sm">
            <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">Bought by</div>
            {detail.sold_to.join(", ")}
          </div>
        )}

        <div className="text-xs font-medium uppercase tracking-wide text-muted">Movement history</div>
        <ol className="mt-2 space-y-2">
          {detail.movements.map((m) => (
            <li key={m.id} className="rounded border border-line p-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium">{m.type}</span>
                <span className={`tabular-nums ${m.quantity < 0 ? "text-red-700" : "text-green-700"}`}>
                  {m.quantity > 0 ? "+" : ""}
                  {m.quantity}
                </span>
              </div>
              <div className="text-[11px] text-muted">
                {m.occurred_at ? new Date(m.occurred_at).toLocaleString() : ""} · {m.warehouse}
                {m.customer ? ` · buyer: ${m.customer}` : ""}
                {m.counterparty_warehouse ? ` · ↔ ${m.counterparty_warehouse}` : ""}
                {m.invoice_id ? ` · invoice #${m.invoice_id}` : ""}
                {m.note ? ` · ${m.note}` : ""}
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div className="text-sm">{value ?? "—"}</div>
    </div>
  );
}
