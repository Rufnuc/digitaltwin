"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/Shell";
import {
  api,
  getRole,
  imageSrc,
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
.kb-prose img{max-width:100%;height:auto;border-radius:.5rem;margin:.7rem 0;border:1px solid var(--line,#e5e7eb)}
`;

function Chip({ children, onClick, active }: { children: React.ReactNode; onClick?: () => void; active?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full border px-2.5 py-0.5 text-[11px] ${
        active ? "border-ink bg-ink text-paper" : "border-line text-muted hover:bg-wash"
      }`}
    >
      {children}
    </button>
  );
}

export default function KnowledgePage() {
  const [items, setItems] = useState<KbArticleListItem[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [allTags, setAllTags] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState<string | null>(null);
  const [tag, setTag] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [editing, setEditing] = useState<KbArticleDetail | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDev, setIsDev] = useState(false);
  const canEdit = roleAtLeast(getRole(), "MANAGER");

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (tag) params.set("tag", tag);
      const r = await api.kbArticles(`?${params.toString()}`);
      setItems(r.items);
      setCategories(r.categories);
      setAllTags(r.tags);
      setIsDev(r.is_developer);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }, [q, tag]);

  useEffect(() => {
    load();
  }, [load]);

  const visible = cat ? items.filter((a) => (a.category || "General") === cat) : items;
  const pinned = visible.filter((a) => a.pinned);
  const byCategory = useMemo(() => {
    const groups: Record<string, KbArticleListItem[]> = {};
    for (const a of visible.filter((x) => !x.pinned)) {
      (groups[a.category || "General"] ||= []).push(a);
    }
    return Object.entries(groups).sort((a, b) => a[0].localeCompare(b[0]));
  }, [visible]);

  if (openId != null) {
    return (
      <div>
        <style>{PROSE_CSS}</style>
        <ArticleReader
          id={openId}
          canEdit={canEdit}
          onBack={() => setOpenId(null)}
          onEdit={(d) => setEditing(d)}
          onTag={(t) => { setTag(t); setOpenId(null); }}
          onChanged={load}
        />
        {editing && (
          <ArticleEditor isDev={isDev} article={editing === "new" ? null : editing} onClose={() => setEditing(null)}
            onSaved={async (id) => { setEditing(null); await load(); if (id) setOpenId(id); }} />
        )}
      </div>
    );
  }

  return (
    <div>
      <style>{PROSE_CSS}</style>
      <PageHeader title="Knowledgebase" subtitle="Guides, policies and notes for running the business." />

      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted">⌕</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search the knowledgebase…"
            className="w-full rounded-lg border border-line bg-paper py-2.5 pl-9 pr-3 text-sm outline-none focus:border-ink" />
        </div>
        {canEdit && (
          <button onClick={() => setEditing("new")} className="rounded-lg bg-ink px-4 py-2.5 text-sm font-medium text-paper">
            + New article
          </button>
        )}
      </div>

      {error && <div className="mb-3 text-sm text-red-700">{error}</div>}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[200px_1fr]">
        {/* Left sidebar: categories + tags */}
        <aside className="lg:sticky lg:top-4 lg:self-start">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted">Topics</div>
          <nav className="mt-2 space-y-1">
            <button onClick={() => setCat(null)}
              className={`block w-full rounded px-2 py-1.5 text-left text-sm ${cat === null ? "bg-wash font-medium" : "hover:bg-wash"}`}>
              All articles
            </button>
            {categories.map((c) => (
              <button key={c} onClick={() => setCat(c)}
                className={`block w-full rounded px-2 py-1.5 text-left text-sm ${cat === c ? "bg-wash font-medium" : "hover:bg-wash"}`}>
                {c}
              </button>
            ))}
          </nav>
          {allTags.length > 0 && (
            <>
              <div className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted">Tags</div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {tag && <Chip active onClick={() => setTag(null)}>✕ {tag}</Chip>}
                {allTags.filter((t) => t !== tag).map((t) => (
                  <Chip key={t} onClick={() => setTag(t)}>#{t}</Chip>
                ))}
              </div>
            </>
          )}
        </aside>

        {/* Main */}
        <div>
          {visible.length === 0 ? (
            <div className="rounded-lg border border-line bg-paper p-10 text-center text-sm text-muted">
              {q || tag ? "No articles match." : "No articles yet."}
            </div>
          ) : (
            <div className="space-y-7">
              {pinned.length > 0 && (
                <section>
                  <h2 className="mb-2 flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-muted">
                    ★ Featured
                  </h2>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {pinned.map((a) => <Card key={a.id} a={a} onOpen={() => setOpenId(a.id)} featured />)}
                  </div>
                </section>
              )}
              {byCategory.map(([c, arts]) => (
                <section key={c}>
                  <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">{c}</h2>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {arts.map((a) => <Card key={a.id} a={a} onOpen={() => setOpenId(a.id)} />)}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>
      </div>

      {editing && (
        <ArticleEditor isDev={isDev} article={editing === "new" ? null : editing} onClose={() => setEditing(null)}
          onSaved={async (id) => { setEditing(null); await load(); if (id) setOpenId(id); }} />
      )}
    </div>
  );
}

function Card({ a, onOpen, featured }: { a: KbArticleListItem; onOpen: () => void; featured?: boolean }) {
  return (
    <button onClick={onOpen}
      className={`group flex h-full flex-col rounded-xl border bg-paper p-4 text-left transition hover:border-ink hover:shadow-sm ${featured ? "border-amber-400/60" : "border-line"}`}>
      <div className="flex items-start gap-2">
        {featured && <span className="text-amber-500">★</span>}
        <span className="font-semibold group-hover:underline">{a.title}</span>
        {a.internal && (
          <span className="ml-auto rounded bg-wash px-1.5 py-0.5 text-[10px] font-medium text-muted">🔒 Internal</span>
        )}
      </div>
      <div className="mt-1 line-clamp-2 flex-1 text-[13px] text-muted">{a.excerpt || "Open to read."}</div>
      {a.tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {a.tags.slice(0, 4).map((t) => (
            <span key={t} className="rounded-full bg-wash px-2 py-0.5 text-[10px] text-muted">#{t}</span>
          ))}
        </div>
      )}
      <div className="mt-2 text-[11px] text-muted">
        Updated {a.updated_at ? new Date(a.updated_at).toLocaleDateString("en-NG", { dateStyle: "medium" }) : "—"}
        {a.version_no > 1 ? ` · v${a.version_no}` : ""}
      </div>
    </button>
  );
}

function ArticleReader({
  id, canEdit, onBack, onEdit, onTag, onChanged,
}: {
  id: number; canEdit: boolean; onBack: () => void;
  onEdit: (d: KbArticleDetail) => void; onTag: (t: string) => void; onChanged: () => void;
}) {
  const [art, setArt] = useState<KbArticleDetail | null>(null);
  const [versions, setVersions] = useState<KbVersion[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [voted, setVoted] = useState<boolean | null>(null);
  const [counts, setCounts] = useState<{ yes: number; no: number }>({ yes: 0, no: 0 });

  const load = useCallback(async () => {
    const [d, v] = await Promise.all([api.kbArticle(id), api.kbVersions(id)]);
    setArt(d);
    setVersions(v.items);
    setVoted(d.my_vote);
    setCounts({ yes: d.helpful_yes, no: d.helpful_no });
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function vote(helpful: boolean) {
    try {
      const r = await api.kbFeedback(id, helpful);
      setVoted(r.my_vote);
      setCounts({ yes: r.helpful_yes, no: r.helpful_no });
    } catch { /* ignore */ }
  }

  if (!art) return <div className="text-sm text-muted">Loading…</div>;
  const total = counts.yes + counts.no;

  return (
    <div className="mx-auto max-w-3xl">
      <button onClick={onBack} className="mb-4 text-sm text-muted hover:text-ink">← All articles</button>

      <div className="rounded-xl border border-line bg-paper p-6 sm:p-8">
        <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted">
          <span>{art.category || "General"}</span>
          {art.pinned && <span className="text-amber-500">★ Featured</span>}
          {art.internal && <span className="text-muted">🔒 Internal (dev only)</span>}
        </div>
        <h1 className="text-2xl font-bold">{art.title}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
          <span>Updated {art.updated_at ? new Date(art.updated_at).toLocaleString("en-NG", { dateStyle: "medium", timeStyle: "short" }) : "—"}</span>
          {art.updated_by && <span>· by {art.updated_by}</span>}
          <span>· version {art.version_no}</span>
        </div>
        {art.tags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {art.tags.map((t) => <Chip key={t} onClick={() => onTag(t)}>#{t}</Chip>)}
          </div>
        )}

        <hr className="my-5 border-line" />

        <div className="kb-prose" dangerouslySetInnerHTML={{ __html: renderMarkdown(art.body, (u) => imageSrc(u) || u) }} />

        {/* Was this helpful? */}
        <div className="mt-8 rounded-lg border border-line bg-wash/40 p-4 text-center">
          <div className="text-sm font-medium">Was this helpful?</div>
          <div className="mt-2 flex items-center justify-center gap-2">
            <button onClick={() => vote(true)}
              className={`rounded-lg border px-4 py-1.5 text-sm ${voted === true ? "border-green-500 bg-green-500/10 text-green-700 dark:text-green-300" : "border-line hover:bg-wash"}`}>
              👍 Yes
            </button>
            <button onClick={() => vote(false)}
              className={`rounded-lg border px-4 py-1.5 text-sm ${voted === false ? "border-red-500 bg-red-500/10 text-red-700 dark:text-red-300" : "border-line hover:bg-wash"}`}>
              👎 No
            </button>
          </div>
          {total > 0 && (
            <div className="mt-2 text-[11px] text-muted">{counts.yes} of {total} found this helpful</div>
          )}
        </div>

        {canEdit && (
          <div className="mt-6 flex flex-wrap gap-2 border-t border-line pt-4">
            <button onClick={() => onEdit(art)} className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-wash">Edit</button>
            <button onClick={async () => { await api.kbPin(id, !art.pinned); await load(); onChanged(); }}
              className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-wash">
              {art.pinned ? "Unfeature" : "★ Feature"}
            </button>
            <button onClick={() => setShowHistory((s) => !s)} className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-wash">
              {showHistory ? "Hide history" : `History (${versions.length})`}
            </button>
            <button onClick={async () => { if (!confirm("Archive this article?")) return; await api.kbArchive(id); onChanged(); onBack(); }}
              className="ml-auto rounded-lg border border-line px-3 py-1.5 text-sm text-muted hover:bg-wash">Archive</button>
          </div>
        )}

        {showHistory && (
          <div className="mt-4 rounded-lg border border-line bg-wash/50 p-4">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Change history</div>
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
  article, isDev, onClose, onSaved,
}: {
  article: KbArticleDetail | null; isDev: boolean; onClose: () => void; onSaved: (id?: number) => void;
}) {
  const [title, setTitle] = useState(article?.title ?? "");
  const [category, setCategory] = useState(article?.category ?? "");
  const [tags, setTags] = useState((article?.tags ?? []).join(", "));
  const [body, setBody] = useState(article?.body ?? "");
  const [internal, setInternal] = useState(article?.internal ?? false);
  const [note, setNote] = useState("");
  const [tab, setTab] = useState<"write" | "preview">("write");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const tagList = () => tags.split(",").map((t) => t.trim()).filter(Boolean);

  async function onPickImage(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setErr(null);
    try {
      const r = await api.kbUploadImage(file);
      setBody((b) => `${b}${b && !b.endsWith("\n") ? "\n\n" : ""}![${file.name}](${r.url})\n`);
      setTab("write");
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Image upload failed");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  async function save() {
    if (!title.trim()) { setErr("Give the article a title"); return; }
    setBusy(true);
    setErr(null);
    try {
      let saved: KbArticleDetail;
      if (article) {
        saved = await api.kbUpdateArticle(article.id, {
          title, category: category || null, tags: tagList(), body,
          ...(isDev ? { internal } : {}), change_note: note || null,
        });
      } else {
        saved = await api.kbCreateArticle({
          title, body, category: category || null, tags: tagList(),
          ...(isDev ? { internal } : {}),
        });
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
      <div className="max-h-[92vh] w-full max-w-2xl overflow-y-auto" onMouseDown={(e) => e.stopPropagation()}>
        <div className="rounded-xl border border-line bg-paper p-5 shadow-xl">
          <div className="mb-3 text-sm font-semibold">{article ? "Edit article" : "New article"}</div>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title"
            className="mb-2 w-full rounded-lg border border-line px-3 py-2 text-sm" />
          <div className="mb-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Category (e.g. How-to)"
              className="w-full rounded-lg border border-line px-3 py-2 text-sm" />
            <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="Tags (comma separated)"
              className="w-full rounded-lg border border-line px-3 py-2 text-sm" />
          </div>

          {isDev && (
            <label className="mb-2 flex items-center gap-2 rounded-lg border border-dashed border-line px-3 py-2 text-sm">
              <input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} />
              <span>🔒 Internal (developer only) — the business owner and staff won&apos;t see this article</span>
            </label>
          )}

          <div className="mb-1 flex items-center gap-2 text-xs">
            {(["write", "preview"] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)}
                className={`rounded px-2 py-1 ${tab === t ? "bg-ink text-paper" : "border border-line hover:bg-wash"}`}>
                {t === "write" ? "Write" : "Preview"}
              </button>
            ))}
            <label className="cursor-pointer rounded border border-line px-2 py-1 hover:bg-wash">
              {uploading ? "Uploading…" : "🖼 Insert image"}
              <input type="file" accept="image/*" onChange={onPickImage} className="hidden" disabled={uploading} />
            </label>
            <span className="ml-auto self-center text-[11px] text-muted"># Heading · **bold** · - list · [link](url)</span>
          </div>

          {tab === "write" ? (
            <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={14}
              placeholder="Write the article… headings, bold, lists and images are supported."
              className="w-full rounded-lg border border-line px-3 py-2 font-mono text-sm" />
          ) : (
            <div className="kb-prose min-h-[14rem] rounded-lg border border-line p-3"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(body, (u) => imageSrc(u) || u) || "<p style='color:#888'>Nothing to preview.</p>" }} />
          )}

          {article && (
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="What changed? (saved as this version's note)"
              className="mt-2 w-full rounded-lg border border-line px-3 py-2 text-sm" />
          )}
          {err && <div className="mt-2 text-xs text-red-700">{err}</div>}
          <div className="mt-3 flex justify-end gap-2">
            <button onClick={onClose} className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-wash">Cancel</button>
            <button onClick={save} disabled={busy} className="rounded-lg bg-ink px-4 py-1.5 text-sm font-medium text-paper disabled:opacity-40">
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
