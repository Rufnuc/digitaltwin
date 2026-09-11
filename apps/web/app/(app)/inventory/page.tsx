"use client";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column } from "@/components/DataTable";
import { money2 } from "@/lib/format";

type Row = Record<string, unknown>;
const columns: Column<Row>[] = [
  { key: "product_id", header: "Product ID" },
  { key: "branch_id", header: "Branch" },
  { key: "quantity_on_hand", header: "On Hand" },
  { key: "safety_stock", header: "Safety Stock" },
  { key: "unit_cost", header: "Unit Cost", render: (r) => money2(r.unit_cost as number) },
];

export default function InventoryPage() {
  return (
    <div>
      <PageHeader title="Inventory" subtitle="Current stock positions." />
      <ResourceTable<Row> resource="inventory" columns={columns} searchable={false} />
    </div>
  );
}
