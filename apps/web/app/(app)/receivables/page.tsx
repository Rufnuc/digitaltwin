"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  newIdempotencyKey,
  type ReceivablesSummary,
  type OverdueInvoice,
  type OverdueList,
} from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card } from "@/components/ui";

// Money owed to the business: what's outstanding, how much is overdue, an aging
// breakdown, the biggest debtors, and the overdue invoices to chase — with a
// quick way to record a payment as it comes in. (Accounts receivable.)

const naira = (n: number | null | undefined) =>
  n == null ? "—" : "₦" + Math.round(n).toLocaleString("en-NG");

const AGING_LABEL: Record<string, string> = {
  current: "Not due yet",
  "1-30": "1–30 days",
  "31-60": "31–60 days",
  "61-90": "61–90 days",
  "90+": "90+ days",
};

export default function ReceivablesPage() {
  const router = useRouter();
  const [summary, setSummary] = useState<ReceivablesSummary | null>(null);
  const [overdue, setOverdue] = useState<OverdueList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [payFor, setPayFor] = useState<OverdueInvoice | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, o] = await Promise.all([api.receivablesSummary(), api.overdueReceivables()]);
      setSummary(s);
      setOverdue(o);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load receivables");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <PageHeader
        title="Receivables"
        subtitle="Who owes you money, how much, and for how long — so nothing slips through. Record payments as they come in."
      />

      {error && <div className="mb-4 text-sm text-red-700">{error}</div>}

      {/* Headline numbers */}
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Stat label="Total outstanding" value={naira(summary?.total_outstanding)} />
        <Stat label="Overdue" value={naira(summary?.overdue_total)} danger />
        <Stat label="Open invoices" value={summary ? String(summary.open_invoice_count) : "—"} />
      </div>

      {/* Aging */}
      {summary && (
        <Card className="mb-4 p-4">
          <div className="mb-2 text-sm font-medium">Aging</div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            {Object.entries(summary.aging).map(([k, v]) => (
              <div key={k} className="rounded border border-line p-2">
                <div className="text-[11px] text-muted">{AGING_LABEL[k] ?? k}</div>
                <div className="text-sm font-semibold">{naira(v)}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Top debtors */}
        <Card className="p-4">
          <div className="mb-2 text-sm font-medium">Top debtors</div>
          {(summary?.debtors ?? []).length === 0 && !loading && (
            <div className="text-sm text-muted">No one owes you right now.</div>
          )}
          <div className="space-y-1">
            {(summary?.debtors ?? []).slice(0, 12).map((d) => (
              <div
                key={`${d.customer_id}-${d.customer_name}`}
                onClick={() => d.customer_id && router.push(`/customers`)}
                className="flex items-center justify-between rounded px-2 py-1.5 text-sm hover:bg-wash"
              >
                <span className="min-w-0 flex-1 truncate">{d.customer_name}</span>
                <span className="font-medium">{naira(d.outstanding)}</span>
              </div>
            ))}
          </div>
        </Card>

        {/* Overdue invoices to chase */}
        <Card className="p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium">To chase (overdue)</span>
            {overdue && <span className="text-xs text-muted">{overdue.count} · {naira(overdue.total)}</span>}
          </div>
          {(overdue?.invoices ?? []).length === 0 && !loading && (
            <div className="text-sm text-muted">Nothing overdue. 🎉</div>
          )}
          <div className="space-y-1">
            {(overdue?.invoices ?? []).slice(0, 15).map((i) => (
              <div key={i.invoice_id} className="flex items-center gap-2 rounded border border-line px-2 py-1.5">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm">{i.customer_name}</div>
                  <div className="text-[11px] text-muted">
                    {i.invoice_number} · {i.days_overdue}d overdue
                  </div>
                </div>
                <span className="text-sm font-medium">{naira(i.balance)}</span>
                <button
                  onClick={() => setPayFor(i)}
                  className="rounded border border-line px-2 py-1 text-xs hover:bg-wash"
                >
                  Record payment
                </button>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {payFor && (
        <PaymentModal
          invoice={payFor}
          onClose={() => setPayFor(null)}
          onDone={() => {
            setPayFor(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function Stat({ label, value, danger }: { label: string; value: string; danger?: boolean }) {
  return (
    <Card className="p-4">
      <div className="text-[11px] text-muted">{label}</div>
      <div className={`text-lg font-semibold ${danger ? "text-red-600" : ""}`}>{value}</div>
    </Card>
  );
}

const METHODS = ["cash", "transfer", "pos", "opay", "moniepoint", "cheque", "other"];

function PaymentModal({
  invoice,
  onClose,
  onDone,
}: {
  invoice: OverdueInvoice;
  onClose: () => void;
  onDone: () => void;
}) {
  const [amount, setAmount] = useState(String(invoice.balance));
  const [method, setMethod] = useState("transfer");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [idemKey] = useState(() => newIdempotencyKey());

  async function submit() {
    const amt = Number(amount);
    if (!amt || amt <= 0) {
      setErr("Enter a positive amount");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api.recordPayment(invoice.invoice_id, { amount: amt, method, reference }, idemKey);
      onDone();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not record payment");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
      <Card className="p-4">
        <div className="mb-1 text-sm font-medium">Record payment</div>
        <div className="mb-3 text-xs text-muted">
          {invoice.customer_name} · {invoice.invoice_number} · balance {naira(invoice.balance)}
        </div>
        <label className="mb-2 block text-xs">
          Amount (₦)
          <input
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="mt-1 w-full rounded border border-line px-3 py-2 text-sm"
          />
        </label>
        <label className="mb-2 block text-xs">
          Method
          <select
            value={method}
            onChange={(e) => setMethod(e.target.value)}
            className="mt-1 w-full rounded border border-line bg-paper px-3 py-2 text-sm"
          >
            {METHODS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <label className="mb-3 block text-xs">
          Reference (optional)
          <input
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            placeholder="bank/txn reference"
            className="mt-1 w-full rounded border border-line px-3 py-2 text-sm"
          />
        </label>
        {err && <div className="mb-2 text-xs text-red-700">{err}</div>}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash">
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={busy}
            className="rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper disabled:opacity-40"
          >
            {busy ? "Saving…" : "Record"}
          </button>
        </div>
      </Card>
      </div>
    </div>
  );
}
