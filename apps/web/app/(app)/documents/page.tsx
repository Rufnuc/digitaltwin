"use client";
import { useEffect, useRef, useState } from "react";
import { api, getRole, type Extraction } from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card } from "@/components/ui";
import { money, pct } from "@/lib/format";

const REVIEW_ROLES = ["ADMIN", "OWNER", "MANAGER"];

const STATUS_STYLE: Record<string, string> = {
  AI_EXTRACTED: "bg-blue-50 text-blue-800 border-blue-200",
  NEEDS_REVIEW: "bg-yellow-50 text-yellow-800 border-yellow-300",
  VERIFIED: "bg-green-50 text-green-800 border-green-200",
  REJECTED: "bg-red-50 text-red-800 border-red-200",
};

export default function DocumentsPage() {
  const [queue, setQueue] = useState<Extraction[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const canReview = REVIEW_ROLES.includes(getRole() ?? "");

  const load = () => api.reviewQueue().then((r) => setQueue(r.items)).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  async function onFile(f: File) {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const res = await api.uploadDocument(f);
      setNote(
        `Extracted "${res.extraction.extracted.invoice_number ?? "invoice"}" → ${res.extraction.status} ` +
          `(confidence ${pct(res.extraction.overall_confidence)})`,
      );
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function approve(id: number) {
    try {
      await api.approveExtraction(id);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Approve failed");
    }
  }
  async function reject(id: number) {
    try {
      await api.rejectExtraction(id, "rejected in review");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reject failed");
    }
  }

  return (
    <div>
      <PageHeader
        title="Documents"
        subtitle="Upload source documents → extract → match → validate → review → approve into the books. Nothing reaches analytics until a manager approves it."
      />

      <Card className="mb-4 p-4">
        <div className="mb-2 text-sm font-medium">Upload a document</div>
        <p className="mb-3 text-[11px] text-muted">
          The OCR/Document-AI provider is pluggable (Google Document AI, AWS Textract, Azure). The
          default offline provider ingests machine-readable invoice JSON, so the full pipeline runs
          without external services. Structure:{" "}
          <code className="font-mono">
            {"{ invoice_number, invoice_date, customer_name, lines: [{ description, quantity, unit_price, line_total }] }"}
          </code>
        </p>
        <input
          ref={fileRef}
          type="file"
          accept=".json,application/json"
          disabled={busy}
          onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
          className="block w-full text-sm file:mr-3 file:rounded file:border file:border-line file:bg-wash file:px-3 file:py-1.5 file:text-sm"
        />
        {note && <div className="mt-2 text-sm text-green-800">{note}</div>}
        {error && <div className="mt-2 text-sm text-red-700">{error}</div>}
        {!canReview && (
          <div className="mt-2 text-[11px] text-muted">
            Your role can upload but not approve into the books (requires Manager or higher).
          </div>
        )}
      </Card>

      <div className="mb-2 text-sm font-medium">Review queue ({queue.length})</div>
      {queue.length === 0 ? (
        <div className="text-sm text-muted">Nothing awaiting review.</div>
      ) : (
        <div className="space-y-3">
          {queue.map((e) => (
            <ExtractionCard
              key={e.id}
              e={e}
              canReview={canReview}
              onApprove={() => approve(e.id)}
              onReject={() => reject(e.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ExtractionCard({
  e,
  canReview,
  onApprove,
  onReject,
}: {
  e: Extraction;
  canReview: boolean;
  onApprove: () => void;
  onReject: () => void;
}) {
  const ex = e.extracted;
  const cust = e.matched.customer;
  const lines = ex.lines ?? [];
  const lineMatches = e.matched.lines ?? [];
  return (
    <Card className="p-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-sm font-medium">
          {ex.invoice_number ?? "—"} · {ex.invoice_date ?? "—"}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-muted">conf {pct(e.overall_confidence)}</span>
          <span
            className={`rounded border px-1.5 py-0.5 text-[10px] font-mono ${
              STATUS_STYLE[e.status] ?? "border-line text-muted"
            }`}
          >
            {e.status}
          </span>
        </div>
      </div>

      <div className="mb-2 text-xs">
        Customer:{" "}
        <span className="font-medium">{ex.customer_name ?? "—"}</span>{" "}
        {cust?.id != null ? (
          <span className="text-green-700">→ matched #{cust.id} ({pct(cust.confidence)})</span>
        ) : (
          <span className="text-yellow-700">→ no confident match</span>
        )}
      </div>

      <div className="overflow-x-auto rounded border border-line">
        <table className="min-w-full text-xs">
          <thead className="bg-wash text-left uppercase tracking-wide text-muted">
            <tr>
              {["Description", "Qty", "Unit", "Total", "Product match"].map((h) => (
                <th key={h} className="px-2 py-1.5 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {lines.map((ln, i) => (
              <tr key={i} className="border-t border-line tabular-nums">
                <td className="px-2 py-1.5">{ln.description}</td>
                <td className="px-2 py-1.5">{ln.quantity}</td>
                <td className="px-2 py-1.5">{money(ln.unit_price)}</td>
                <td className="px-2 py-1.5">{money(ln.line_total)}</td>
                <td className="px-2 py-1.5">
                  {lineMatches[i]?.product_id != null ? (
                    <span className="text-green-700">
                      #{lineMatches[i].product_id} ({pct(lineMatches[i].confidence)})
                    </span>
                  ) : (
                    <span className="text-yellow-700">unmatched</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!e.validation.arithmetic_ok && (
        <div className="mt-2 rounded border border-yellow-400 bg-yellow-50 p-2 text-xs">
          {e.validation.issues.map((iss, i) => (
            <div key={i}>⚠ {iss}</div>
          ))}
        </div>
      )}

      {canReview && (
        <div className="mt-3 flex gap-2">
          <button
            onClick={onApprove}
            className="rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper"
          >
            Approve into books
          </button>
          <button
            onClick={onReject}
            className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash"
          >
            Reject
          </button>
        </div>
      )}
    </Card>
  );
}
