"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/Shell";
import {
  api,
  getRole,
  type KbArticleDetail,
  type KbArticleListItem,
  type KbVersion,
} from "@/lib/api";
import { renderMarkdown } from "@/lib/markdown";
import { roleAtLeast } from "@/lib/roles";

const PROSE_CSS = `
.kb-prose{color:var(--ink,inherit);font-size:15px;line-height:1.7}
.kb-prose h1{font-size:1.6rem;font-weight:700;margin:0 0 .6rem}
.kb-prose h2{font-size:1.2rem;font-weight:700;margin:1.4rem 0 .5rem;padding-bottom:.25rem;border-bottom:1px solid var(--line,#e5e7eb)}
.kb-prose h3{font-size:1.02rem;font-weight:600;margin:1.1rem 0 .4rem}
.kb-prose p{margin:.6rem 0}
.kb-prose ul,.kb-prose ol{margin:.5rem 0 .8rem;padding-left:1.4rem}
.kb-prose li{margin:.3rem 0}
.kb-prose a{color:#2563eb;text-decoration:underline;text-decoration-style:dotted}
.kb-prose code{background:var(--wash,#f4f4f5);padding:.1rem .35rem;border-radius:.25rem;font-size:.9em}
.kb-prose blockquote{border-left:3px solid var(--line,#e5e7eb);margin:.6rem 0;padding:.2rem 0 .2rem .9rem;color:var(--muted,#6b7280)}
.kb-prose strong{font-weight:650}
`;

