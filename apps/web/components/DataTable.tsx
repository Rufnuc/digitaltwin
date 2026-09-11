"use client";
import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ProvenanceBadge } from "./ui";

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => React.ReactNode;
  className?: string;
}

// Generic paginated resource table. Fetches `/resource?limit&offset&q`.
export function ResourceTable<T extends Record<string, unknown>>({
  resource,
  columns,
  searchable = true,
  showProvenance = true,
}: {
  resource: string;
  columns: Column<T>[];
  searchable?: boolean;
  showProvenance?: boolean;
}) {
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const limit = 25;

  useEffect(() => {
    let active = true;
    setLoading(true);
    const params = `?limit=${limit}&offset=${offset}${q ? `&q=${encodeURIComponent(q)}` : ""}`;
    api
      .list<T>(resource, params)
      .then((res) => {
        if (!active) return;
        setItems(res.items);
        setTotal(res.total);
        setError(null);
      })
      .catch((e) => active && setError(e.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [resource, offset, q]);

  return (
    <div>
      {searchable && (
        <input
          value={q}
          onChange={(e) => {
            setOffset(0);
            setQ(e.target.value);
          }}
          placeholder="Search…"
          className="mb-3 w-64 rounded border border-line px-3 py-1.5 text-sm outline-none focus:border-ink"
        />
      )}
      {error && <div className="mb-2 text-sm text-red-700">Error: {error}</div>}
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="min-w-full text-sm">
          <thead className="bg-wash text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={`px-3 py-2 font-medium ${c.className ?? ""}`}>
                  {c.header}
                </th>
              ))}
              {showProvenance && <th className="px-3 py-2 font-medium">Origin</th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td className="px-3 py-6 text-muted" colSpan={columns.length + 1}>
                  Loading…
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td className="px-3 py-6 text-muted" colSpan={columns.length + 1}>
                  No records.
                </td>
              </tr>
            ) : (
              items.map((row, i) => (
                <tr key={i} className="border-t border-line hover:bg-wash">
                  {columns.map((c) => (
                    <td key={c.key} className={`px-3 py-2 tabular-nums ${c.className ?? ""}`}>
                      {c.render ? c.render(row) : String(row[c.key] ?? "—")}
                    </td>
                  ))}
                  {showProvenance && (
                    <td className="px-3 py-2">
                      <ProvenanceBadge origin={String(row["data_origin"] ?? "REAL")} />
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex items-center justify-between text-xs text-muted">
        <span>
          {total} record{total === 1 ? "" : "s"}
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
    </div>
  );
}
