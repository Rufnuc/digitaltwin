"use client";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column } from "@/components/DataTable";
import { money2 } from "@/lib/format";

type Row = Record<string, unknown>;
const columns: Column<Row>[] = [
  { key: "expense_date", header: "Date" },
  { key: "category", header: "Category" },
  { key: "description", header: "Description" },
  { key: "amount", header: "Amount", render: (r) => money2(r.amount as number) },
];

export default function ExpensesPage() {
  return (
    <div>
      <PageHeader title="Expenses" subtitle="Operating expenses by category." />
      <ResourceTable<Row> resource="expenses" columns={columns} />
    </div>
  );
}
