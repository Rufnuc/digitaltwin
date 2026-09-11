"use client";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column } from "@/components/DataTable";
import { money2 } from "@/lib/format";

type Row = Record<string, unknown>;
const columns: Column<Row>[] = [
  { key: "invoice_number", header: "Invoice #" },
  { key: "invoice_date", header: "Date" },
  { key: "subtotal", header: "Subtotal", render: (r) => money2(r.subtotal as number) },
  { key: "tax", header: "Tax", render: (r) => money2(r.tax as number) },
  { key: "total", header: "Total", render: (r) => money2(r.total as number) },
  { key: "verification_status", header: "Verification" },
];

export default function InvoicesPage() {
  return (
    <div>
      <PageHeader
        title="Invoices"
        subtitle="Sales invoices. Arithmetic is validated on entry; inconsistencies are flagged NEEDS_REVIEW, never silently corrected."
      />
      <ResourceTable<Row> resource="invoices" columns={columns} searchable={false} />
    </div>
  );
}
