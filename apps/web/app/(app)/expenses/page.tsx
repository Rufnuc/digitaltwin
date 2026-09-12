"use client";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column, type FilterSpec } from "@/components/DataTable";
import { money2 } from "@/lib/format";

type Row = Record<string, unknown>;
const columns: Column<Row>[] = [
  { key: "expense_date", header: "Date", sortable: true },
  { key: "category", header: "Category", sortable: true },
  { key: "description", header: "Description" },
  { key: "amount", header: "Amount", sortable: true, render: (r) => money2(r.amount as number) },
];

const filters: FilterSpec[] = [
  {
    key: "category",
    label: "Category",
    options: ["Rent", "Utilities", "Salaries", "Transport", "Marketing", "Misc"].map((v) => ({
      value: v,
      label: v,
    })),
  },
];

export default function ExpensesPage() {
  return (
    <div>
      <PageHeader title="Expenses" subtitle="Operating expenses by category." />
      <ResourceTable<Row> resource="expenses" columns={columns} filters={filters} />
    </div>
  );
}
