"use client";
import { useCallback, useEffect, useState } from "react";
import { api, type AuditEvent } from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card } from "@/components/ui";

// The activity log: a complete, automatic record of every change in the app —
// who did what, when, and the before→after. Read straight from the audit trail.

const ACTION_STYLE: Record<string, string> = {
  CREATE: "text-green-700 dark:text-green-300",
  UPDATE: "text-blue-700 dark:text-blue-300",
  DELETE: "text-red-700 dark:text-red-300",
};

const ENTITY_TYPES = [
  "", "customers", "products", "suppliers", "invoices", "invoice_lines",
  "expenses", "stock_lots", "stock_movements", "warehouses", "product_substitutes",
  "users", "simulation_runs",
];

function when(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("en-NG", { dateStyle: "medium", timeStyle: "short" });
}

export default function ActivityPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [entityType, setEntityType] = useState("");
  const [action, setAction] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const q = new URLSearchParams();
      if (entityType) q.set("entity_type", entityType);
      if (action) q.set("action", action);
      q.set("limit", "100");
      const r = await api.activityLog(`?${q.toString()}`);
      setEvents(r.items);
      setTotal(r.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the activity log");
    } finally {
      setLoading(false);
    }
  }, [entityType, action]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <PageHeader
        title="Activity Log"
        subtitle="A complete, automatic record of everything that changes in the app — who did what, when, and the before → after. Nothing is recorded by hand; it's captured for you."
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select
          value={entityType}
          onChange={(e) => setEntityType(e.target.value)}
          className="rounded border border-line bg-paper px-3 py-2 text-sm"
        >
          {ENTITY_TYPES.map((t) => (
            <option key={t} value={t}>
              {t === "" ? "All records" : t.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <select
          value={action}
          onChange={(e) => setAction(e.target.value)}
          className="rounded border border-line bg-paper px-3 py-2 text-sm"
        >
          <option value="">All actions</option>
          <option value="CREATE">Created</option>
          <option value="UPDATE">Updated</option>
          <option value="DELETE">Deleted</option>
        </select>
        <button
          onClick={load}
          disabled={loading}
          className="rounded bg-ink px-4 py-2 text-sm font-medium text-paper disabled:opacity-40"
        >
          {loading ? "Loading…" : "Refresh"}
        </button>
        <span className="ml-auto text-sm text-muted">{total.toLocaleString()} events</span>
      </div>

      {error && <div className="mb-4 text-sm text-red-700">{error}</div>}
      {!loading && events.length === 0 && !error && (
        <Card className="p-6 text-center text-sm text-muted">No activity recorded yet.</Card>
      )}

      <div className="space-y-1.5">
        {events.map((e) => {
          const open = openId === e.id;
          const hasDetail = e.old_value || e.new_value;
          return (
            <Card key={e.id} className="p-3">
              <div
                onClick={() => hasDetail && setOpenId(open ? null : e.id)}
                className={`flex items-start gap-3 ${hasDetail ? "cursor-pointer" : ""}`}
              >
                <span className={`mt-0.5 w-16 shrink-0 text-xs font-semibold ${ACTION_STYLE[e.action] ?? "text-muted"}`}>
                  {e.action}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm">
                    <span className="font-medium">{(e.entity_type ?? "").replace(/_/g, " ")}</span>
                    {e.entity_id != null && <span className="text-muted"> #{e.entity_id}</span>}
                  </div>
                  <div className="text-xs text-muted">
                    {e.user_name ?? "system"}
                    {e.source && e.source !== "api" ? ` · via ${e.source}` : ""} · {when(e.at)}
                  </div>
                </div>
                {hasDetail && (
                  <span className="shrink-0 text-xs text-muted">{open ? "Hide" : "Details"}</span>
                )}
              </div>
              {open && hasDetail && <ChangeDetail event={e} />}
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function ChangeDetail({ event }: { event: AuditEvent }) {
  const keys = Array.from(
    new Set([...Object.keys(event.old_value ?? {}), ...Object.keys(event.new_value ?? {})]),
  );
  const fmt = (v: unknown) => (v == null ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v));
  return (
    <div className="mt-2 border-t border-line pt-2">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-muted">
            <th className="py-1 pr-3 font-medium">Field</th>
            <th className="py-1 pr-3 font-medium">Before</th>
            <th className="py-1 font-medium">After</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => (
            <tr key={k} className="border-t border-line/50">
              <td className="py-1 pr-3 font-mono">{k}</td>
              <td className="py-1 pr-3 text-muted">{fmt((event.old_value ?? {})[k])}</td>
              <td className="py-1">{fmt((event.new_value ?? {})[k])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
