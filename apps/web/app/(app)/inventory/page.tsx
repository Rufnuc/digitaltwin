"use client";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column } from "@/components/DataTable";
import { InventoryTabs } from "@/components/InventoryTabs";
import { money2 } from "@/lib/format";

type Row = Record<string, unknown>;
const columns: Column<Row>[] = [
  { key: "product_id", header: "Product ID", sortable: true },
  { key: "branch_id", header: "Branch", sortable: true },
  { key: "quantity_on_hand", header: "On Hand", sortable: true },
  { key: "safety_stock", header: "Safety Stock", sortable: true },
  { key: "unit_cost", header: "Unit Cost", sortable: true, render: (r) => money2(r.unit_cost as number) },
];

export default function InventoryPage() {
  return (
    <div>
      <PageHeader title="Inventory" subtitle="Current stock positions." />
      <InventoryTabs active="levels" />
      <ResourceTable<Row> resource="inventory" columns={columns} searchable={false} />
    </div>
  );
}
