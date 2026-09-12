"use client";
import { useEffect, useRef, useState } from "react";
import {
  api,
  type ImportBatch,
  type ImportField,
  type ImportPreview,
  type ImportResult,
} from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card } from "@/components/ui";

export default function ImportsPage() {
  const [entities, setEntities] = useState<Record<string, ImportField[]>>({});
  const [entity, setEntity] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ImportResult | null>(null);
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadBatches = () => api.listImports().then((r) => setBatches(r.items)).catch(() => {});

  useEffect(() => {
    api.importEntities().then((r) => {
      setEntities(r.entities);
      setEntity(Object.keys(r.entities)[0] ?? "");
    });
    loadBatches();
  }, []);

  async function onFile(f: File) {
    setFile(f);
    setResult(null);
    setError(null);
    try {
      const p = await api.previewImport(f);
      setPreview(p);
      // Auto-map target fields to same-named (case-insensitive) source columns.
      const fields = entities[entity] ?? [];
      const auto: Record<string, string> = {};
      for (const col of p.columns) {
        const match = fields.find((fld) => fld.name.toLowerCase() === col.toLowerCase());
        if (match) auto[col] = match.name;
      }
      setMapping(auto);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Preview failed");
    }
  }

  async function commit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.commitImport(entity, mapping, file);
      setResult(res);
      loadBatches();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  const fields = entities[entity] ?? [];
  const mappedTargets = new Set(Object.values(mapping));
  const requiredUnmapped = fields.filter((f) => f.required && !mappedTargets.has(f.name));

  return (
    <div>
      <PageHeader
        title="Imports"
        subtitle="Upload a CSV → preview → map columns → import. Every batch is recorded with provenance (spec §15, §42)."
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="p-4">
          <div className="mb-3 text-sm font-medium">1 · Choose & upload</div>
          <label className="mb-1 block text-xs text-muted">Entity type</label>
          <select
            value={entity}
            onChange={(e) => {
              setEntity(e.target.value);
              setPreview(null);
              setMapping({});
              setResult(null);
            }}
            className="mb-3 w-full rounded border border-line px-2 py-1.5 text-sm"
          >
            {Object.keys(entities).map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
            className="block w-full text-sm file:mr-3 file:rounded file:border file:border-line file:bg-wash file:px-3 file:py-1.5 file:text-sm"
          />
          {fields.length > 0 && (
            <p className="mt-3 text-[11px] text-muted">
              Target fields:{" "}
              {fields.map((f) => (
                <span key={f.name} className="font-mono">
                  {f.name}
                  {f.required ? "*" : ""}{" "}
                </span>
              ))}
            </p>
          )}
          {error && <div className="mt-2 text-sm text-red-700">{error}</div>}
        </Card>

        <Card className="p-4 lg:col-span-2">
          <div className="mb-3 text-sm font-medium">2 · Map columns → fields</div>
          {!preview ? (
            <div className="text-sm text-muted">Upload a CSV to see its columns.</div>
          ) : (
            <div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {preview.columns.map((col) => (
                  <div key={col} className="flex items-center gap-2">
                    <span className="w-32 truncate font-mono text-xs text-muted" title={col}>
                      {col}
                    </span>
                    <span className="text-muted">→</span>
                    <select
                      value={mapping[col] ?? ""}
                      onChange={(e) =>
                        setMapping((m) => {
                          const next = { ...m };
                          if (e.target.value) next[col] = e.target.value;
                          else delete next[col];
                          return next;
                        })
                      }
                      className="flex-1 rounded border border-line px-2 py-1 text-sm"
                    >
                      <option value="">(ignore)</option>
                      {fields.map((f) => (
                        <option key={f.name} value={f.name}>
                          {f.name}
                          {f.required ? " *" : ""}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>

              {requiredUnmapped.length > 0 && (
                <div className="mt-3 rounded border border-yellow-500/50 bg-yellow-500/15 p-2 text-xs">
                  Required fields not yet mapped:{" "}
                  {requiredUnmapped.map((f) => f.name).join(", ")}
                </div>
              )}

              <button
                onClick={commit}
                disabled={busy || requiredUnmapped.length > 0}
                className="mt-4 rounded bg-ink px-3 py-2 text-sm font-medium text-paper disabled:opacity-40"
              >
                {busy ? "Importing…" : "Import"}
              </button>

              {result && (
                <div className="mt-4 rounded border border-line p-3 text-sm">
                  <div className="font-medium">
                    Imported {result.rows_imported}/{result.rows_total} rows
                    {result.rows_failed > 0 && ` · ${result.rows_failed} failed`}
                  </div>
                  {result.errors.length > 0 && (
                    <ul className="mt-2 max-h-40 overflow-y-auto text-xs text-muted">
                      {result.errors.map((e, i) => (
                        <li key={i}>
                          row {e.row}: {e.error}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          )}
        </Card>
      </div>

      <Card className="mt-4 p-4">
        <div className="mb-2 text-sm font-medium">Import history</div>
        {batches.length === 0 ? (
          <div className="text-sm text-muted">No imports yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-muted">
                <tr>
                  {["#", "File", "Status", "Imported", "Failed", "When"].map((h) => (
                    <th key={h} className="px-2 py-1.5 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {batches.map((b) => (
                  <tr key={b.id} className="border-t border-line">
                    <td className="px-2 py-1.5">{b.id}</td>
                    <td className="px-2 py-1.5">{b.filename ?? "—"}</td>
                    <td className="px-2 py-1.5 font-mono text-xs">{b.status}</td>
                    <td className="px-2 py-1.5">{b.rows_imported ?? "—"}</td>
                    <td className="px-2 py-1.5">{b.rows_failed ?? "—"}</td>
                    <td className="px-2 py-1.5 text-xs text-muted">
                      {new Date(b.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
