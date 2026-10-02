"use client";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/Shell";
import { Card } from "@/components/ui";
import { api, type PosUnmatched } from "@/lib/api";
import { money2 } from "@/lib/format";

export default function PosPage() {
  const [items, setItems] = useState<PosUnmatched[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [manual, setManual] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    try {
      const r = await api.posUnmatched();
      setItems(r.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function assign(txnId: number, invoiceId: number) {
    setBusyId(txnId);
    setError(null);
    try {
      await api.posAssign(txnId, invoiceId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not assign");
    } finally {
      setBusyId(null);
    }
  }

  async function ignore(txnId: number) {
    if (!confirm("Mark this POS transaction as not a sale (ignore it)?")) return;
    setBusyId(txnId);
    try {
      await api.posIgnore(txnId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not ignore");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="POS Payments"
        subtitle="Card payments received from the terminal that still need to be linked to an invoice. Most link automatically; these need a quick confirm."
      />

      {error && <div className="mb-3 text-sm text-red-700">{error}</div>}

      {items.length === 0 ? (
        <Card className="p-6 text-sm text-muted">
          Nothing to reconcile — every POS payment is linked. 🎉
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((t) => (
            <Card key={t.id} className="p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="text-lg font-semibold tabular-nums">{money2(t.amount)}</div>
                <div className="text-[11px] text-muted">
                  {t.provider}
                  {t.terminal_id ? ` · terminal ${t.terminal_id}` : ""}
                  {t.reference ? ` · ref ${t.reference}` : ""}
                  {t.occurred_at ? ` · ${new Date(t.occurred_at).toLocaleString("en-NG", { dateStyle: "medium", timeStyle: "short" })}` : ""}
                </div>
              </div>

              {t.suggestions.length > 0 ? (
                <div className="mt-3">
                  <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">
                    Likely invoice
                  </div>
                  <div className="space-y-1">
                    {t.suggestions.map((s) => (
                      <button
                        key={s.invoice_id}
                        disabled={busyId === t.id}
                        onClick={() => assign(t.id, s.invoice_id)}
                        className="flex w-full items-center justify-between gap-3 rounded border border-line px-3 py-2 text-left text-sm hover:bg-wash disabled:opacity-40"
                      >
                        <span>
                          <span className="font-medium">{s.invoice_number}</span>{" "}
                          <span className="text-muted">· {s.customer_name} · bal {money2(s.balance)}</span>
                        </span>
                        <span className="whitespace-nowrap text-[11px] text-muted">
                          {Math.round(s.score * 100)}% match → assign
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="mt-3 text-xs text-muted">No close match found — assign by invoice ID.</div>
              )}

              <div className="mt-3 flex flex-wrap items-center gap-2">
                <input
                  value={manual[t.id] ?? ""}
                  onChange={(e) => setManual((m) => ({ ...m, [t.id]: e.target.value }))}
                  placeholder="Invoice ID"
                  className="w-28 rounded border border-line px-2 py-1 text-sm"
                />
                <button
                  disabled={busyId === t.id || !manual[t.id]}
                  onClick={() => assign(t.id, Number(manual[t.id]))}
                  className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash disabled:opacity-40"
                >
                  Assign to this invoice
                </button>
                <button
                  disabled={busyId === t.id}
                  onClick={() => ignore(t.id)}
                  className="ml-auto rounded border border-line px-3 py-1.5 text-sm text-muted hover:bg-wash disabled:opacity-40"
                >
                  Ignore
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
