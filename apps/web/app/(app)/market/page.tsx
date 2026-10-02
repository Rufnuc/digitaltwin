"use client";
import { useEffect, useState } from "react";
import { api, getRole, type MarketSummary } from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card, ProvenanceBadge } from "@/components/ui";

const REFRESH_ROLES = ["ADMIN", "OWNER", "MANAGER", "ANALYST"];

function fmtValue(v: number, unit: string) {
  if (unit.startsWith("NGN")) return `₦${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  if (unit === "%") return `${v.toFixed(1)}%`;
  return v.toLocaleString();
}

export default function MarketPage() {
  const [summary, setSummary] = useState<MarketSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [checks, setChecks] = useState<import("@/lib/api").MarketSourceCheck[] | null>(null);
  const canRefresh = REFRESH_ROLES.includes(getRole() ?? "");

  async function testSources() {
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      const r = await api.marketDiagnostics();
      setChecks(r.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Diagnostics failed");
    } finally {
      setBusy(false);
    }
  }

  const load = () => api.marketSummary().then(setSummary).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  async function refresh() {
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      const r = await api.refreshMarket();
      if (!r.reached_any && r.errors && r.errors.length > 0) {
        // Nothing came back — show exactly which sources failed and why, so this is
        // debuggable (usually the API server can't reach the internet).
        setError(
          "Couldn't reach the data sources from the server:\n" +
            r.errors.map((x) => `• ${x.source}: ${x.error}`).join("\n"),
        );
      } else {
        const parts = [
          `Fetched from ${r.sources.join(", ") || "—"} — ${r.indicators_ingested} new / ${r.indicators_updated} updated indicators, ${r.news_ingested} news (as of ${r.as_of}).`,
        ];
        if (r.errors && r.errors.length > 0) {
          parts.push(`Some sources were unreachable: ${r.errors.map((x) => x.source).join(", ")}.`);
        }
        setMsg(parts.join(" "));
      }
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Refresh failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Market Intelligence"
        subtitle="Real external economic data for Nigeria — World Bank indicators, live FX, and business news. Every fact keeps its source, date and link."
      />

      <div className="mb-4 flex items-center gap-3">
        {canRefresh ? (
          <button
            onClick={refresh}
            disabled={busy}
            className="rounded bg-ink px-4 py-2 text-sm font-medium text-paper disabled:opacity-50"
          >
            {busy ? "Fetching real data…" : "Refresh from sources"}
          </button>
        ) : (
          <span className="text-xs text-muted">Analyst or higher can refresh from sources.</span>
        )}
        {canRefresh && (
          <button
            onClick={testSources}
            disabled={busy}
            className="rounded border border-line px-3 py-2 text-sm hover:bg-wash disabled:opacity-50"
          >
            Test data sources
          </button>
        )}
        {msg && <span className="text-xs text-green-700 dark:text-green-300">{msg}</span>}
        {error && (
          <span className="whitespace-pre-line text-sm text-red-700">{error}</span>
        )}
      </div>

      {checks && (
        <Card className="mb-4 p-3">
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">
            Source connectivity (from your server)
          </div>
          <ul className="space-y-1 text-sm">
            {checks.map((c) => (
              <li key={c.source} className="flex items-center justify-between gap-3">
                <span>
                  <span className={c.ok ? "text-green-700 dark:text-green-300" : "text-red-700"}>
                    {c.ok ? "✓" : "✗"}
                  </span>{" "}
                  {c.source}
                </span>
                <span className="text-[11px] text-muted">
                  {c.status ? `HTTP ${c.status}` : ""}
                  {c.error ? ` · ${c.error}` : ""} · {c.ms}ms
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-2 text-[11px] text-muted">
            All ✗ → your API server has no outbound internet (fix egress on your host).
            Some ✓ / some ✗ with HTTP 403 → that source is blocking your server&apos;s IP.
          </div>
        </Card>
      )}

      {!summary ? (
        <div className="text-sm text-muted">Loading…</div>
      ) : !summary.has_data ? (
        <Card className="p-6 text-sm text-muted">
          No market data yet. Click “Refresh from sources” to fetch real economic indicators and
          news.
        </Card>
      ) : (
        <>
          <div className="mb-2 text-sm font-medium">Economic indicators</div>
          <div className="mb-6 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {summary.indicators.map((i) => (
              <Card key={i.indicator} className="p-4">
                <div className="flex items-start justify-between">
                  <div className="text-xs uppercase tracking-wide text-muted">{i.label}</div>
                  <ProvenanceBadge origin={i.data_origin} />
                </div>
                <div className="mt-1 text-2xl font-semibold tabular-nums">
                  {fmtValue(i.value, i.unit)}
                </div>
                <div className="mt-0.5 text-[11px] text-muted">
                  {i.period} ·{" "}
                  <a
                    href={i.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline decoration-dotted"
                  >
                    {i.source}
                  </a>
                </div>
                {i.implication && (
                  <div className="mt-2 rounded border border-line bg-wash p-2 text-[11px] text-muted">
                    <span className="font-mono text-[9px] uppercase">Possible impact · assumption</span>
                    <div>{i.implication}</div>
                  </div>
                )}
              </Card>
            ))}
          </div>

          <div className="mb-2 text-sm font-medium">Relevant business news</div>
          <Card className="p-4">
            {summary.top_news.length === 0 ? (
              <div className="text-sm text-muted">No relevant news items.</div>
            ) : (
              <ul className="divide-y divide-line">
                {summary.top_news.map((n) => (
                  <li key={n.id} className="py-2">
                    <div className="flex items-start justify-between gap-3">
                      <a
                        href={n.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm font-medium hover:underline"
                      >
                        {n.title}
                      </a>
                      <span className="whitespace-nowrap text-[11px] text-muted">
                        rel {(n.relevance * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="text-[11px] text-muted">
                      {n.source} · {n.published}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <p className="mt-3 text-xs text-muted">{summary.note}</p>
        </>
      )}
    </div>
  );
}
