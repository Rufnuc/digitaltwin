"use client";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column, type FilterSpec } from "@/components/DataTable";
import { money2 } from "@/lib/format";

type Row = Record<string, unknown>;
const columns: Column<Row>[] = [
  { key: "code", header: "Code", sortable: true },
  { key: "name", header: "Name", sortable: true },
  { key: "category", header: "Category", sortable: true },
  { key: "purchase_cost", header: "Cost", sortable: true, render: (r) => money2(r.purchase_cost as number) },
  { key: "selling_price", header: "Price", sortable: true, render: (r) => money2(r.selling_price as number) },
];

const filters: FilterSpec[] = [
  {
    key: "category",
    label: "Category",
    options: ["Engine", "Brakes", "Electrical", "Suspension", "Filters", "Body"].map((v) => ({
      value: v,
      label: v,
    })),
  },
  {
    key: "is_active",
    label: "Active",
    options: [
      { value: "true", label: "Active" },
      { value: "false", label: "Inactive" },
    ],
  },
];

export default function ProductsPage() {
  return (
    <div>
      <PageHeader title="Products" subtitle="Product catalogue with cost and price." />
      <ResourceTable<Row> resource="products" columns={columns} filters={filters} />
    </div>
  );
}
