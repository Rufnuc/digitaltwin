"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type NotificationItem, type AlertItem } from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card, ProvenanceBadge } from "@/components/ui";

// A "suggestion" is a proactive, actionable item the business should look at.
// We combine two real sources: generated notifications (low stock, churn risk,
// FX moves, etc.) and dashboard alerts. Benfieg answers questions on demand;
// this page surfaces what needs attention without being asked.

const SEV_ORDER: Record<string, number> = { high: 0, medium: 1, info: 2, low: 3 };

const SEV_STYLE: Record<string, string> = {
  high: "border-red-500/40 bg-red-500/10",
  medium: "border-yellow-500/40 bg-yellow-500/10",
  info: "border-blue-500/40 bg-blue-500/10",
  low: "border-line bg-wash",
};

const SEV_DOT: Record<string, string> = {
  high: "bg-red-500",
  medium: "bg-yellow-500",
  info: "bg-blue-500",
  low: "bg-muted",
};

interface Suggestion {
  key: string;
  title: string;
  body: string | null;
  category: string;
  severity: string;
  link: string | null;
  origin?: string;
}

function fromNotification(n: NotificationItem): Suggestion {
  return {
    key: `n${n.id}`,
    title: n.title,
    body: n.body,
    category: n.category,
    severity: n.severity || "info",
    link: n.link,
  };
}

function fromAlert(a: AlertItem): Suggestion {
  return {
    key: `a${a.id}`,
    title: a.title,
    body: a.body,
    category: a.category,
    severity: a.severity || "info",
    link: null,
    origin: a.data_origin,
  };
}

export default function SuggestionsPage() {
  const router = useRouter();
  const [items, setItems] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Regenerate from current conditions, then read the fresh list + alerts.
      await api.generateNotifications().catch(() => undefined);
      const [notifs, alerts] = await Promise.all([
        api.notifications().catch(() => ({ items: [] as NotificationItem[], unread_count: 0 })),
        api.alerts().catch(() => ({ items: [] as AlertItem[] })),
      ]);
      const merged: Suggestion[] = [
        ...notifs.items.map(fromNotification),
        ...alerts.items.map(fromAlert),
      ];
      // De-duplicate by title (an alert and a notification can overlap).
      const seen = new Set<string>();
      const unique = merged.filter((s) => {
        const k = s.title.trim().toLowerCase();
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
      });
      unique.sort(
        (a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9),
      );
      setItems(unique);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load suggestions");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <PageHeader
        title="Suggestions"
        subtitle="Things worth your attention right now — low stock, reorder needs, at-risk customers, cost and market changes. These come from your real business data and market signals. Ask Benfieg for the full analysis or a what-if."
      />

      <div className="mb-4 flex items-center gap-3">
        <button
          onClick={load}
          disabled={loading}
          className="rounded bg-ink px-4 py-2 text-sm font-medium text-paper disabled:opacity-40"
        >
          {loading ? "Checking…" : "Refresh suggestions"}
        </button>
        <button
          onClick={() => router.push("/assistant")}
          className="rounded border border-line px-4 py-2 text-sm hover:bg-wash"
        >
          Ask Benfieg
        </button>
      </div>

      {error && <div className="mb-4 text-sm text-red-700">{error}</div>}

      {!loading && items.length === 0 && !error && (
        <Card className="p-6 text-center text-sm text-muted">
          Nothing needs your attention right now. Everything looks in order.
        </Card>
      )}

      <div className="space-y-2">
        {items.map((s) => (
          <Card
            key={s.key}
            className={`border p-3 ${SEV_STYLE[s.severity] ?? SEV_STYLE.low} ${
              s.link ? "cursor-pointer hover:opacity-90" : ""
            }`}
          >
            <div
              onClick={() => s.link && router.push(s.link)}
              className="flex items-start gap-3"
            >
              <span
                className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                  SEV_DOT[s.severity] ?? SEV_DOT.low
                }`}
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">{s.title}</span>
                  <span className="rounded-full border border-line px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted">
                    {s.category}
                  </span>
                  {s.origin && <ProvenanceBadge origin={s.origin} />}
                </div>
                {s.body && <p className="mt-1 text-sm text-muted">{s.body}</p>}
                {s.link && (
                  <span className="mt-1 inline-block text-xs text-ink underline decoration-dotted">
                    View
                  </span>
                )}
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
