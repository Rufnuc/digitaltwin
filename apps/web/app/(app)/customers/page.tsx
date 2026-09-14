"use client";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column, type FilterSpec, type FormField } from "@/components/DataTable";
import { money } from "@/lib/format";

const STATUS = ["ACTIVE", "INACTIVE", "PROSPECT", "ARCHIVED"];
const TYPES = ["RETAIL", "WHOLESALE", "TRADE", "OTHER"];

const formFields: FormField[] = [
  { key: "code", label: "Code", required: true, placeholder: "CUS-0001" },
  { key: "name", label: "Name", required: true },
  { key: "location", label: "Location" },
  { key: "contact_email", label: "Email" },
  { key: "contact_phone", label: "Phone" },
  { key: "customer_type", label: "Type", type: "select", options: TYPES.map((v) => ({ value: v, label: v })) },
  { key: "status", label: "Status", type: "select", options: STATUS.map((v) => ({ value: v, label: v })) },
];

type Row = Record<string, unknown>;
const columns: Column<Row>[] = [
  { key: "code", header: "Code", sortable: true },
  { key: "name", header: "Name", sortable: true },
  { key: "location", header: "Location", sortable: true },
  { key: "customer_type", header: "Type", sortable: true },
  { key: "status", header: "Status", sortable: true },
  {
    key: "lifetime_revenue",
    header: "Lifetime Rev.",
    sortable: true,
    render: (r) => money(r.lifetime_revenue as number),
  },
];

const filters: FilterSpec[] = [
  {
    key: "status",
    label: "Status",
    options: ["ACTIVE", "INACTIVE", "PROSPECT", "ARCHIVED"].map((v) => ({ value: v, label: v })),
  },
  {
    key: "customer_type",
    label: "Type",
    options: ["RETAIL", "WHOLESALE", "TRADE", "OTHER"].map((v) => ({ value: v, label: v })),
  },
];

export default function CustomersPage() {
  return (
    <div>
      <PageHeader title="Customers" subtitle="Customer master records." />
      <ResourceTable<Row>
        resource="customers"
        columns={columns}
        filters={filters}
        formFields={formFields}
        entityLabel="customer"
      />
    </div>
  );
}
