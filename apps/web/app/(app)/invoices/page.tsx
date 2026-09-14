"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/Shell";
import { Card, ProvenanceBadge } from "@/components/ui";
import { api, getRole, type InvoiceDetail, type InvoiceVersionRow } from "@/lib/api";
import { printInvoice } from "@/lib/printInvoice";
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

  const [viewVersion, setViewVersion] = useState<InvoiceVersionRow | null>(null);

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
              <F label={inv.shipping_note ? `Shipping (${inv.shipping_note})` : "Shipping"} value={money2(inv.shipping)} />
              <F label="Discount" value={money2(inv.discount)} />
              <F label="Total" value={money2(inv.total)} />
              <F label="Verification" value={inv.verification_status} />
              <F label="Version" value={`v${inv.version_no}`} />
              <F label="Raised by" value={inv.created_by ?? "—"} />
              <F label="Last edited by" value={inv.updated_by ?? "—"} />
            </div>

            <div className="mb-4 flex flex-wrap gap-2">
              {canEdit && (
                <button
                  onClick={() => setEditing(true)}
                  className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash"
                >
                  Edit invoice
                </button>
              )}
              <button
                onClick={() => printInvoice(inv, versions)}
                className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash"
              >
                Print / download
              </button>
            </div>

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
                Version history ({versions.length}) — click to view
              </span>
              <ProvenanceBadge origin="REAL" />
            </div>
            <ol className="mt-2 space-y-2">
              {versions.length === 0 && (
                <li className="text-[11px] text-muted">
                  No prior versions recorded (invoice predates version tracking, or is unedited).
                </li>
              )}
              {versions.map((v) => (
                <li key={v.version_no}>
                  <button
                    onClick={() => setViewVersion(v)}
                    className="w-full rounded border border-line p-2 text-left text-sm hover:bg-wash"
                  >
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
                  </button>
                </li>
              ))}
            </ol>

            {editing && (
              <InvoiceEditModal
                inv={inv}
                onClose={() => setEditing(false)}
                onSaved={async () => {
                  setEditing(false);
                  await reload();
                  onChanged();
                }}
              />
            )}
            {viewVersion && (
              <VersionModal
                invoiceNumber={inv.invoice_number}
                version={viewVersion}
                onClose={() => setViewVersion(null)}
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

// ---- Full edit (header + line items) ---------------------------------------
interface EditLine {
  key: number;
  product_id: string;
  description: string;
  quantity: string;
  unit_price: string;
}

function InvoiceEditModal({
  inv,
  onClose,
  onSaved,
}: {
  inv: InvoiceDetail;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [products, setProducts] = useState<{ id: number; name: string; code: string }[]>([]);
  const [number, setNumber] = useState(inv.invoice_number);
  const [date, setDate] = useState(inv.invoice_date);
  const [tax, setTax] = useState(String(inv.tax));
  const [discount, setDiscount] = useState(String(inv.discount));
  const [shipping, setShipping] = useState(String(inv.shipping));
  const [shippingNote, setShippingNote] = useState(inv.shipping_note ?? "");
  const [statusVal, setStatusVal] = useState(inv.verification_status);
  const [note, setNote] = useState("");
  const [lines, setLines] = useState<EditLine[]>(
    inv.lines.map((ln, i) => ({
      key: i,
      product_id: ln.product_id ? String(ln.product_id) : "",
      description: ln.original_description ?? "",
      quantity: String(ln.quantity),
      unit_price: String(ln.unit_price),
    })),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.list<{ id: number; name: string; code: string }>("products", "?limit=200")
      .then((r) => setProducts(r.items))
      .catch(() => {});
  }, []);

  function setLine(key: number, patch: Partial<EditLine>) {
    setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  }
  const subtotal = lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_price) || 0), 0);
  const total = subtotal + (Number(tax) || 0) + (Number(shipping) || 0) - (Number(discount) || 0);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.invoiceUpdate(inv.id, {
        invoice_number: number,
        invoice_date: date,
        verification_status: statusVal,
        tax: Number(tax) || 0,
        discount: Number(discount) || 0,
        shipping: Number(shipping) || 0,
        shipping_note: shippingNote || null,
        change_note: note || "edited",
        lines: lines
          .filter((l) => l.description.trim() || l.product_id)
          .map((l) => ({
            product_id: l.product_id ? Number(l.product_id) : null,
            original_description:
              l.description.trim() ||
              products.find((p) => String(p.id) === l.product_id)?.name ||
              null,
            quantity: Number(l.quantity) || 0,
            unit_price: Number(l.unit_price) || 0,
          })),
      });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  const inp = "w-full rounded border border-line bg-paper px-2 py-1.5 text-sm outline-none focus:border-ink";

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto bg-black/50 p-4" onMouseDown={onClose}>
      <form onMouseDown={(e) => e.stopPropagation()} onSubmit={save} className="w-full max-w-2xl rounded-lg border border-line bg-paper p-4 shadow-xl">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">Edit {inv.invoice_number}</h2>
          <button type="button" onClick={onClose} className="text-muted hover:text-ink">✕</button>
        </div>
        <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <label className="col-span-2 text-xs text-muted">Invoice #
            <input value={number} onChange={(e) => setNumber(e.target.value)} className={inp} />
          </label>
          <label className="text-xs text-muted">Date
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={inp} />
          </label>
          <label className="text-xs text-muted">Status
            <select value={statusVal} onChange={(e) => setStatusVal(e.target.value)} className={inp}>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
        </div>

        <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">Line items</div>
        <div className="space-y-2">
          {lines.map((l) => (
            <div key={l.key} className="grid grid-cols-12 items-center gap-2">
              <select
                value={l.product_id}
                onChange={(e) => {
                  const p = products.find((x) => String(x.id) === e.target.value);
                  setLine(l.key, { product_id: e.target.value, description: p ? p.name : l.description });
                }}
                className={`col-span-12 sm:col-span-5 ${inp}`}
              >
                <option value="">Custom / no product</option>
                {products.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </select>
              <input value={l.description} onChange={(e) => setLine(l.key, { description: e.target.value })} placeholder="Description" className={`col-span-12 sm:col-span-3 ${inp}`} />
              <input type="number" value={l.quantity} onChange={(e) => setLine(l.key, { quantity: e.target.value })} placeholder="Qty" className={`col-span-4 sm:col-span-1 ${inp}`} />
              <input type="number" step="0.01" value={l.unit_price} onChange={(e) => setLine(l.key, { unit_price: e.target.value })} placeholder="Unit ₦" className={`col-span-6 sm:col-span-2 ${inp}`} />
              <button type="button" onClick={() => setLines((ls) => ls.filter((x) => x.key !== l.key))} className="col-span-2 text-muted hover:text-red-700 sm:col-span-1" aria-label="Remove">✕</button>
            </div>
          ))}
        </div>
        <button type="button" onClick={() => setLines((ls) => [...ls, { key: Date.now(), product_id: "", description: "", quantity: "1", unit_price: "" }])} className="mt-2 text-xs text-muted underline decoration-dotted">+ Add line</button>

        <div className="mt-3 grid grid-cols-3 gap-3 sm:max-w-lg">
          <label className="text-xs text-muted">Tax (₦)
            <input type="number" step="0.01" value={tax} onChange={(e) => setTax(e.target.value)} className={inp} />
          </label>
          <label className="text-xs text-muted">Discount (₦)
            <input type="number" step="0.01" value={discount} onChange={(e) => setDiscount(e.target.value)} className={inp} />
          </label>
          <label className="text-xs text-muted">Shipping (₦)
            <input type="number" step="0.01" value={shipping} onChange={(e) => setShipping(e.target.value)} className={inp} />
          </label>
        </div>
        {(Number(shipping) || 0) > 0 && (
          <label className="mt-2 block text-xs text-muted">Shipping is for
            <input value={shippingNote} onChange={(e) => setShippingNote(e.target.value)} placeholder="e.g. delivery, courier" className={inp} />
          </label>
        )}
        <div className="mt-2 text-right text-sm font-semibold">Total: {money2(total)}</div>

        <label className="mt-3 block text-xs text-muted">Reason for change
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="why you're editing" className={inp} />
        </label>

        {error && <div className="mt-2 text-sm text-red-700">{error}</div>}
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash">Cancel</button>
          <button type="submit" disabled={busy} className="rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper disabled:opacity-50">
            {busy ? "Saving…" : "Save new version"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ---- Read-only view of a past version --------------------------------------
function VersionModal({
  invoiceNumber,
  version,
  onClose,
}: {
  invoiceNumber: string;
  version: InvoiceVersionRow;
  onClose: () => void;
}) {
  const s = version.snapshot as {
    total?: number; subtotal?: number; tax?: number; discount?: number;
    shipping?: number; shipping_note?: string | null;
    verification_status?: string; invoice_date?: string;
    lines?: { description?: string | null; quantity?: number; unit_price?: number; line_total?: number }[];
  };
  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto bg-black/50 p-4" onMouseDown={onClose}>
      <div onMouseDown={(e) => e.stopPropagation()} className="w-full max-w-lg rounded-lg border border-line bg-paper p-4 shadow-xl">
        <div className="mb-1 flex items-center justify-between">
          <h2 className="text-base font-semibold">{invoiceNumber} — version {version.version_no}</h2>
          <button onClick={onClose} className="text-muted hover:text-ink">✕</button>
        </div>
        <div className="mb-3 text-[11px] text-muted">
          {version.change_note ?? "—"} · {version.changed_by ?? "—"}
          {version.changed_at ? ` · ${new Date(version.changed_at).toLocaleString()}` : ""}
          <span className="ml-2 rounded bg-muted/15 px-1 py-0.5">immutable</span>
        </div>
        <div className="mb-3 grid grid-cols-2 gap-2 text-sm">
          <F label="Date" value={s.invoice_date ?? "—"} />
          <F label="Verification" value={s.verification_status ?? "—"} />
          <F label="Subtotal" value={money2(s.subtotal ?? 0)} />
          <F label="Tax" value={money2(s.tax ?? 0)} />
          <F label={s.shipping_note ? `Shipping (${s.shipping_note})` : "Shipping"} value={money2(s.shipping ?? 0)} />
          <F label="Discount" value={money2(s.discount ?? 0)} />
          <F label="Total" value={money2(s.total ?? 0)} />
        </div>
        <div className="text-xs font-medium uppercase tracking-wide text-muted">Line items (as at this version)</div>
        <table className="mt-1 w-full text-sm">
          <tbody>
            {(s.lines ?? []).map((ln, i) => (
              <tr key={i} className="border-t border-line tabular-nums">
                <td className="py-1">{ln.description ?? "—"}</td>
                <td className="py-1 text-right">{ln.quantity} ×</td>
                <td className="py-1 text-right">{money2(ln.unit_price ?? 0)}</td>
                <td className="py-1 text-right font-medium">{money2(ln.line_total ?? 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
