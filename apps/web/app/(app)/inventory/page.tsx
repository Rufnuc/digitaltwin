"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/Shell";
import { Card } from "@/components/ui";
import { InventoryTabs } from "@/components/InventoryTabs";
import { api, imageSrc, type StockLevel } from "@/lib/api";
import { money2, num } from "@/lib/format";

interface Prod { id: number; name: string; code: string; image_url: string | null }
type Sort = "name" | "on_hand" | "value" | "reorder_level";

export default function InventoryPage() {
  const [rows, setRows] = useState<StockLevel[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [products, setProducts] = useState<Prod[]>([]);
  const [warehouses, setWarehouses] = useState<{ id: number; name: string; code: string }[]>([]);
  const [q, setQ] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [category, setCategory] = useState("");
  const [lowStock, setLowStock] = useState(false);
  const [sort, setSort] = useState<Sort>("on_hand");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.list<Prod>("products", "?limit=500").then((r) => setProducts(r.items)).catch(() => {});
    api.list<{ id: number; name: string; code: string }>("warehouses", "?limit=200")
      .then((r) => setWarehouses(r.items)).catch(() => {});
  }, []);

  const pmap = useMemo(() => {
    const m = new Map<number, Prod>();
    for (const p of products) m.set(p.id, p);
    return m;
  }, [products]);

  const load = useCallback(() => {
    setLoading(true);
    const qs =
      `?limit=500&sort=${sort}&sort_dir=${sortDir}` +
      (q ? `&q=${encodeURIComponent(q)}` : "") +
      (warehouseId ? `&warehouse_id=${warehouseId}` : "") +
      (category ? `&category=${encodeURIComponent(category)}` : "") +
      (lowStock ? `&low_stock=true` : "");
    api.stockLevels(qs)
      .then((r) => { setRows(r.items); setCategories(r.categories); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [q, warehouseId, category, lowStock, sort, sortDir]);

  // Debounce the search box; other filters apply immediately.
  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);

  function toggleSort(col: Sort) {
    if (sort === col) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSort(col); setSortDir(col === "name" ? "asc" : "desc"); }
  }
  const arrow = (col: Sort) => (sort === col ? (sortDir === "asc" ? " ↑" : " ↓") : "");

  const totalValue = rows.reduce((s, r) => s + r.value, 0);
  const totalUnits = rows.reduce((s, r) => s + r.on_hand, 0);

  return (
    <div>
      <PageHeader
        title="Inventory"
        subtitle="Current stock level and value per product, from the lot ledger. For lot-level history, see Stock & Markers."
      />
      <InventoryTabs active="levels" />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Search product name or code…"
          className="min-w-52 flex-1 rounded border border-line bg-paper px-3 py-1.5 text-sm outline-none focus:border-ink" />
        <select value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}
          className="rounded border border-line bg-paper px-2 py-1.5 text-sm">
          <option value="">All warehouses</option>
          {warehouses.map((w) => <option key={w.id} value={w.id}>{w.code} — {w.name}</option>)}
        </select>
        <select value={category} onChange={(e) => setCategory(e.target.value)}
          className="rounded border border-line bg-paper px-2 py-1.5 text-sm">
          <option value="">All categories</option>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={lowStock} onChange={(e) => setLowStock(e.target.checked)} />
          Low stock only
        </label>
      </div>

      {error && <div className="mb-3 text-sm text-red-700">Error: {error}</div>}

      <Card className="p-0">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line px-4 py-2 text-sm">
          <span className="font-medium">{rows.length} products</span>
          <span className="text-muted">{num(totalUnits)} units on hand</span>
          <span className="text-muted">Total value {money2(totalValue)}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-wash text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <Th onClick={() => toggleSort("name")}>Product{arrow("name")}</Th>
                <th className="px-3 py-2 font-medium">Category</th>
                <Th onClick={() => toggleSort("on_hand")} right>On hand{arrow("on_hand")}</Th>
                <Th onClick={() => toggleSort("reorder_level")} right>Reorder{arrow("reorder_level")}</Th>
                <Th onClick={() => toggleSort("value")} right>Value{arrow("value")}</Th>
              </tr>
            </thead>
            <tbody>
              {loading && rows.length === 0 ? (
                <tr><td colSpan={5} className="px-3 py-6 text-center text-muted">Loading…</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={5} className="px-3 py-6 text-center text-muted">No products match.</td></tr>
              ) : (
                rows.map((r) => {
                  const p = pmap.get(r.product_id);
                  const src = imageSrc(p?.image_url ?? null);
                  return (
                    <tr key={r.product_id} className="border-t border-line hover:bg-wash">
                      <td className="px-3 py-2">
                        <span className="flex items-center gap-2">
                          {src ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={src} alt="" className="h-6 w-6 rounded border border-line object-cover" />
                          ) : <span className="text-line">🧩</span>}
                          <span>{r.code} — {r.name}</span>
                        </span>
                      </td>
                      <td className="px-3 py-2 text-muted">{r.category ?? "—"}</td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        <span className={r.low ? "font-medium text-red-700 dark:text-red-300" : ""}>
                          {num(r.on_hand)}
                        </span>
                        {r.low && <span className="ml-1 rounded bg-red-500/15 px-1 text-[10px] text-red-700 dark:text-red-300">low</span>}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-muted">
                        {r.reorder_level != null ? num(r.reorder_level) : "—"}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{money2(r.value)}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function Th({ children, onClick, right }: { children: React.ReactNode; onClick: () => void; right?: boolean }) {
  return (
    <th className={`px-3 py-2 font-medium ${right ? "text-right" : ""}`}>
      <button onClick={onClick} className="uppercase tracking-wide hover:text-ink">{children}</button>
    </th>
  );
}
