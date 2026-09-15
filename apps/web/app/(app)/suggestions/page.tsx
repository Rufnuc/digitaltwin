"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  type NotificationItem,
  type AlertItem,
  type ReorderItem,
  type ReorderPlan,
} from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card } from "@/components/ui";

// The action list: what to do now, decided by the quant brain — the parts to
// reorder, most important (most money at risk) first — so staff who won't type
// questions to Benfieg still see what needs doing. Below it, other things worth
// knowing (low stock, at-risk customers, market moves) from the alert feed.

const naira = (n: number | null | undefined) =>
  n == null ? "—" : "₦" + Math.round(n).toLocaleString("en-NG");

const SEV_DOT: Record<string, string> = {
  high: "bg-red-500",
  medium: "bg-yellow-500",
  info: "bg-blue-500",
  low: "bg-muted",
};
const SEV_ORDER: Record<string, number> = { high: 0, medium: 1, info: 2, low: 3 };

export default function SuggestionsPage() {
  const router = useRouter();
  const [plan, setPlan] = useState<ReorderPlan | null>(null);
  const [alerts, setAlerts] = useState<{ title: string; body: string | null; severity: string; category: string; link: string | null; key: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [sample, setSample] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (demo: boolean) => {
    setLoading(true);
    setError(null);
    try {
      const [rp, notifs, al] = await Promise.all([
        api.reorderPlan(demo).catch(() => null),
        api.generateNotifications().then(() => api.notifications()).catch(() => ({ items: [] as NotificationItem[], unread_count: 0 })),
        api.alerts().catch(() => ({ items: [] as AlertItem[] })),
      ]);
      setPlan(rp);
      // Merge alert-style items (dedup by title), reorder handled separately above.
      const merged = [
        ...notifs.items
          .filter((n) => n.category !== "reorder") // reorder is the action list now
          .map((n) => ({ key: `n${n.id}`, title: n.title, body: n.body, severity: n.severity || "info", category: n.category, link: n.link })),
        ...al.items.map((a) => ({ key: `a${a.id}`, title: a.title, body: a.body, severity: a.severity || "info", category: a.category, link: null })),
      ];
      const seen = new Set<string>();
      const unique = merged.filter((s) => {
        const k = s.title.trim().toLowerCase();
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
      });
      unique.sort((a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9));
      setAlerts(unique);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the action list");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(false);
  }, [load]);

  const orderNow = (plan?.items ?? []).filter((i) => i.recommendation_status === "READY");
  const needsReview = (plan?.items ?? []).filter((i) => i.recommendation_status !== "READY");
  const nothingLive = !loading && plan != null && orderNow.length === 0 && needsReview.length === 0 && !sample;

  return (
    <div>
      <PageHeader
        title="Action list"
        subtitle="What to do now — the parts to reorder, most important first, decided from your real sales and stock. No need to ask Benfieg; it's here."
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <button
          onClick={() => load(sample)}
          disabled={loading}
          className="rounded bg-ink px-4 py-2 text-sm font-medium text-paper disabled:opacity-40"
        >
          {loading ? "Checking…" : "Refresh"}
        </button>
        <button
          onClick={() => router.push("/assistant")}
          className="rounded border border-line px-4 py-2 text-sm hover:bg-wash"
        >
          Ask Benfieg
        </button>
        {plan != null && (
          <span className="ml-auto text-sm text-muted">
            {orderNow.length} to order{orderNow.length ? ` · ${naira(plan.total_estimated_restock_cost)} to restock` : ""}
          </span>
        )}
      </div>

      {error && <div className="mb-4 text-sm text-red-700">{error}</div>}
      {sample && (
        <div className="mb-4 rounded border border-yellow-500/40 bg-yellow-500/10 px-3 py-2 text-xs text-yellow-700 dark:text-yellow-300">
          Showing a sample using demo data — for illustration only, not your live figures.
        </div>
      )}

      {/* Reorder now — the action list */}
      <h2 className="mb-2 text-sm font-semibold">Reorder now</h2>
      {orderNow.length === 0 && !loading && (
        <Card className="mb-4 p-4 text-sm text-muted">
          Nothing needs ordering right now.
          {nothingLive && (
            <>
              {" "}
              <button
                onClick={() => { setSample(true); load(true); }}
                className="underline decoration-dotted"
              >
                Preview with sample data
              </button>
            </>
          )}
        </Card>
      )}
      <div className="mb-6 space-y-2">
        {orderNow.map((i) => (
          <ReorderRow key={i.product_id} item={i} onOpen={() => router.push("/stock")} />
        ))}
      </div>

      {/* Needs a look — quality gate tripped */}
      {needsReview.length > 0 && (
        <>
          <h2 className="mb-2 text-sm font-semibold">
            Needs a look <span className="font-normal text-muted">({needsReview.length})</span>
          </h2>
          <p className="mb-2 text-xs text-muted">
            These may need reordering, but sales history is too thin to be sure — check them yourself.
          </p>
          <div className="mb-6 space-y-2">
            {needsReview.map((i) => (
              <ReorderRow key={i.product_id} item={i} review onOpen={() => router.push("/stock")} />
            ))}
          </div>
        </>
      )}

      {/* Also worth knowing — the alert feed */}
      {alerts.length > 0 && (
        <>
          <h2 className="mb-2 text-sm font-semibold">Also worth knowing</h2>
          <div className="space-y-2">
            {alerts.map((s) => (
              <Card
                key={s.key}
                onClick={() => s.link && router.push(s.link)}
                className={`border-line p-3 ${s.link ? "cursor-pointer hover:bg-wash" : ""}`}
              >
                <div className="flex items-start gap-3">
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${SEV_DOT[s.severity] ?? SEV_DOT.low}`} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium">{s.title}</span>
                      <span className="rounded-full border border-line px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted">
                        {s.category}
                      </span>
                    </div>
                    {s.body && <p className="mt-1 text-sm text-muted">{s.body}</p>}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function ReorderRow({ item, review, onOpen }: { item: ReorderItem; review?: boolean; onOpen: () => void }) {
  return (
    <Card
      onClick={onOpen}
      className={`cursor-pointer border p-3 hover:bg-wash ${review ? "border-yellow-500/30" : "border-line"}`}
    >
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{item.product_name}</span>
            <span className="text-[11px] text-muted">{item.product_code}</span>
            {item.abc_class && (
              <span className="rounded-full border border-line px-1.5 py-0.5 text-[10px] font-medium text-muted">
                Class {item.abc_class}
              </span>
            )}
          </div>
          <div className="mt-1 text-xs text-muted">
            {review ? "Money at risk if it runs out: " : "Protects "}
            <span className="font-medium text-ink">{naira(item.margin_at_risk_over_horizon)}</span>
            {review ? "" : " of margin at risk"}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-sm font-semibold">Order {Math.round(item.recommended_order_quantity)}</div>
          <div className="text-xs text-muted">{naira(item.estimated_order_cost)}</div>
        </div>
      </div>
    </Card>
  );
}
