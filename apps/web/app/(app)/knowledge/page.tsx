"use client";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/Shell";
import { Card } from "@/components/ui";
import {
  api,
  type AuditEvent,
  type KbArticleDetail,
  type KbArticleListItem,
  type KbVersion,
} from "@/lib/api";

type Tab = "articles" | "changes";

export default function KnowledgePage() {
  const [tab, setTab] = useState<Tab>("articles");
  return (
    <div>
      <PageHeader
        title="Knowledgebase"
        subtitle="Internal articles (SOPs, policies, notes) with full version history, plus a live feed of every change made across the app. Managers only."
      />
      <div className="mb-4 flex gap-2">
        {(["articles", "changes"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded px-3 py-1.5 text-sm ${
              tab === t ? "bg-ink text-paper" : "border border-line hover:bg-wash"
            }`}
          >
            {t === "articles" ? "Articles" : "Live changes"}
          </button>
        ))}
      </div>
      {tab === "articles" ? <Articles /> : <Changes />}
    </div>
  );
}

function Articles() {
  const [items, setItems] = useState<KbArticleListItem[]>([]);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [editing, setEditing] = useState<KbArticleDetail | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.kbArticles(q ? `?q=${encodeURIComponent(q)}` : "");
      setItems(r.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }, [q]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search articles…"
          className="w-64 rounded border border-line px-3 py-1.5 text-sm"
        />
        <button
          onClick={() => setEditing("new")}
          className="ml-auto rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper"
        >
          + New article
        </button>
      </div>
      {error && <div className="mb-2 text-sm text-red-700">{error}</div>}
      {items.length === 0 ? (
        <Card className="p-6 text-sm text-muted">No articles yet. Create the first one.</Card>
      ) : (
        <div className="space-y-2">
          {items.map((a) => (
            <Card key={a.id} className="p-3">
              <button onClick={() => setOpen(open === a.id ? null : a.id)} className="w-full text-left">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{a.title}</span>
                  <span className="text-[11px] text-muted">
                    v{a.version_no}
                    {a.category ? ` · ${a.category}` : ""}
                    {a.updated_by ? ` · ${a.updated_by}` : ""}
                    {a.updated_at ? ` · ${new Date(a.updated_at).toLocaleString("en-NG", { dateStyle: "short", timeStyle: "short" })}` : ""}
                  </span>
                </div>
              </button>
              {open === a.id && (
                <ArticleDetail
                  id={a.id}
                  onEdit={(d) => setEditing(d)}
                  onChanged={load}
                />
              )}
            </Card>
          ))}
        </div>
      )}
      {editing && (
        <ArticleEditor
          article={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await load();
          }}
        />
      )}
    </div>
  );
}

function ArticleDetail({
  id,
  onEdit,
  onChanged,
}: {
  id: number;
  onEdit: (d: KbArticleDetail) => void;
  onChanged: () => void;
}) {
  const [art, setArt] = useState<KbArticleDetail | null>(null);
  const [versions, setVersions] = useState<KbVersion[]>([]);
  const [showVersions, setShowVersions] = useState(false);

  const load = useCallback(async () => {
    const [d, v] = await Promise.all([api.kbArticle(id), api.kbVersions(id)]);
    setArt(d);
    setVersions(v.items);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (!art) return <div className="mt-2 text-xs text-muted">Loading…</div>;

  return (
    <div className="mt-2 border-t border-line pt-2">
      <div className="whitespace-pre-wrap text-sm">{art.body || <span className="text-muted">No content.</span>}</div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button onClick={() => onEdit(art)} className="rounded border border-line px-3 py-1.5 text-xs hover:bg-wash">
          Edit
        </button>
        <button
          onClick={() => setShowVersions((s) => !s)}
          className="rounded border border-line px-3 py-1.5 text-xs hover:bg-wash"
        >
          {showVersions ? "Hide" : "Version history"} ({versions.length})
        </button>
        <button
          onClick={async () => {
            if (!confirm("Archive this article?")) return;
            await api.kbArchive(id);
            onChanged();
          }}
          className="rounded border border-line px-3 py-1.5 text-xs text-muted hover:bg-wash"
        >
          Archive
        </button>
      </div>
      {showVersions && (
        <ol className="mt-2 space-y-1">
          {versions.map((v) => (
            <li key={v.version_no} className="rounded border border-line p-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-medium">v{v.version_no}</span>
                <button
                  onClick={async () => {
                    if (!confirm(`Restore v${v.version_no}? This creates a new version with that content.`)) return;
                    await api.kbRestore(id, v.version_no);
                    await load();
                    onChanged();
                  }}
                  className="text-ink underline decoration-dotted"
                >
                  restore
                </button>
              </div>
              <div className="text-muted">
                {v.change_note ?? "—"} · {v.changed_by ?? "—"}
                {v.changed_at ? ` · ${new Date(v.changed_at).toLocaleString()}` : ""}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function ArticleEditor({
  article,
  onClose,
  onSaved,
}: {
  article: KbArticleDetail | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(article?.title ?? "");
  const [category, setCategory] = useState(article?.category ?? "");
  const [body, setBody] = useState(article?.body ?? "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    if (!title.trim()) {
      setErr("Title is required");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      if (article) {
        await api.kbUpdateArticle(article.id, {
          title,
          category: category || null,
          body,
          change_note: note || null,
        });
      } else {
        await api.kbCreateArticle({ title, body, category: category || null });
      }
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4" onMouseDown={onClose}>
      <div className="w-full max-w-2xl" onMouseDown={(e) => e.stopPropagation()}>
        <div className="rounded-lg border border-line bg-paper p-4 shadow-xl">
          <div className="mb-3 text-sm font-medium">{article ? `Edit — v${article.version_no} → v${article.version_no + 1}` : "New article"}</div>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title"
            className="mb-2 w-full rounded border border-line px-3 py-2 text-sm"
          />
          <input
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="Category (optional, e.g. Sales, Policy)"
            className="mb-2 w-full rounded border border-line px-3 py-2 text-sm"
          />
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Write the article…"
            rows={12}
            className="mb-2 w-full rounded border border-line px-3 py-2 font-mono text-sm"
          />
          {article && (
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="What changed? (saved with this version)"
              className="mb-2 w-full rounded border border-line px-3 py-2 text-sm"
            />
          )}
          {err && <div className="mb-2 text-xs text-red-700">{err}</div>}
          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash">
              Cancel
            </button>
            <button
              onClick={save}
              disabled={busy}
              className="rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper disabled:opacity-40"
            >
              {busy ? "Saving…" : "Save version"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Changes() {
  const [items, setItems] = useState<AuditEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.activityLog("?limit=60");
      setItems(r.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load changes");
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 15_000); // live-ish feed
    return () => clearInterval(t);
  }, [load]);

  return (
    <Card className="p-3">
      <div className="mb-2 text-xs text-muted">
        Every change across the app, newest first — refreshes automatically.
      </div>
      {error && <div className="mb-2 text-sm text-red-700">{error}</div>}
      {items.length === 0 ? (
        <div className="text-sm text-muted">No activity recorded yet.</div>
      ) : (
        <ul className="divide-y divide-line">
          {items.map((e) => (
            <li key={e.id} className="py-2 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{e.summary ?? `${e.action} ${e.entity_type ?? ""}`}</span>
                <span className="whitespace-nowrap text-[11px] text-muted">
                  {e.at ? new Date(e.at).toLocaleString("en-NG", { dateStyle: "short", timeStyle: "short" }) : ""}
                </span>
              </div>
              <div className="text-[11px] text-muted">
                {e.action}
                {e.entity_type ? ` · ${e.entity_type}${e.entity_id ? ` #${e.entity_id}` : ""}` : ""}
                {e.user_name ? ` · ${e.user_name}` : ""}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
