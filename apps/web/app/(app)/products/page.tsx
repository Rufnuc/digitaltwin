"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { PageHeader } from "@/components/Shell";
import { Card } from "@/components/ui";
import { EntityForm, type FormField } from "@/components/EntityForm";
import {
  api,
  getRole,
  imageSrc,
  type ProductImage as PImage,
  type ProductAnalytics,
  type ProductHistory as ProductHistoryType,
} from "@/lib/api";
import { money2, num } from "@/lib/format";
import { roleAtLeast } from "@/lib/roles";
import { Modal } from "@/components/Modal";
import { MiniLineChart } from "@/components/MiniLineChart";

interface Product {
  id: number;
  code: string;
  name: string;
  part_number: string | null;
  category: string | null;
  manufacturer: string | null;
  description: string | null;
  purchase_cost: number | null;
  selling_price: number | null;
  reorder_level: number | null;
  lead_time_days: number | null;
  image_url: string | null;
  data_origin?: string;
}

const CATEGORIES = ["Engine", "Brakes", "Electrical", "Suspension", "Filters", "Body"];

const formFields: FormField[] = [
  { key: "name", label: "Name", required: true },
  { key: "part_number", label: "Part number" },
  { key: "category", label: "Category" },
  { key: "manufacturer", label: "Manufacturer" },
  { key: "purchase_cost", label: "Purchase cost (₦)", type: "number", step: "0.01" },
  { key: "selling_price", label: "Selling price (₦)", type: "number", step: "0.01" },
  { key: "reorder_level", label: "Reorder level", type: "number" },
  { key: "lead_time_days", label: "Lead time (days)", type: "number" },
];

