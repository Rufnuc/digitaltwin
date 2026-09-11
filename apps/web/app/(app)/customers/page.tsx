"use client";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column } from "@/components/DataTable";
import { money } from "@/lib/format";

type Row = Record<string, unknown>;
const columns: Column<Row>[] = [
  { key: "code", header: "Code" },
  { key: "name", header: "Name" },
  { key: "location", header: "Location" },
  { key: "customer_type", header: "Type" },
  { key: "status", header: "Status" },
  { key: "lifetime_revenue", header: "Lifetime Rev.", render: (r) => money(r.lifetime_revenue as number) },
];

export default function CustomersPage() {
  return (
    <div>
      <PageHeader title="Customers" subtitle="Customer master records." />
      <ResourceTable<Row> resource="customers" columns={columns} />
    </div>
  );
}
