"use client";
import React, { useEffect, useState } from "react";
import { api, getRole } from "@/lib/api";
import { type Role, roleAtLeast } from "@/lib/roles";
import { EntityForm, type FormField } from "./EntityForm";
import { ProvenanceBadge } from "./ui";

export type { FormField };

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

// Generic paginated resource table with search, sortable headers, filters and —
// when `formFields` is supplied — role-gated Add / Edit / Delete.
export function ResourceTable<T extends Record<string, unknown>>({
  resource,
  columns,
  searchable = true,
  showProvenance = true,
  filters = [],
  formFields,
  entityLabel = "record",
  writeRole = "STAFF",
  deleteRole = "MANAGER",
  writeAllow = [],
  requireSearch = false,
  idKey = "id",
  viewable = false,
  renderExtra,
}: {
  resource: string;
  columns: Column<T>[];
  searchable?: boolean;
  showProvenance?: boolean;
  filters?: FilterSpec[];
  formFields?: FormField[];
  entityLabel?: string;
  writeRole?: Role;
  deleteRole?: Role;
  // Roles allowed to create/edit beyond the hierarchy (e.g. SALESGIRL on customers).
  writeAllow?: string[];
  // When true, the list stays hidden until the user searches (front-desk lookup).
  requireSearch?: boolean;
  idKey?: string;
  viewable?: boolean;
  // Extra content rendered inside the view modal (e.g. a customer's receivables).
  renderExtra?: (row: T) => React.ReactNode;
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
  const [refreshKey, setRefreshKey] = useState(0);
  const [editing, setEditing] = useState<T | null>(null);
  const [creating, setCreating] = useState(false);
  const [viewing, setViewing] = useState<T | null>(null);
  const limit = 25;

  const role = getRole();
  const canWrite = !!formFields && (roleAtLeast(role, writeRole) || (!!role && writeAllow.includes(role)));
  const canDelete = !!formFields && roleAtLeast(role, deleteRole);
  // Front-desk lookup mode: nothing is listed until a search is typed.
  const gateList = requireSearch && q.trim() === "";
  const cols = columns.length + (showProvenance ? 1 : 0) + (canWrite ? 1 : 0);

  useEffect(() => {
    let active = true;
    // In front-desk lookup mode, don't load anything until the user searches.
    if (requireSearch && q.trim() === "") {
      setItems([]);
      setTotal(0);
      setLoading(false);
      return;
    }
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
  }, [resource, offset, q, sort, sortDir, filterValues, refreshKey]);

  async function remove(row: T) {
    const label = String(row["name"] ?? row["code"] ?? row[idKey]);
    if (!window.confirm(`Delete ${entityLabel} "${label}"? This cannot be undone.`)) return;
    try {
      await api.deleteResource(resource, row[idKey] as number);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

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
        {canWrite && (
          <button
            onClick={() => setCreating(true)}
            className="ml-auto rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper"
          >
            + Add {entityLabel}
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
            {gateList ? `Search by name above to look up a ${entityLabel}.` : "No records."}
          </div>
        ) : (
          items.map((row, i) => (
            <div
              key={i}
              onClick={viewable ? () => setViewing(row) : undefined}
              className={`rounded-lg border border-line bg-paper p-3 ${viewable ? "cursor-pointer" : ""}`}
            >
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
              {(showProvenance || canWrite) && (
                <div className="mt-1 flex items-center justify-between border-t border-line pt-1.5">
                  {showProvenance ? (
                    <ProvenanceBadge origin={String(row["data_origin"] ?? "REAL")} />
                  ) : (
                    <span />
                  )}
                  {canWrite && (
                    <span className="flex gap-3 text-xs">
                      <button onClick={(e) => { e.stopPropagation(); setEditing(row); }} className="text-muted underline">
                        Edit
                      </button>
                      {canDelete && (
                        <button onClick={(e) => { e.stopPropagation(); remove(row); }} className="text-red-700 underline">
                          Delete
                        </button>
                      )}
                    </span>
                  )}
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
              {canWrite && <th className="px-3 py-2 text-right font-medium">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td className="px-3 py-6 text-muted" colSpan={cols}>
                  Loading…
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td className="px-3 py-6 text-muted" colSpan={cols}>
                  {gateList ? `Search by name above to look up a ${entityLabel}.` : "No records."}
                </td>
              </tr>
            ) : (
              items.map((row, i) => (
                <tr
                  key={i}
                  onClick={viewable ? () => setViewing(row) : undefined}
                  className={`border-t border-line hover:bg-wash ${viewable ? "cursor-pointer" : ""}`}
                >
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
                  {canWrite && (
                    <td className="whitespace-nowrap px-3 py-2 text-right">
                      <button
                        onClick={(e) => { e.stopPropagation(); setEditing(row); }}
                        className="text-xs text-muted underline hover:text-ink"
                      >
                        Edit
                      </button>
                      {canDelete && (
                        <button
                          onClick={(e) => { e.stopPropagation(); remove(row); }}
                          className="ml-3 text-xs text-red-700 underline"
                        >
                          Delete
                        </button>
                      )}
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

      {formFields && creating && (
        <EntityForm
          title={`Add ${entityLabel}`}
          fields={formFields}
          onClose={() => setCreating(false)}
          onSubmit={async (values) => {
            await api.createResource(resource, values);
            setRefreshKey((k) => k + 1);
          }}
        />
      )}
      {formFields && editing && (
        <EntityForm
          title={`Edit ${entityLabel}`}
          fields={formFields}
          initial={editing}
          onClose={() => setEditing(null)}
          onSubmit={async (values) => {
            await api.updateResource(resource, editing[idKey] as number, values);
            setRefreshKey((k) => k + 1);
          }}
        />
      )}
      {viewable && viewing && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:items-center"
          onMouseDown={() => setViewing(null)}
        >
          <div
            className={`w-full ${renderExtra ? "max-w-lg" : "max-w-md"} rounded-lg border border-line bg-paper p-4 shadow-xl`}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-semibold">
                {String(viewing["name"] ?? viewing["code"] ?? entityLabel)}
              </h2>
              <button onClick={() => setViewing(null)} className="text-muted hover:text-ink">
                ✕
              </button>
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              {columns.map((c) => (
                <div key={c.key}>
                  <div className="text-[10px] uppercase tracking-wide text-muted">{c.header}</div>
                  <div>{c.render ? c.render(viewing) : String(viewing[c.key] ?? "—")}</div>
                </div>
              ))}
            </div>
            {renderExtra && <div className="mt-3">{renderExtra(viewing)}</div>}
            {canWrite && (
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  onClick={() => {
                    setEditing(viewing);
                    setViewing(null);
                  }}
                  className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash"
                >
                  Edit
                </button>
                {canDelete && (
                  <button
                    onClick={() => {
                      const row = viewing;
                      setViewing(null);
                      remove(row);
                    }}
                    className="rounded border border-red-500/40 px-3 py-1.5 text-sm text-red-700 hover:bg-red-500/10"
                  >
                    Delete
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
