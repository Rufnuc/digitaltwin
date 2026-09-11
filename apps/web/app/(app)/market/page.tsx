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
  const canRefresh = REFRESH_ROLES.includes(getRole() ?? "");

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
      setMsg(
        `Fetched from ${r.sources.join(", ")} — ${r.indicators_ingested} new / ${r.indicators_updated} updated indicators, ${r.news_ingested} news (as of ${r.as_of}).`,
      );
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
        {msg && <span className="text-xs text-green-800">{msg}</span>}
        {error && <span className="text-sm text-red-700">{error}</span>}
      </div>

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
