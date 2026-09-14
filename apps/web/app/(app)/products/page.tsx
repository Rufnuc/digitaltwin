"use client";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column, type FilterSpec, type FormField } from "@/components/DataTable";
import { money2 } from "@/lib/format";

type Row = Record<string, unknown>;

const formFields: FormField[] = [
  { key: "code", label: "Code", required: true, placeholder: "PRD-0001" },
  { key: "name", label: "Name", required: true },
  { key: "part_number", label: "Part number" },
  { key: "category", label: "Category" },
  { key: "manufacturer", label: "Manufacturer" },
  { key: "purchase_cost", label: "Purchase cost (₦)", type: "number", step: "0.01" },
  { key: "selling_price", label: "Selling price (₦)", type: "number", step: "0.01" },
  { key: "reorder_level", label: "Reorder level", type: "number" },
  { key: "lead_time_days", label: "Lead time (days)", type: "number" },
];
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
      <ResourceTable<Row>
        resource="products"
        columns={columns}
        filters={filters}
        formFields={formFields}
        entityLabel="product"
      />
    </div>
  );
}
