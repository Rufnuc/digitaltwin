"use client";
import { useCallback, useEffect, useState } from "react";
import { api, type Waybill } from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card } from "@/components/ui";

const naira = (n: number | null | undefined) =>
  n == null ? "—" : "₦" + Math.round(n).toLocaleString("en-NG");
const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("en-NG", { dateStyle: "medium", timeStyle: "short" }) : "—";

const STATUS_STYLE: Record<string, string> = {
  PENDING: "bg-yellow-500/15 text-yellow-700 dark:text-yellow-300 border-yellow-500/30",
  DISPATCHED: "bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/30",
  DELIVERED: "bg-green-500/15 text-green-700 dark:text-green-300 border-green-500/30",
  CANCELLED: "bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/30",
};
const STATUSES = ["PENDING", "DISPATCHED", "DELIVERED", "CANCELLED"];

function Badge({ status }: { status: string }) {
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[11px] font-medium ${STATUS_STYLE[status] ?? ""}`}>
      {status}
    </span>
  );
}

export default function WaybillsPage() {
  const [rows, setRows] = useState<Waybill[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Waybill | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (statusFilter) params.set("status", statusFilter);
    if (q) params.set("q", q);
    const qs = params.toString();
    api
      .listWaybills(qs ? `?${qs}` : "")
      .then((r) => setRows(r.items))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [statusFilter, q]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <PageHeader
        title="Waybills"
        subtitle="Track how goods leave — each waybill is tied to an invoice and records the driver, who's collecting, destination and dispatch time."
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search waybill #…"
          className="w-48 rounded border border-line bg-paper px-3 py-1.5 text-sm outline-none focus:border-ink"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded border border-line bg-paper px-3 py-1.5 text-sm"
        >
          <option value="">Status: all</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <button
          onClick={() => setCreating(true)}
          className="ml-auto rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper"
        >
          + New waybill
        </button>
      </div>

      <Card className="overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="border-b border-line text-left text-xs text-muted">
            <tr>
              <th className="px-3 py-2">Waybill #</th>
              <th className="px-3 py-2">Invoice</th>
              <th className="px-3 py-2">Customer</th>
              <th className="px-3 py-2">Destination</th>
              <th className="px-3 py-2">Apprentice</th>
              <th className="px-3 py-2">Dispatched</th>
              <th className="px-3 py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={7} className="px-3 py-6 text-center text-muted">Loading…</td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-6 text-center text-muted">No waybills yet.</td></tr>
            )}
            {rows.map((w) => (
              <tr
                key={w.id}
                onClick={() => setSelected(w)}
                className="cursor-pointer border-t border-line hover:bg-wash"
              >
                <td className="px-3 py-2 font-medium">{w.waybill_number}</td>
                <td className="px-3 py-2">{w.invoice_number ?? `#${w.invoice_id}`}</td>
                <td className="px-3 py-2">{w.customer_name ?? "—"}</td>
                <td className="px-3 py-2">{w.destination ?? "—"}</td>
                <td className="px-3 py-2">{w.apprentice_name ?? "—"}</td>
                <td className="px-3 py-2 text-muted">{when(w.dispatched_at)}</td>
                <td className="px-3 py-2"><Badge status={w.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {selected && (
        <WaybillDrawer
          waybill={selected}
          onClose={() => setSelected(null)}
          onSaved={(w) => {
            setSelected(w);
            load();
          }}
        />
      )}
      {creating && (
        <NewWaybillModal
          onClose={() => setCreating(false)}
          onCreated={(w) => {
            setCreating(false);
            setSelected(w);
            load();
          }}
        />
      )}
    </div>
  );
}

function Field({ label, value, onChange, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] uppercase tracking-wide text-muted">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded border border-line bg-paper px-2 py-1.5 text-sm outline-none focus:border-ink"
      />
    </label>
  );
}