export default function KnowledgePage() {
  const [items, setItems] = useState<KbArticleListItem[]>([]);
  const [q, setQ] = useState("");
  const [openId, setOpenId] = useState<number | null>(null);
  const [editing, setEditing] = useState<KbArticleDetail | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canEdit = roleAtLeast(getRole(), "MANAGER");

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

  const byCategory = useMemo(() => {
    const groups: Record<string, KbArticleListItem[]> = {};
    for (const a of items) {
      const k = a.category || "General";
      (groups[k] ||= []).push(a);
    }
    return Object.entries(groups).sort((a, b) => a[0].localeCompare(b[0]));
  }, [items]);

  return (
    <div>
      <style>{PROSE_CSS}</style>

      {openId != null ? (
        <ArticleReader
          id={openId}
          canEdit={canEdit}
          onBack={() => setOpenId(null)}
          onEdit={(d) => setEditing(d)}
          onChanged={load}
        />
      ) : (
        <>
          <PageHeader
            title="Knowledgebase"
            subtitle="Guides, policies and notes for running the business. Search or browse by topic."
          />

          <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative flex-1">
              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted">⌕</span>
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search the knowledgebase…"
                className="w-full rounded-lg border border-line bg-paper py-2.5 pl-9 pr-3 text-sm outline-none focus:border-ink"
              />
            </div>
            {canEdit && (
              <button
                onClick={() => setEditing("new")}
                className="rounded-lg bg-ink px-4 py-2.5 text-sm font-medium text-paper"
              >
                + New article
              </button>
            )}
          </div>

          {error && <div className="mb-3 text-sm text-red-700">{error}</div>}

          {items.length === 0 ? (
            <div className="rounded-lg border border-line bg-paper p-10 text-center text-sm text-muted">
              {q ? "No articles match your search." : "No articles yet."}
            </div>
          ) : (
            <div className="space-y-7">
              {byCategory.map(([cat, arts]) => (
                <section key={cat}>
                  <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">{cat}</h2>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {arts.map((a) => (
                      <button
                        key={a.id}
                        onClick={() => setOpenId(a.id)}
                        className="group flex h-full flex-col rounded-xl border border-line bg-paper p-4 text-left transition hover:border-ink hover:shadow-sm"
                      >
                        <div className="font-semibold group-hover:underline">{a.title}</div>
                        <div className="mt-1 line-clamp-3 flex-1 text-[13px] text-muted">
                          {a.excerpt || "Open to read."}
                        </div>
                        <div className="mt-3 text-[11px] text-muted">
                          Updated{" "}
                          {a.updated_at
                            ? new Date(a.updated_at).toLocaleDateString("en-NG", { dateStyle: "medium" })
                            : "—"}
                          {a.version_no > 1 ? ` · v${a.version_no}` : ""}
                        </div>
                      </button>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </>
      )}

      {editing && (
        <ArticleEditor
          article={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={async (id) => {
            setEditing(null);
            await load();
            if (id) setOpenId(id);
          }}
        />
      )}
    </div>
  );
}

function ArticleReader({
  id,
  canEdit,
  onBack,
  onEdit,
  onChanged,
}: {
  id: number;
  canEdit: boolean;
  onBack: () => void;
  onEdit: (d: KbArticleDetail) => void;
  onChanged: () => void;
}) {
  const [art, setArt] = useState<KbArticleDetail | null>(null);
  const [versions, setVersions] = useState<KbVersion[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  const load = useCallback(async () => {
    const [d, v] = await Promise.all([api.kbArticle(id), api.kbVersions(id)]);
    setArt(d);
    setVersions(v.items);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (!art) return <div className="text-sm text-muted">Loading…</div>;

  return (
    <div className="mx-auto max-w-3xl">
      <button onClick={onBack} className="mb-4 text-sm text-muted hover:text-ink">
        ← All articles
      </button>

      <div className="rounded-xl border border-line bg-paper p-6 sm:p-8">
        <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
          {art.category || "General"}
        </div>
        <h1 className="text-2xl font-bold">{art.title}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
          <span>
            Updated{" "}
            {art.updated_at
              ? new Date(art.updated_at).toLocaleString("en-NG", { dateStyle: "medium", timeStyle: "short" })
              : "—"}
          </span>
          {art.updated_by && <span>· by {art.updated_by}</span>}
          <span>· version {art.version_no}</span>
        </div>

        <hr className="my-5 border-line" />

        <div
          className="kb-prose"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(art.body) }}
        />

        {canEdit && (
          <div className="mt-8 flex flex-wrap gap-2 border-t border-line pt-4">
            <button
              onClick={() => onEdit(art)}
              className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-wash"
            >
              Edit
            </button>
            <button
              onClick={() => setShowHistory((s) => !s)}
              className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-wash"
            >
              {showHistory ? "Hide history" : `History (${versions.length})`}
            </button>
            <button
              onClick={async () => {
                if (!confirm("Archive this article? It will be hidden from the knowledgebase.")) return;
                await api.kbArchive(id);
                onChanged();
                onBack();
              }}
              className="ml-auto rounded-lg border border-line px-3 py-1.5 text-sm text-muted hover:bg-wash"
            >
              Archive
            </button>
          </div>
        )}

        {showHistory && (
          <div className="mt-4 rounded-lg border border-line bg-wash/50 p-4">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
              Change history
            </div>
            <ol className="relative space-y-3 border-l border-line pl-4">
              {versions.map((v) => (
                <li key={v.version_no} className="relative">
                  <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border border-line bg-paper" />
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-sm font-medium">v{v.version_no} — {v.change_note ?? "updated"}</span>
                    <span className="whitespace-nowrap text-[11px] text-muted">
                      {v.changed_at ? new Date(v.changed_at).toLocaleString("en-NG", { dateStyle: "medium", timeStyle: "short" }) : ""}
                    </span>
                  </div>
                  {v.changed_by && <div className="text-[11px] text-muted">by {v.changed_by}</div>}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
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
  onSaved: (id?: number) => void;
}) {
  const [title, setTitle] = useState(article?.title ?? "");
  const [category, setCategory] = useState(article?.category ?? "");
  const [body, setBody] = useState(article?.body ?? "");
  const [note, setNote] = useState("");
  const [tab, setTab] = useState<"write" | "preview">("write");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    if (!title.trim()) {
      setErr("Give the article a title");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      let saved: KbArticleDetail;
      if (article) {
        saved = await api.kbUpdateArticle(article.id, {
          title,
          category: category || null,
          body,
          change_note: note || null,
        });
      } else {
        saved = await api.kbCreateArticle({ title, body, category: category || null });
      }
      onSaved(saved.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4" onMouseDown={onClose}>
      <style>{PROSE_CSS}</style>
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto" onMouseDown={(e) => e.stopPropagation()}>
        <div className="rounded-xl border border-line bg-paper p-5 shadow-xl">
          <div className="mb-3 text-sm font-semibold">{article ? "Edit article" : "New article"}</div>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title"
            className="mb-2 w-full rounded-lg border border-line px-3 py-2 text-sm"
          />
          <input
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="Category (e.g. How-to, Sales, Policy)"
            className="mb-3 w-full rounded-lg border border-line px-3 py-2 text-sm"
          />

          <div className="mb-1 flex gap-2 text-xs">
            {(["write", "preview"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded px-2 py-1 ${tab === t ? "bg-ink text-paper" : "border border-line hover:bg-wash"}`}
              >
                {t === "write" ? "Write" : "Preview"}
              </button>
            ))}
            <span className="ml-auto self-center text-[11px] text-muted">
              Formatting: # Heading, **bold**, - list, [link](url)
            </span>
          </div>

          {tab === "write" ? (
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Write the article… headings, bold and lists are supported."
              rows={14}
              className="w-full rounded-lg border border-line px-3 py-2 font-mono text-sm"
            />
          ) : (
            <div
              className="kb-prose min-h-[14rem] rounded-lg border border-line p-3"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(body) || "<p style='color:#888'>Nothing to preview.</p>" }}
            />
          )}

          {article && (
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="What changed? (saved as this version's note)"
              className="mt-2 w-full rounded-lg border border-line px-3 py-2 text-sm"
            />
          )}
          {err && <div className="mt-2 text-xs text-red-700">{err}</div>}
          <div className="mt-3 flex justify-end gap-2">
            <button onClick={onClose} className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-wash">
              Cancel
            </button>
            <button
              onClick={save}
              disabled={busy}
              className="rounded-lg bg-ink px-4 py-1.5 text-sm font-medium text-paper disabled:opacity-40"
            >
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
