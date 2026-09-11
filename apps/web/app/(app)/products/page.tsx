"use client";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column } from "@/components/DataTable";
import { money2 } from "@/lib/format";

type Row = Record<string, unknown>;
const columns: Column<Row>[] = [
  { key: "code", header: "Code" },
  { key: "name", header: "Name" },
  { key: "category", header: "Category" },
  { key: "purchase_cost", header: "Cost", render: (r) => money2(r.purchase_cost as number) },
  { key: "selling_price", header: "Price", render: (r) => money2(r.selling_price as number) },
];

export default function ProductsPage() {
  return (
    <div>
      <PageHeader title="Products" subtitle="Product catalogue with cost and price." />
      <ResourceTable<Row> resource="products" columns={columns} />
    </div>
  );
}
