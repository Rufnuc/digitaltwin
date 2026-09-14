"use client";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column, type FilterSpec, type FormField } from "@/components/DataTable";

type Row = Record<string, unknown>;

const formFields: FormField[] = [
  { key: "code", label: "Code", required: true, placeholder: "SUP-001" },
  { key: "name", label: "Name", required: true },
  { key: "location", label: "Location", placeholder: "Import — China / Lagos" },
  { key: "currency", label: "Currency", placeholder: "NGN / USD / CNY" },
  { key: "payment_terms", label: "Payment terms" },
  { key: "lead_time_days", label: "Lead time (days)", type: "number" },
  {
    key: "status",
    label: "Status",
    type: "select",
    options: ["ACTIVE", "INACTIVE", "ARCHIVED"].map((v) => ({ value: v, label: v })),
  },
];
const columns: Column<Row>[] = [
  { key: "code", header: "Code", sortable: true },
  { key: "name", header: "Name", sortable: true },
  { key: "location", header: "Location", sortable: true },
  { key: "currency", header: "Currency", sortable: true },
  { key: "lead_time_days", header: "Lead (days)", sortable: true },
  { key: "reliability_score", header: "Reliability", sortable: true },
];

const filters: FilterSpec[] = [
  {
    key: "status",
    label: "Status",
    options: ["ACTIVE", "INACTIVE", "ARCHIVED"].map((v) => ({ value: v, label: v })),
  },
];

export default function SuppliersPage() {
  return (
    <div>
      <PageHeader title="Suppliers" subtitle="Supplier records and reliability." />
      <ResourceTable<Row>
        resource="suppliers"
        columns={columns}
        filters={filters}
        formFields={formFields}
        entityLabel="supplier"
      />
    </div>
  );
}
