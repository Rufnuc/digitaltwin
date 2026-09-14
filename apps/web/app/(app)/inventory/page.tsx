"use client";
import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column } from "@/components/DataTable";
import { InventoryTabs } from "@/components/InventoryTabs";
import { api, imageSrc } from "@/lib/api";
import { money2 } from "@/lib/format";

type Row = Record<string, unknown>;
interface Prod {
  id: number;
  name: string;
  code: string;
  image_url: string | null;
}

export default function InventoryPage() {
  const [products, setProducts] = useState<Prod[]>([]);

  useEffect(() => {
    api.list<Prod>("products", "?limit=200").then((r) => setProducts(r.items)).catch(() => {});
  }, []);

  const pmap = useMemo(() => {
    const m = new Map<number, Prod>();
    for (const p of products) m.set(p.id, p);
    return m;
  }, [products]);

  const columns: Column<Row>[] = useMemo(
    () => [
      {
        key: "product_id",
        header: "Product",
        sortable: true,
        render: (r) => {
          const p = pmap.get(r.product_id as number);
          const src = imageSrc(p?.image_url ?? null);
          return (
            <span className="flex items-center gap-2">
              {src ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={src} alt="" className="h-6 w-6 rounded border border-line object-cover" />
              ) : (
                <span className="text-line">🧩</span>
              )}
              {p ? `${p.code} — ${p.name}` : `#${r.product_id ?? "—"}`}
            </span>
          );
        },
      },
      { key: "branch_id", header: "Branch", sortable: true },
      { key: "quantity_on_hand", header: "On Hand", sortable: true },
      { key: "safety_stock", header: "Safety Stock", sortable: true },
      { key: "unit_cost", header: "Unit Cost", sortable: true, render: (r) => money2(r.unit_cost as number) },
    ],
    [pmap],
  );

  return (
    <div>
      <PageHeader
        title="Inventory"
        subtitle="Current stock positions. For lot-level tracking with full history, see Stock & Markers."
      />
      <InventoryTabs active="levels" />
      <ResourceTable<Row> resource="inventory" columns={columns} searchable={false} />
    </div>
  );
}
