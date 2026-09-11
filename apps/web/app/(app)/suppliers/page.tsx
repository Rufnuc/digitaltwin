"use client";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column } from "@/components/DataTable";

type Row = Record<string, unknown>;
const columns: Column<Row>[] = [
  { key: "code", header: "Code" },
  { key: "name", header: "Name" },
  { key: "location", header: "Location" },
  { key: "currency", header: "Currency" },
  { key: "lead_time_days", header: "Lead (days)" },
  { key: "reliability_score", header: "Reliability" },
];

export default function SuppliersPage() {
  return (
    <div>
      <PageHeader title="Suppliers" subtitle="Supplier records and reliability." />
      <ResourceTable<Row> resource="suppliers" columns={columns} />
    </div>
  );
}
