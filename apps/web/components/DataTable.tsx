"use client";
import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ProvenanceBadge } from "./ui";

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => React.ReactNode;
  className?: string;
  sortable?: boolean; // clickable header → server-side sort by `key`
}

export interface FilterSpec {
  key: string;
  label: string;
  options: { value: string; label: string }[];
}

// Generic paginated resource table with search, sortable headers and filters.
export function ResourceTable<T extends Record<string, unknown>>({
  resource,
  columns,
  searchable = true,
  showProvenance = true,
  filters = [],
}: {
  resource: string;
  columns: Column<T>[];
  searchable?: boolean;
  showProvenance?: boolean;
  filters?: FilterSpec[];
}) {
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [filterValues, setFilterValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const limit = 25;

  useEffect(() => {
    let active = true;
    setLoading(true);
    const parts = [`limit=${limit}`, `offset=${offset}`];
    if (q) parts.push(`q=${encodeURIComponent(q)}`);
    if (sort) parts.push(`sort=${sort}`, `sort_dir=${sortDir}`);
    for (const [k, v] of Object.entries(filterValues)) if (v) parts.push(`${k}=${encodeURIComponent(v)}`);
    api
      .list<T>(resource, `?${parts.join("&")}`)
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
  }, [resource, offset, q, sort, sortDir, filterValues]);

  function toggleSort(key: string) {
    setOffset(0);
    if (sort === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSort(key);
      setSortDir("asc");
    }
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {searchable && (
          <input
            value={q}
            onChange={(e) => {
              setOffset(0);
              setQ(e.target.value);
            }}
            placeholder="Search…"
            className="w-56 rounded border border-line bg-paper px-3 py-1.5 text-sm outline-none focus:border-ink"
          />
        )}
        {filters.map((f) => (
          <select
            key={f.key}
            value={filterValues[f.key] ?? ""}
            onChange={(e) => {
              setOffset(0);
              setFilterValues((prev) => ({ ...prev, [f.key]: e.target.value }));
            }}
            className="rounded border border-line bg-paper px-2 py-1.5 text-sm"
          >
            <option value="">{f.label}: all</option>
            {f.options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        ))}
        {(sort || Object.values(filterValues).some(Boolean) || q) && (
          <button
            onClick={() => {
              setSort(null);
              setFilterValues({});
              setQ("");
              setOffset(0);
            }}
            className="text-xs text-muted underline decoration-dotted"
          >
            Clear
          </button>
        )}
      </div>

      {error && <div className="mb-2 text-sm text-red-700">Error: {error}</div>}

      {/* Mobile: each record as a stacked card so no field is hidden off-screen. */}
      <div className="space-y-2 sm:hidden">
        {loading ? (
          <div className="rounded-lg border border-line px-3 py-6 text-sm text-muted">Loading…</div>
        ) : items.length === 0 ? (
          <div className="rounded-lg border border-line px-3 py-6 text-sm text-muted">
            No records.
          </div>
        ) : (
          items.map((row, i) => (
            <div key={i} className="rounded-lg border border-line bg-paper p-3">
              {columns.map((c) => (
                <div key={c.key} className="flex items-start justify-between gap-3 py-0.5 text-sm">
                  <span className="shrink-0 text-xs uppercase tracking-wide text-muted">
                    {c.header}
                  </span>
                  <span className="min-w-0 break-words text-right tabular-nums">
                    {c.render ? c.render(row) : String(row[c.key] ?? "—")}
                  </span>
                </div>
              ))}
              {showProvenance && (
                <div className="mt-1 flex justify-end border-t border-line pt-1.5">
                  <ProvenanceBadge origin={String(row["data_origin"] ?? "REAL")} />
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Tablet and up: the full table (scrolls horizontally only if truly wide). */}
      <div className="hidden overflow-x-auto rounded-lg border border-line sm:block">
        <table className="min-w-full text-sm">
          <thead className="bg-wash text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={`px-3 py-2 font-medium ${c.className ?? ""}`}>
                  {c.sortable ? (
                    <button
                      onClick={() => toggleSort(c.key)}
                      className="inline-flex items-center gap-1 hover:text-ink"
                    >
                      {c.header}
                      <span className="text-[9px]">
                        {sort === c.key ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
                      </span>
                    </button>
                  ) : (
                    c.header
                  )}
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
