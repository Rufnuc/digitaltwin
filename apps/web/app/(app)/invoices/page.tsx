"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/Shell";
import { Card, ProvenanceBadge } from "@/components/ui";
import { EntityForm, type FormField } from "@/components/EntityForm";
import { api, getRole, type InvoiceDetail, type InvoiceVersionRow } from "@/lib/api";
import { money2 } from "@/lib/format";
import { roleAtLeast } from "@/lib/roles";

interface Row {
  id: number;
  invoice_number: string;
  invoice_date: string;
  subtotal: number;
  tax: number;
  total: number;
  verification_status: string;
  created_by: string | null;
  version_no: number;
}

const STATUSES = ["VERIFIED", "NEEDS_REVIEW", "AI_EXTRACTED", "UNVERIFIED"];

export default function InvoicesPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("id");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const limit = 25;

  const canSell = roleAtLeast(getRole(), "STAFF");

  const load = useCallback(async () => {
    try {
      const parts = [`limit=${limit}`, `offset=${offset}`, `sort=${sort}`, `sort_dir=${sortDir}`];
      if (q) parts.push(`q=${encodeURIComponent(q)}`);
      if (status) parts.push(`verification_status=${status}`);
      const r = await api.list<Row>("invoices", `?${parts.join("&")}`);
      setRows(r.items);
      setTotal(r.total);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }, [offset, q, status, sort, sortDir]);

  useEffect(() => {
    load();
  }, [load]);

  function toggleSort(key: string) {
    setOffset(0);
    if (sort === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSort(key);
      setSortDir("asc");
    }
  }

  const sortMark = (key: string) => (sort === key ? (sortDir === "asc" ? "▲" : "▼") : "↕");

  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <PageHeader
          title="Invoices & Sales"
          subtitle="Every invoice records who raised it and keeps a version history of every edit. Click a row to see details and history."
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

      {error && <div className="mb-3 text-sm text-red-700">Error: {error}</div>}

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          value={q}
          onChange={(e) => {
            setOffset(0);
            setQ(e.target.value);
          }}
          placeholder="Search invoice #…"
          className="w-56 rounded border border-line bg-paper px-3 py-1.5 text-sm outline-none focus:border-ink"
        />
        <select
          value={status}
          onChange={(e) => {
            setOffset(0);
            setStatus(e.target.value);
          }}
          className="rounded border border-line bg-paper px-2 py-1.5 text-sm"
        >
          <option value="">Status: all</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        {(q || status || sort !== "id") && (
          <button
            onClick={() => {
              setQ("");
              setStatus("");
              setSort("id");
              setSortDir("desc");
              setOffset(0);
            }}
            className="text-xs text-muted underline decoration-dotted"
          >
            Clear
          </button>
        )}
      </div>

      <Card className="overflow-x-auto p-0">
        <table className="min-w-full text-sm">
          <thead className="bg-wash text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              {[
                ["invoice_number", "Invoice #"],
                ["invoice_date", "Date"],
                ["total", "Total"],
              ].map(([key, label]) => (
                <th key={key} className="px-3 py-2 font-medium">
                  <button onClick={() => toggleSort(key)} className="inline-flex items-center gap-1 hover:text-ink">
                    {label} <span className="text-[9px]">{sortMark(key)}</span>
                  </button>
                </th>
              ))}
              <th className="px-3 py-2 font-medium">Verification</th>
              <th className="px-3 py-2 font-medium">Raised by</th>
              <th className="px-3 py-2 font-medium">Ver.</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td className="px-3 py-6 text-muted" colSpan={6}>
                  No invoices.
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => setSelected(r.id)}
                  className="cursor-pointer border-t border-line tabular-nums hover:bg-wash"
                >
                  <td className="px-3 py-2 font-medium">{r.invoice_number}</td>
                  <td className="px-3 py-2">{r.invoice_date}</td>
                  <td className="px-3 py-2">{money2(r.total)}</td>
                  <td className="px-3 py-2">
                    <span className={r.verification_status === "NEEDS_REVIEW" ? "text-yellow-700 dark:text-yellow-300" : ""}>
                      {r.verification_status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-muted">{r.created_by ?? "—"}</td>
                  <td className="px-3 py-2 text-muted">v{r.version_no}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>

      <div className="mt-3 flex items-center justify-between text-xs text-muted">
        <span>
          {total} invoice{total === 1 ? "" : "s"}
        </span>
        <div className="flex gap-2">
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - limit))}
            className="rounded border border-line px-2 py-1 disabled:opacity-40"
          >
            Prev
          </button>
          <button
            disabled={offset + limit >= total}
            onClick={() => setOffset(offset + limit)}
            className="rounded border border-line px-2 py-1 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>

      {selected != null && (
        <InvoiceDrawer id={selected} onClose={() => setSelected(null)} onChanged={load} />
      )}
    </div>
  );
}

