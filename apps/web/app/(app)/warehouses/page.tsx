"use client";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column, type FilterSpec, type FormField } from "@/components/DataTable";

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
      { value: "warehouse", label: "Warehouse" },
      { value: "shop", label: "Shop / Counter" },
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
      <ResourceTable<Row>
        resource="warehouses"
        columns={columns}
        filters={filters}
        formFields={formFields}
        entityLabel="warehouse"
        writeRole="MANAGER"
        showProvenance={false}
      />
    </div>
  );
}
