"use client";
import Link from "next/link";
import { PageHeader } from "@/components/Shell";
import { ResourceTable, type Column } from "@/components/DataTable";
import { getRole } from "@/lib/api";
import { money2 } from "@/lib/format";
import { roleAtLeast } from "@/lib/roles";

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
  const canSell = roleAtLeast(getRole(), "STAFF");
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <PageHeader
          title="Invoices"
          subtitle="Sales invoices. Arithmetic is validated on entry; inconsistencies are flagged NEEDS_REVIEW, never silently corrected."
        />
        {canSell && (
          <Link
            href="/sell"
            className="shrink-0 rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper"
          >
            + New Sale
          </Link>
        )}
      </div>
      <ResourceTable<Row> resource="invoices" columns={columns} searchable={false} />
    </div>
  );
}
