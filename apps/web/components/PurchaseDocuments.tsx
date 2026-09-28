"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, getRole, type PurchaseDocument } from "@/lib/api";

const SHIPPING_KINDS = [
  { value: "shipping", label: "Shipping / waybill" },
  { value: "packing", label: "Packing list" },
  { value: "bill_of_lading", label: "Bill of lading" },
  { value: "invoice", label: "Supplier invoice" },
  { value: "payment", label: "Proof of payment" },
  { value: "photo", label: "Photo" },
  { value: "other", label: "Other" },
];

// Receipt types used when documents are tied to a specific payment.
export const RECEIPT_KINDS = [
  { value: "payment_receipt", label: "Naira payment receipt" },
  { value: "fx_confirmation", label: "FX conversion confirmation" },
  { value: "other", label: "Other receipt" },
];

const kindLabel = (k: string) =>
  [...SHIPPING_KINDS, ...RECEIPT_KINDS].find((x) => x.value === k)?.label ?? k;
const size = (b: number | null) =>
  b == null ? "" : b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(0)} KB` : `${(b / 1048576).toFixed(1)} MB`;
const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("en-NG", { dateStyle: "medium" }) : "";

/** Upload / list / download documents for a purchase (supply group), or receipts
 * for a specific payment when paymentId is given. */
export function PurchaseDocuments({
  purchaseId,
  paymentId,
  onChanged,
}: {
  purchaseId: number;
  paymentId?: number;
  onChanged?: () => void;
}) {
  const receiptMode = paymentId != null;
  const kindOptions = receiptMode ? RECEIPT_KINDS : SHIPPING_KINDS;
  const [docs, setDocs] = useState<PurchaseDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [kind, setKind] = useState(kindOptions[0].value);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const canDelete = getRole() === "MANAGER" || getRole() === "OWNER";

  const load = useCallback(() => {
    setLoading(true);
    api
      .listPurchaseDocuments(purchaseId, paymentId)
      .then((r) => setDocs(r.items))
      .catch(() => setDocs([]))
      .finally(() => setLoading(false));
  }, [purchaseId, paymentId]);

  useEffect(() => { load(); }, [load]);

  async function upload(files: FileList | null) {
    if (!files || files.length === 0) return;
    setBusy(true); setErr(null);
    try {
      for (const f of Array.from(files)) {
        await api.uploadPurchaseDocument(purchaseId, f, kind, note, paymentId);
      }
      setNote("");
      if (fileRef.current) fileRef.current.value = "";
      load();
      onChanged?.();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove(d: PurchaseDocument) {
    if (!confirm(`Remove "${d.filename}"?`)) return;
    try {
      await api.deletePurchaseDocument(purchaseId, d.id);
      load();
      onChanged?.();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Delete failed");
    }
  }

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-end gap-2">
        <label className="text-xs">
          <span className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Type</span>
          <select value={kind} onChange={(e) => setKind(e.target.value)}
            className="rounded border border-line bg-paper px-2 py-1.5 text-sm">
            {kindOptions.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
          </select>
        </label>
        <label className="flex-1 text-xs">
          <span className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Note (optional)</span>
          <input value={note} onChange={(e) => setNote(e.target.value)}
            placeholder={receiptMode ? "e.g. bank, amount converted" : "e.g. B/L no., carrier"}
            className="w-full rounded border border-line bg-paper px-2 py-1.5 text-sm" />
        </label>
        <button onClick={() => fileRef.current?.click()} disabled={busy}
          className="rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper disabled:opacity-40">
          {busy ? "Uploading…" : receiptMode ? "+ Receipt" : "+ Upload"}
        </button>
        <input ref={fileRef} type="file" multiple hidden
          onChange={(e) => upload(e.target.files)} />
      </div>
      {err && <div className="mb-2 text-xs text-red-700">{err}</div>}

      {loading ? (
        <div className="text-xs text-muted">Loading…</div>
      ) : docs.length === 0 ? (
        <div className="rounded border border-dashed border-line px-3 py-3 text-center text-xs text-muted">
          {receiptMode
            ? "No receipts yet. Attach the naira payment receipt and the FX-conversion confirmation."
            : "No documents yet. Upload waybills, packing lists, invoices or payment proofs for this supply."}
        </div>
      ) : (
        <div className="space-y-1">
          {docs.map((d) => (
            <div key={d.id}
              className="flex items-center gap-2 rounded border border-line px-2 py-1.5 text-xs">
              <span className="min-w-0 flex-1 truncate">
                <button onClick={() => api.downloadPurchaseDocument(purchaseId, d.id, d.filename)}
                  className="font-medium text-blue-700 hover:underline dark:text-blue-300">
                  {d.filename}
                </button>
                <span className="block text-muted">
                  {kindLabel(d.kind)}{d.note ? ` · ${d.note}` : ""}
                  {d.size_bytes ? ` · ${size(d.size_bytes)}` : ""} · {when(d.created_at)}
                </span>
              </span>
              {canDelete && (
                <button onClick={() => remove(d)}
                  className="shrink-0 text-muted hover:text-red-700" title="Delete">✕</button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
