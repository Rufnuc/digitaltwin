"use client";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column, type FilterSpec, type FormField } from "@/components/DataTable";
import { InventoryTabs } from "@/components/InventoryTabs";
import { api, type WarehouseSummary } from "@/lib/api";
import { money2, num } from "@/lib/format";
import { Modal } from "@/components/Modal";

type Row = Record<string, unknown>;

const columns: Column<Row>[] = [
  { key: "code", header: "Code", sortable: true },
  { key: "name", header: "Name", sortable: true },
  { key: "location", header: "Location", sortable: true },
  { key: "type", header: "Type", sortable: true },
  { key: "status", header: "Status", sortable: true },
];

const filters: FilterSpec[] = [
  {
    key: "status",
    label: "Status",
    options: ["ACTIVE", "INACTIVE"].map((v) => ({ value: v, label: v })),
  },
];

const formFields: FormField[] = [
  { key: "code", label: "Code", required: true, placeholder: "WH-LAG" },
  { key: "name", label: "Name", required: true, placeholder: "Lagos Main Warehouse" },
  { key: "location", label: "Location", placeholder: "Apapa, Lagos" },
  { key: "address", label: "Address", type: "textarea" },
  {
    key: "type",
    label: "Type",
    type: "select",
    options: [
      { value: "warehouse", label: "Warehouse (storage)" },
      { value: "shop", label: "Point of sale (Home / Office)" },
      { value: "transit", label: "Transit" },
    ],
  },
  {
    key: "status",
    label: "Status",
    type: "select",
    options: ["ACTIVE", "INACTIVE"].map((v) => ({ value: v, label: v })),
  },
];

export default function WarehousesPage() {
  return (
    <div>
      <PageHeader
        title="Warehouses"
        subtitle="Your storage locations. The same product can hold stock in several at once; transfers move it between them."
      />
      <InventoryTabs active="warehouses" />
      <ResourceTable<Row>
        resource="warehouses"
        columns={columns}
        filters={filters}
        formFields={formFields}
        entityLabel="warehouse"
        writeRole="MANAGER"
        showProvenance={false}
        viewable
        renderExtra={(row) => (
          <WarehouseDetailButton warehouseId={Number(row.id)} name={String(row.name ?? "")} />
        )}
      />
    </div>
  );
}

const day = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("en-NG", { dateStyle: "medium" }) : "—";

function WarehouseDetailButton({ warehouseId, name }: { warehouseId: number; name: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-t border-line pt-3">
      <button onClick={() => setOpen(true)}
        className="w-full rounded border border-line px-3 py-2 text-sm font-medium hover:bg-wash">
        📦 Stock stored &amp; records
      </button>
      {open && <WarehouseDetailModal warehouseId={warehouseId} name={name} onClose={() => setOpen(false)} />}
    </div>
  );
}

function WarehouseDetailModal({ warehouseId, name, onClose }: {
  warehouseId: number; name: string; onClose: () => void;
}) {
  const [data, setData] = useState<WarehouseSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"products" | "movements">("products");

  const load = useCallback(() => {
    api.warehouseSummary(warehouseId)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load warehouse"));
  }, [warehouseId]);
  useEffect(() => { load(); }, [load]);

  return (
    <Modal title={`${name || "Warehouse"} · stock & records`} size="xl" onClose={onClose}>
      {error && <div className="text-sm text-red-700">{error}</div>}
      {!data && !error && <div className="text-sm text-muted">Loading…</div>}
      {data && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 text-center sm:grid-cols-4">
            <Stat label="Value of goods" value={money2(data.total_value)} />
            <Stat label="Units available" value={num(data.total_units)} />
            <Stat label="Products" value={num(data.product_count)} />
            <Stat label="Open lots" value={num(data.open_lot_count)} />
          </div>

          <div className="mb-2 flex gap-1.5">
            {([["products", `Products (${data.products.length})`],
               ["movements", `Recent movements (${data.recent_movements.length})`]] as const).map(([t, label]) => (
              <button key={t} onClick={() => setTab(t)}
                className={`rounded border px-2.5 py-1 text-xs ${tab === t ? "border-ink bg-ink text-paper" : "border-line hover:bg-wash"}`}>
                {label}
              </button>
            ))}
          </div>

          <div className="max-h-96 space-y-1 overflow-y-auto">
            {tab === "products" && (data.products.length === 0 ? (
              <div className="text-sm text-muted">No goods stored here yet.</div>
            ) : data.products.map((p) => (
              <div key={p.product_id} className="flex items-start gap-2 rounded border border-line px-3 py-2 text-sm">
                <span className="min-w-0 flex-1 truncate">
                  <span className="font-medium">{p.name ?? "—"}</span>
                  {p.code ? <span className="text-muted"> · {p.code}</span> : null}
                </span>
                <span className="shrink-0 text-right">
                  <span className="block tabular-nums">{num(p.on_hand)} units</span>
                  <span className="block tabular-nums text-muted">{money2(p.value)}</span>
                </span>
              </div>
            )))}

            {tab === "movements" && (data.recent_movements.length === 0 ? (
              <div className="text-sm text-muted">No movements recorded here yet.</div>
            ) : data.recent_movements.map((m, i) => (
              <div key={i} className="flex items-start gap-2 rounded border border-line px-3 py-2 text-sm">
                <span className="min-w-0 flex-1">
                  <span className="font-medium">{m.type}</span>
                  <span className="text-muted"> · {m.product ?? "—"}</span>
                  <span className="block text-xs text-muted">{day(m.occurred_at)}{m.note ? ` · ${m.note}` : ""}</span>
                </span>
                <span className={`shrink-0 tabular-nums ${m.quantity < 0 ? "text-red-700 dark:text-red-300" : "text-green-700 dark:text-green-300"}`}>
                  {m.quantity > 0 ? "+" : ""}{num(m.quantity)}
                </span>
              </div>
            )))}
          </div>
        </>
      )}
    </Modal>
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