function WaybillDrawer({ waybill, onClose, onSaved }: {
  waybill: Waybill; onClose: () => void; onSaved: (w: Waybill) => void;
}) {
  const [w, setW] = useState(waybill);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: keyof Waybill) => (v: string) => setW({ ...w, [k]: v });

  async function save(extra: Partial<Waybill> = {}) {
    setBusy(true);
    setErr(null);
    try {
      const updated = await api.updateWaybill(w.id, {
        apprentice_name: w.apprentice_name, transport_company: w.transport_company,
        driver_phone: w.driver_phone, vehicle_info: w.vehicle_info, station: w.station,
        receiver_name: w.receiver_name, receiver_phone: w.receiver_phone,
        destination: w.destination, notes: w.notes,
        ...extra,
      });
      setW(updated);
      onSaved(updated);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-line bg-paper p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-lg font-semibold">{w.waybill_number}</h2>
          <Badge status={w.status} />
          <button onClick={onClose} className="ml-auto text-muted hover:text-ink">✕</button>
        </div>

        <div className="mb-3 rounded border border-line bg-wash p-2.5 text-sm">
          <div className="flex justify-between">
            <span className="text-muted">Invoice</span>
            <span className="font-medium">{w.invoice_number ?? `#${w.invoice_id}`}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted">Customer</span>
            <span>{w.customer_name ?? "—"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted">Invoice total</span>
            <span>{naira(w.invoice_total)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted">Dispatched</span>
            <span>{when(w.dispatched_at)}</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2.5">
          <Field label="Apprentice (took to park)" value={w.apprentice_name ?? ""} onChange={set("apprentice_name")} />
          <Field label="Transport company / no." value={w.transport_company ?? ""} onChange={set("transport_company")} />
          <Field label="Driver / company phone" value={w.driver_phone ?? ""} onChange={set("driver_phone")} />
          <Field label="Vehicle type & plate" value={w.vehicle_info ?? ""} onChange={set("vehicle_info")} placeholder="e.g. Sienna, ABC-123-XY" />
          <Field label="Station / park" value={w.station ?? ""} onChange={set("station")} />
          <Field label="Destination" value={w.destination ?? ""} onChange={set("destination")} />
          <Field label="Picked up by" value={w.receiver_name ?? ""} onChange={set("receiver_name")} />
          <Field label="Collector phone" value={w.receiver_phone ?? ""} onChange={set("receiver_phone")} />
        </div>
        <label className="mt-2.5 block">
          <span className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Special instructions</span>
          <textarea
            value={w.notes ?? ""}
            onChange={(e) => setW({ ...w, notes: e.target.value })}
            rows={2}
            className="w-full rounded border border-line bg-paper px-2 py-1.5 text-sm outline-none focus:border-ink"
          />
        </label>

        {err && <div className="mt-2 text-sm text-red-700">{err}</div>}

        <div className="mt-3 flex flex-wrap gap-2">
          <button onClick={() => save()} disabled={busy}
            className="rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper disabled:opacity-40">
            {busy ? "Saving…" : "Save details"}
          </button>
          {w.status === "PENDING" && (
            <button onClick={() => save({ status: "DISPATCHED" })} disabled={busy}
              className="rounded border border-blue-500/40 px-3 py-1.5 text-sm text-blue-700 hover:bg-blue-500/10">
              Mark dispatched
            </button>
          )}
          {w.status === "DISPATCHED" && (
            <button onClick={() => save({ status: "DELIVERED" })} disabled={busy}
              className="rounded border border-green-500/40 px-3 py-1.5 text-sm text-green-700 hover:bg-green-500/10">
              Mark delivered
            </button>
          )}
          <button onClick={() => printWaybill(w)}
            className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash">
            Print
          </button>
          {w.status !== "CANCELLED" && w.status !== "DELIVERED" && (
            <button onClick={() => save({ status: "CANCELLED" })} disabled={busy}
              className="ml-auto rounded border border-red-500/40 px-3 py-1.5 text-sm text-red-700 hover:bg-red-500/10">
              Cancel
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function NewWaybillModal({ onClose, onCreated }: {
  onClose: () => void; onCreated: (w: Waybill) => void;
}) {
  const [invoiceNo, setInvoiceNo] = useState("");
  const [matches, setMatches] = useState<{ id: number; invoice_number: string; customer_name?: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function search() {
    setErr(null);
    try {
      const r = await api.list<{ id: number; invoice_number: string; customer_name?: string }>(
        "invoices", `?q=${encodeURIComponent(invoiceNo)}&limit=10`);
      setMatches(r.items);
      if (r.items.length === 0) setErr("No invoice found for that number.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Search failed");
    }
  }

  async function create(invoiceId: number) {
    setBusy(true);
    setErr(null);
    try {
      onCreated(await api.createWaybill({ invoice_id: invoiceId }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not create waybill");
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-lg border border-line bg-paper p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center">
          <h2 className="text-lg font-semibold">New waybill</h2>
          <button onClick={onClose} className="ml-auto text-muted hover:text-ink">✕</button>
        </div>
        <p className="mb-2 text-sm text-muted">Find the invoice this dispatch is for.</p>
        <div className="flex gap-2">
          <input
            value={invoiceNo}
            onChange={(e) => setInvoiceNo(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && search()}
            placeholder="Invoice number…"
            className="flex-1 rounded border border-line bg-paper px-2 py-1.5 text-sm outline-none focus:border-ink"
          />
          <button onClick={search} className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash">
            Search
          </button>
        </div>
        {err && <div className="mt-2 text-sm text-red-700">{err}</div>}
        <div className="mt-2 space-y-1">
          {matches.map((m) => (
            <button
              key={m.id}
              disabled={busy}
              onClick={() => create(m.id)}
              className="flex w-full items-center justify-between rounded border border-line px-2 py-1.5 text-left text-sm hover:bg-wash disabled:opacity-40"
            >
              <span className="font-medium">{m.invoice_number}</span>
              <span className="text-muted">{m.customer_name ?? ""}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// A printable waybill in a new window — the copy the driver carries.
function printWaybill(w: Waybill) {
  const row = (k: string, v: string | null | undefined) =>
    `<tr><td style="padding:4px 10px;color:#666">${k}</td><td style="padding:4px 10px;font-weight:600">${v ?? "—"}</td></tr>`;
  const html = `<!doctype html><html><head><title>${w.waybill_number}</title>
<style>body{font-family:system-ui,Arial,sans-serif;padding:32px;color:#111}
h1{font-size:20px;margin:0 0 4px} .sub{color:#666;margin-bottom:16px}
table{border-collapse:collapse;width:100%;max-width:520px}
td{border-bottom:1px solid #eee;font-size:14px}
.sign{margin-top:48px;display:flex;justify-content:space-between;max-width:520px}
.sign div{border-top:1px solid #333;padding-top:6px;width:45%;font-size:12px;color:#666}</style></head>
<body>
<h1>WAYBILL ${w.waybill_number}</h1>
<div class="sub">Status: ${w.status}${w.dispatched_at ? " · Dispatched " + when(w.dispatched_at) : ""}</div>
<table>
${row("Invoice", w.invoice_number ?? "#" + w.invoice_id)}
${row("Customer", w.customer_name)}
${row("Apprentice", w.apprentice_name)}
${row("Transport company", (w.transport_company ?? "") + (w.driver_phone ? " · " + w.driver_phone : ""))}
${row("Vehicle", w.vehicle_info)}
${row("Station / park", w.station)}
${row("Destination", w.destination)}
${row("Picked up by", (w.receiver_name ?? "") + (w.receiver_phone ? " · " + w.receiver_phone : ""))}
${row("Special instructions", w.notes)}
</table>
<div class="sign"><div>Dispatched by / sign</div><div>Received by / sign</div></div>
</body></html>`;
  const win = window.open("", "_blank", "width=640,height=800");
  if (!win) return;
  win.document.write(html);
  win.document.close();
  win.focus();
  win.print();
}
