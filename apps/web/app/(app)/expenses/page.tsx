"use client";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column, type FilterSpec, type FormField } from "@/components/DataTable";
import { money2 } from "@/lib/format";

type Row = Record<string, unknown>;

const formFields: FormField[] = [
  { key: "expense_date", label: "Date", type: "date", required: true },
  {
    key: "category",
    label: "Category",
    type: "select",
    required: true,
    options: ["Rent", "Utilities", "Salaries", "Transport", "Marketing", "Misc"].map((v) => ({
      value: v,
      label: v,
    })),
  },
  { key: "description", label: "Description", type: "textarea" },
  { key: "amount", label: "Amount (₦)", type: "number", step: "0.01", required: true },
];
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
      <ResourceTable<Row>
        resource="expenses"
        columns={columns}
        filters={filters}
        formFields={formFields}
        entityLabel="expense"
      />
    </div>
  );
}