function InvoiceDrawer({
  id,
  onClose,
  onChanged,
}: {
  id: number;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [inv, setInv] = useState<InvoiceDetail | null>(null);
  const [versions, setVersions] = useState<InvoiceVersionRow[]>([]);
  const [editing, setEditing] = useState(false);
  const canEdit = roleAtLeast(getRole(), "MANAGER");

  const reload = useCallback(async () => {
    const [d, v] = await Promise.all([api.invoiceDetail(id), api.invoiceVersions(id)]);
    setInv(d);
    setVersions(v.items);
  }, [id]);

  useEffect(() => {
    reload();
  }, [reload]);

  const editFields: FormField[] = [
    { key: "invoice_date", label: "Date", type: "date" },
    { key: "tax", label: "Tax (₦)", type: "number", step: "0.01" },
    { key: "discount", label: "Discount (₦)", type: "number", step: "0.01" },
    {
      key: "verification_status",
      label: "Verification",
      type: "select",
      options: STATUSES.map((s) => ({ value: s, label: s })),
    },
    { key: "change_note", label: "Reason for change", placeholder: "why you're editing" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onMouseDown={onClose}>
      <div
        className="h-full w-full max-w-md overflow-y-auto border-l border-line bg-paper p-4 shadow-xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        {!inv ? (
          <div className="text-sm text-muted">Loading…</div>
        ) : (
          <>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-semibold">{inv.invoice_number}</h2>
              <button onClick={onClose} aria-label="Close" className="text-muted hover:text-ink">
                ✕
              </button>
            </div>

            <div className="mb-4 grid grid-cols-2 gap-2 text-sm">
              <F label="Customer" value={inv.customer_name ?? "Walk-in"} />
              <F label="Date" value={inv.invoice_date} />
              <F label="Subtotal" value={money2(inv.subtotal)} />
              <F label="Tax" value={money2(inv.tax)} />
              <F label="Discount" value={money2(inv.discount)} />
              <F label="Total" value={money2(inv.total)} />
              <F label="Verification" value={inv.verification_status} />
              <F label="Version" value={`v${inv.version_no}`} />
              <F label="Raised by" value={inv.created_by ?? "—"} />
              <F label="Last edited by" value={inv.updated_by ?? "—"} />
            </div>

            {canEdit && (
              <button
                onClick={() => setEditing(true)}
                className="mb-4 rounded border border-line px-3 py-1.5 text-sm hover:bg-wash"
              >
                Edit invoice
              </button>
            )}

            <div className="text-xs font-medium uppercase tracking-wide text-muted">Line items</div>
            <table className="mb-4 mt-1 w-full text-sm">
              <tbody>
                {inv.lines.map((ln, i) => (
                  <tr key={i} className="border-t border-line tabular-nums">
                    <td className="py-1">{ln.original_description ?? `Product #${ln.product_id ?? "—"}`}</td>
                    <td className="py-1 text-right">{ln.quantity} ×</td>
                    <td className="py-1 text-right">{money2(ln.unit_price)}</td>
                    <td className="py-1 text-right font-medium">{money2(ln.line_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wide text-muted">
                Version history ({versions.length})
              </span>
              <ProvenanceBadge origin="REAL" />
            </div>
            <ol className="mt-2 space-y-2">
              {versions.map((v) => (
                <li key={v.version_no} className="rounded border border-line p-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">v{v.version_no}</span>
                    <span className="tabular-nums">
                      {money2((v.snapshot.total as number) ?? 0)}
                    </span>
                  </div>
                  <div className="text-[11px] text-muted">
                    {v.change_note ?? "—"} · {v.changed_by ?? "—"}
                    {v.changed_at ? ` · ${new Date(v.changed_at).toLocaleString()}` : ""}
                  </div>
                </li>
              ))}
            </ol>

            {editing && (
              <EntityForm
                title={`Edit ${inv.invoice_number}`}
                submitLabel="Save version"
                fields={editFields}
                initial={{
                  invoice_date: inv.invoice_date,
                  tax: inv.tax,
                  discount: inv.discount,
                  verification_status: inv.verification_status,
                }}
                onClose={() => setEditing(false)}
                onSubmit={async (vals) => {
                  await api.invoiceUpdate(id, vals);
                  await reload();
                  onChanged();
                }}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

function F({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div className="text-sm">{value}</div>
    </div>
  );
}
