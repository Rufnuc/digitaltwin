"use client";
import { type ReactNode, useState } from "react";

export interface FormField {
  key: string;
  label: string;
  type?: "text" | "number" | "select" | "textarea" | "date";
  options?: { value: string; label: string }[];
  required?: boolean;
  placeholder?: string;
  step?: string;
  help?: string;
}

// A modal form driven by a field spec. Emits a plain object of values (numbers
// coerced) to onSubmit; the caller does the API call.
export function EntityForm({
  title,
  fields,
  initial = {},
  submitLabel = "Save",
  onSubmit,
  onClose,
  extra,
}: {
  title: string;
  fields: FormField[];
  initial?: Record<string, unknown>;
  submitLabel?: string;
  onSubmit: (values: Record<string, unknown>) => Promise<void>;
  onClose: () => void;
  extra?: ReactNode;
}) {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const v: Record<string, string> = {};
    for (const f of fields) {
      const raw = initial[f.key];
      v[f.key] = raw == null ? "" : String(raw);
    }
    return v;
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set(key: string, val: string) {
    setValues((prev) => ({ ...prev, [key]: val }));
  }

  // Editing an existing record (initial values supplied) vs creating a new one.
  const isEdit = Object.keys(initial).length > 0;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    // Build the payload, coercing numbers. On create we drop empty optionals; on
    // edit we send an explicit null so a cleared field is actually cleared (not left
    // at its old value).
    const payload: Record<string, unknown> = {};
    for (const f of fields) {
      const raw = values[f.key]?.trim() ?? "";
      if (raw === "") {
        if (f.required) {
          setError(`${f.label} is required`);
          return;
        }
        if (isEdit) payload[f.key] = null;
        continue;
      }
      payload[f.key] = f.type === "number" ? Number(raw) : raw;
    }
    setBusy(true);
    try {
      await onSubmit(payload);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:items-center"
      onMouseDown={onClose}
    >
      <div
        className="w-full max-w-lg rounded-lg border border-line bg-paper p-4 shadow-xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="text-muted hover:text-ink">
            ✕
          </button>
        </div>
        <form onSubmit={submit} className="space-y-3">
          {fields.map((f) => (
            <div key={f.key}>
              <label className="mb-1 block text-xs font-medium text-muted">
                {f.label}
                {f.required && <span className="text-red-600"> *</span>}
              </label>
              {f.type === "select" ? (
                <select
                  value={values[f.key] ?? ""}
                  onChange={(e) => set(f.key, e.target.value)}
                  className="w-full rounded border border-line bg-paper px-3 py-1.5 text-sm outline-none focus:border-ink"
                >
                  <option value="">—</option>
                  {f.options?.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              ) : f.type === "textarea" ? (
                <textarea
                  value={values[f.key] ?? ""}
                  onChange={(e) => set(f.key, e.target.value)}
                  placeholder={f.placeholder}
                  rows={2}
                  className="w-full rounded border border-line bg-paper px-3 py-1.5 text-sm outline-none focus:border-ink"
                />
              ) : (
                <input
                  type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"}
                  step={f.step}
                  value={values[f.key] ?? ""}
                  onChange={(e) => set(f.key, e.target.value)}
                  placeholder={f.placeholder}
                  className="w-full rounded border border-line bg-paper px-3 py-1.5 text-sm outline-none focus:border-ink"
                />
              )}
              {f.help && <p className="mt-0.5 text-[11px] text-muted">{f.help}</p>}
            </div>
          ))}
          {extra}
          {error && <div className="text-sm text-red-700">{error}</div>}
          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy}
              className="rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper disabled:opacity-50"
            >
              {busy ? "Saving…" : submitLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