export default function ProductsPage() {
  const [rows, setRows] = useState<Product[]>([]);
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canWrite = roleAtLeast(getRole(), "STAFF");

  const load = useCallback(async () => {
    try {
      const parts = ["limit=200"];
      if (q) parts.push(`q=${encodeURIComponent(q)}`);
      if (category) parts.push(`category=${encodeURIComponent(category)}`);
      const r = await api.list<Product>("products", `?${parts.join("&")}`);
      setRows(r.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }, [q, category]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <PageHeader title="Products" subtitle="Product catalogue. Click a product for its image, details and actions." />
        {canWrite && (
          <button onClick={() => setCreating(true)} className="shrink-0 rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper">
            + Add product
          </button>
        )}
      </div>

      {error && <div className="mb-3 text-sm text-red-700">Error: {error}</div>}

      <div className="mb-3 flex flex-wrap gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search…"
          className="w-56 rounded border border-line bg-paper px-3 py-1.5 text-sm outline-none focus:border-ink"
        />
        <select value={category} onChange={(e) => setCategory(e.target.value)} className="rounded border border-line bg-paper px-2 py-1.5 text-sm">
          <option value="">Category: all</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {rows.map((p) => (
          <button
            key={p.id}
            onClick={() => setSelected(p.id)}
            className="overflow-hidden rounded-lg border border-line bg-paper text-left hover:border-ink"
          >
            <div className="flex h-28 items-center justify-center bg-wash">
              {imageSrc(p.image_url) ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={imageSrc(p.image_url)!} alt={p.name} className="h-full w-full object-contain" />
              ) : (
                <span className="text-3xl text-line">🧩</span>
              )}
            </div>
            <div className="p-2">
              <div className="truncate text-sm font-medium">{p.name}</div>
              <div className="text-[11px] text-muted">{p.code}{p.category ? ` · ${p.category}` : ""}</div>
              <div className="mt-0.5 text-xs tabular-nums">{p.selling_price != null ? money2(p.selling_price) : "—"}</div>
            </div>
          </button>
        ))}
        {rows.length === 0 && <div className="text-sm text-muted">No products.</div>}
      </div>

      {creating && (
        <EntityForm
          title="Add product"
          fields={formFields}
          onClose={() => setCreating(false)}
          onSubmit={async (v) => {
            await api.createResource("products", v);
            load();
          }}
        />
      )}
      {selected != null && (
        <ProductModal id={selected} onClose={() => setSelected(null)} onChanged={load} canWrite={canWrite} />
      )}
    </div>
  );
}

function ProductModal({
  id,
  onClose,
  onChanged,
  canWrite,
}: {
  id: number;
  onClose: () => void;
  onChanged: () => void;
  canWrite: boolean;
}) {
  const [p, setP] = useState<Product | null>(null);
  const [images, setImages] = useState<PImage[]>([]);
  const [sel, setSel] = useState(0);
  const [editing, setEditing] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const canDelete = roleAtLeast(getRole(), "MANAGER");

  const reload = useCallback(async () => {
    const [r, imgs] = await Promise.all([
      api.list<Product>("products", `?limit=1&id=${id}`),
      api.productImages(id).catch(() => ({ items: [] as PImage[] })),
    ]);
    setP(r.items.find((x) => x.id === id) ?? null);
    setImages(imgs.items);
    setSel((s) => Math.min(s, Math.max(0, imgs.items.length - 1)));
  }, [id]);

  useEffect(() => {
    reload();
  }, [reload]);

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      await api.uploadProductImage(id, file);
      await reload();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function addUrl() {
    const u = urlInput.trim();
    if (!u) return;
    setBusy(true);
    setError(null);
    try {
      await api.addProductImageUrl(id, u);
      setUrlInput("");
      await reload();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Add image failed");
    } finally {
      setBusy(false);
    }
  }

  async function makePrimary(imageId: number) {
    await api.setPrimaryImage(id, imageId);
    await reload();
    onChanged();
  }

  async function removeImage(imageId: number) {
    await api.deleteProductImage(id, imageId);
    await reload();
    onChanged();
  }

  async function remove() {
    if (!p || !window.confirm(`Delete product "${p.name}"? This cannot be undone.`)) return;
    try {
      await api.deleteResource("products", id);
      onChanged();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  const current = images[sel];
  const src = imageSrc(current?.url ?? p?.image_url);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 sm:items-center" onMouseDown={onClose}>
      <div className="w-full max-w-lg rounded-lg border border-line bg-paper p-4 shadow-xl" onMouseDown={(e) => e.stopPropagation()}>
        {!p ? (
          <div className="text-sm text-muted">Loading…</div>
        ) : (
          <>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-semibold">{p.name}</h2>
              <button onClick={onClose} className="text-muted hover:text-ink">✕</button>
            </div>

            <div className="mb-2 flex h-48 items-center justify-center rounded-lg border border-line bg-wash">
              {src ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={src} alt={p.name} className="h-full w-full cursor-zoom-in object-contain" onClick={() => setFullscreen(true)} />
              ) : (
                <span className="text-sm text-muted">No images yet</span>
              )}
            </div>

            {/* Thumbnail strip */}
            {images.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-2">
                {images.map((img, i) => (
                  <div key={img.id} className="relative">
                    <button
                      onClick={() => setSel(i)}
                      className={`h-12 w-12 overflow-hidden rounded border ${i === sel ? "border-ink" : "border-line"}`}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={imageSrc(img.url)!} alt="" className="h-full w-full object-cover" />
                    </button>
                    {img.is_primary && (
                      <span className="absolute -left-1 -top-1 rounded-full bg-ink px-1 text-[8px] text-paper">★</span>
                    )}
                    {canWrite && (
                      <div className="mt-0.5 flex justify-center gap-1 text-[9px]">
                        {!img.is_primary && (
                          <button onClick={() => makePrimary(img.id)} className="text-muted underline" title="Set as primary">★</button>
                        )}
                        <button onClick={() => removeImage(img.id)} className="text-red-700 underline" title="Remove">✕</button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {canWrite && (
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <input
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  placeholder="Paste an image URL…"
                  className="min-w-0 flex-1 rounded border border-line bg-paper px-2 py-1 text-xs outline-none focus:border-ink"
                />
                <button onClick={addUrl} disabled={busy || !urlInput.trim()} className="rounded border border-line px-2 py-1 text-xs hover:bg-wash disabled:opacity-50">
                  Add URL
                </button>
              </div>
            )}

            <div className="mb-3 grid grid-cols-2 gap-2 text-sm">
              <D label="Code" value={p.code} />
              <D label="Category" value={p.category ?? "—"} />
              <D label="Part number" value={p.part_number ?? "—"} />
              <D label="Manufacturer" value={p.manufacturer ?? "—"} />
              <D label="Cost" value={p.purchase_cost != null ? money2(p.purchase_cost) : "—"} />
              <D label="Price" value={p.selling_price != null ? money2(p.selling_price) : "—"} />
            </div>
            {p.description && <div className="mb-3 text-sm text-muted">{p.description}</div>}

            {error && <div className="mb-2 text-sm text-red-700">{error}</div>}

            <div className="flex flex-wrap gap-2">
              {src && (
                <button onClick={() => setFullscreen(true)} className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash">
                  Fullscreen
                </button>
              )}
              {canWrite && (
                <>
                  <button onClick={() => setEditing(true)} className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash">
                    Edit
                  </button>
                  <button onClick={() => fileRef.current?.click()} disabled={busy} className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash disabled:opacity-50">
                    {busy ? "Uploading…" : "Upload image"}
                  </button>
                  <input
                    ref={fileRef}
                    type="file"
                    accept="image/*"
                    hidden
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) upload(f);
                      e.target.value = "";
                    }}
                  />
                </>
              )}
              {canDelete && (
                <button onClick={remove} className="rounded border border-red-500/40 px-3 py-1.5 text-sm text-red-700 hover:bg-red-500/10">
                  Delete
                </button>
              )}
            </div>

            <ProductInsightsButton productId={id} name={p.name} />

            <ProductHistorySection productId={id} />

            {editing && (
              <EntityForm
                title={`Edit ${p.name}`}
                fields={formFields}
                initial={p as unknown as Record<string, unknown>}
                onClose={() => setEditing(false)}
                onSubmit={async (v) => {
                  await api.updateResource("products", id, v);
                  await reload();
                  onChanged();
                }}
              />
            )}
            {fullscreen && src && (
              <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/90 p-4" onClick={() => setFullscreen(false)}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={src} alt={p.name} className="max-h-full max-w-full object-contain" />
                <button onClick={() => setFullscreen(false)} className="absolute right-4 top-4 text-2xl text-white">✕</button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// A button in the product modal that opens a roomy insights popup.
function ProductInsightsButton({ productId, name }: { productId: number; name: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-4 border-t border-line pt-3">
      <button onClick={() => setOpen(true)}
        className="w-full rounded border border-line px-3 py-2 text-sm font-medium hover:bg-wash">
        📊 Product insights &amp; charts
      </button>
      {open && <ProductInsightsModal productId={productId} name={name} onClose={() => setOpen(false)} />}
    </div>
  );
}

// A product's own charts: current stock/value/revenue, and units bought vs sold
// over the last 12 months — all from the lot ledger and invoices.
function ProductInsightsModal({ productId, name, onClose }: {
  productId: number; name: string; onClose: () => void;
}) {
  const [data, setData] = useState<ProductAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.productAnalytics(productId)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e instanceof Error ? e.message : "Could not load insights"));
    return () => { alive = false; };
  }, [productId]);

  return (
    <Modal title={`${name || "Product"} · insights`} size="xl" onClose={onClose}>
      {error && <div className="text-sm text-red-700">{error}</div>}
      {!data && !error && <div className="text-sm text-muted">Loading…</div>}
      {data && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 text-center sm:grid-cols-4">
            <PStat label="On hand" value={num(data.on_hand)}
              tone={data.reorder_level != null && data.on_hand <= data.reorder_level ? "bad" : undefined} />
            <PStat label="Total sold" value={num(data.total_sold)} />
            <PStat label="Revenue" value={money2(data.revenue)} />
            <PStat label="Stock value" value={money2(data.stock_value)} />
          </div>

          <div className="rounded-lg border border-line p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wide text-muted">Units bought vs sold — last 12 months</span>
              <span className="text-[11px] text-muted">received {num(data.total_received)} · sold {num(data.total_sold)}</span>
            </div>
            <MiniLineChart
              xLabels={data.monthly.map((m) => m.month)}
              series={[
                { label: "Bought", color: "#2563eb", points: data.monthly.map((m) => m.received) },
                { label: "Sold", color: "#16a34a", points: data.monthly.map((m) => m.sold) },
              ]}
            />
          </div>
        </>
      )}
    </Modal>
  );
}

function PStat({ label, value, tone }: { label: string; value: string; tone?: "bad" }) {
  return (
    <div className="rounded border border-line p-2">
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`text-sm font-semibold ${tone === "bad" ? "text-red-700 dark:text-red-300" : ""}`}>{value}</div>
    </div>
  );
}

const HIST_STYLE: Record<string, string> = {
  RECEIVE: "text-green-700 dark:text-green-300",
  SALE: "text-blue-700 dark:text-blue-300",
  ADJUST: "text-yellow-700 dark:text-yellow-300",
  PRICE_CHANGE: "text-purple-700 dark:text-purple-300",
};

function ProductHistorySection({ productId }: { productId: number }) {
  const [hist, setHist] = useState<ProductHistoryType | null>(null);
  const [q, setQ] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .productHistory(productId)
      .then((r) => alive && setHist(r))
      .catch((e) => alive && setError(e instanceof Error ? e.message : "Could not load history"));
    return () => {
      alive = false;
    };
  }, [productId]);

  const events = hist?.events ?? [];
  const types = Array.from(new Set(events.map((e) => e.type)));
  const filtered = events
    .filter((e) => (typeFilter ? e.type === typeFilter : true))
    .filter((e) => {
      if (!q) return true;
      const hay = [e.type, e.warehouse, e.customer, e.invoice, e.user, e.note]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q.toLowerCase());
    })
    .sort((a, b) => {
      const cmp = (a.at ?? "").localeCompare(b.at ?? "");
      return sortDir === "desc" ? -cmp : cmp;
    });

  const money = (n: number | null | undefined) =>
    n == null ? "" : "₦" + Math.round(n).toLocaleString("en-NG");
  const when = (iso: string | null) =>
    iso ? new Date(iso).toLocaleString("en-NG", { dateStyle: "medium", timeStyle: "short" }) : "";

  return (
    <div className="mt-4 border-t border-line pt-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">History</span>
        {hist && (
          <span className="text-[11px] text-muted">
            {hist.counts.stock_events} stock · {hist.counts.price_changes} price changes
          </span>
        )}
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search…"
          className="ml-auto w-32 rounded border border-line bg-paper px-2 py-1 text-xs outline-none focus:border-ink"
        />
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded border border-line bg-paper px-2 py-1 text-xs"
        >
          <option value="">All</option>
          {types.map((t) => (
            <option key={t} value={t}>
              {t.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <button
          onClick={() => setSortDir((d) => (d === "desc" ? "asc" : "desc"))}
          className="rounded border border-line px-2 py-1 text-xs hover:bg-wash"
          title="Toggle sort"
        >
          {sortDir === "desc" ? "Newest ↓" : "Oldest ↑"}
        </button>
      </div>
      {error && <div className="text-xs text-red-700">{error}</div>}
      {!hist ? (
        <div className="text-xs text-muted">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="text-xs text-muted">No history yet.</div>
      ) : (
        <div className="max-h-64 space-y-1 overflow-y-auto">
          {filtered.map((e, i) => (
            <div key={i} className="flex items-start gap-2 rounded border border-line px-2 py-1.5 text-xs">
              <span className={`w-24 shrink-0 font-medium ${HIST_STYLE[e.type] ?? ""}`}>
                {e.type.replace(/_/g, " ")}
              </span>
              <div className="min-w-0 flex-1">
                {e.kind === "PRICE" ? (
                  <span>
                    Sell {money(e.selling_price)}
                    {e.purchase_cost != null ? ` · cost ${money(e.purchase_cost)}` : ""}
                  </span>
                ) : (
                  <span>
                    {e.quantity != null ? `${e.quantity > 0 ? "+" : ""}${e.quantity} units` : ""}
                    {e.warehouse ? ` · ${e.warehouse}` : ""}
                    {e.customer ? ` · to ${e.customer}` : ""}
                    {e.invoice ? ` · ${e.invoice}` : ""}
                    {e.unit_cost != null ? ` · @ ${money(e.unit_cost)}` : ""}
                  </span>
                )}
                <div className="text-muted">
                  {when(e.at)}
                  {e.user ? ` · by ${e.user}` : ""}
                  {e.note ? ` · ${e.note}` : ""}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function D({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div className="text-sm">{value}</div>
    </div>
  );
}
