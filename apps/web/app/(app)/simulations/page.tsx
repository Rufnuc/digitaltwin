"use client";
import { useCallback, useEffect, useState } from "react";
import { api, type PlainSim, type SimOutcome, type Simulation } from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card } from "@/components/ui";

// A plain-language "what if" tool. Three ways in: run every idea automatically,
// try your own numbers, or reopen a past run. No jargon, no configuration.

const naira = (n: number | null | undefined) =>
  n == null ? "—" : "₦" + Math.round(n).toLocaleString("en-NG");

const VERDICT_STYLE: Record<string, string> = {
  better: "text-green-700 dark:text-green-300",
  worse: "text-red-700 dark:text-red-300",
  "about the same": "text-muted",
};

type Tab = "auto" | "manual" | "history";

export default function SimulationsPage() {
  const [tab, setTab] = useState<Tab>("auto");

  return (
    <div>
      <PageHeader
        title="What-if simulator"
        subtitle="See how a change — prices, sales, or supplier cost — would affect your profit, in plain terms."
      />
      <div className="mb-4 flex gap-2">
        {([
          ["auto", "Run automatically"],
          ["manual", "Try your own"],
          ["history", "History"],
        ] as [Tab, string][]).map(([t, label]) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded border px-3 py-1.5 text-sm ${
              tab === t ? "border-ink bg-ink text-paper" : "border-line hover:bg-wash"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "auto" && <AutoTab />}
      {tab === "manual" && <ManualTab />}
      {tab === "history" && <HistoryTab />}
    </div>
  );
}

function OutcomeRow({ o, baselineProfit }: { o: SimOutcome; baselineProfit: number }) {
  return (
    <div className="flex items-center gap-3 rounded border border-line p-2.5 text-sm">
      <div className="min-w-0 flex-1">
        <div className="font-medium">{o.name}</div>
        <div className="text-xs text-muted">Profit {naira(o.net_profit)}</div>
      </div>
      <div className="shrink-0 text-right">
        <div className={`font-semibold ${VERDICT_STYLE[o.verdict] ?? ""}`}>
          {o.net_profit_delta >= 0 ? "+" : ""}
          {naira(o.net_profit_delta)}
        </div>
        <div className={`text-xs ${VERDICT_STYLE[o.verdict] ?? "text-muted"}`}>
          {o.net_profit_pct >= 0 ? "+" : ""}
          {o.net_profit_pct}% · {o.verdict}
        </div>
      </div>
    </div>
  );
}

function AutoResult({ sim }: { sim: PlainSim }) {
  return (
    <>
      <Card className="mb-3 p-4">
        <div className="text-[11px] uppercase tracking-wide text-muted">Today (baseline)</div>
        <div className="text-lg font-semibold">Profit {naira(sim.baseline.net_profit)}</div>
        <div className="text-xs text-muted">on revenue {naira(sim.baseline.revenue)}</div>
      </Card>
      <div className="mb-2 text-sm font-medium">What each change would do (best first)</div>
      <div className="space-y-1.5">
        {(sim.outcomes ?? []).map((o) => (
          <OutcomeRow key={o.name} o={o} baselineProfit={sim.baseline.net_profit} />
        ))}
      </div>
      <p className="mt-3 text-[11px] text-muted">
        A model projection using your current figures and a standard price-response assumption.
        Not a guarantee.
      </p>
    </>
  );
}

function AutoTab() {
  const [sim, setSim] = useState<PlainSim | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      setSim(await api.runAutoSimulation());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not run the simulation");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      {!sim && (
        <Card className="p-6 text-center">
          <p className="mb-3 text-sm text-muted">
            One click runs every idea — raising or cutting prices, selling more or less,
            supplier cost going up or down — and ranks them by profit.
          </p>
          <button
            onClick={run}
            disabled={loading}
            className="rounded bg-ink px-5 py-2.5 text-sm font-medium text-paper disabled:opacity-40"
          >
            {loading ? "Running…" : "Run simulation"}
          </button>
        </Card>
      )}
      {error && <div className="mb-3 text-sm text-red-700">{error}</div>}
      {sim && (
        <>
          <div className="mb-3 flex items-center gap-2">
            <button
              onClick={run}
              disabled={loading}
              className="rounded bg-ink px-4 py-2 text-sm font-medium text-paper disabled:opacity-40"
            >
              {loading ? "Running…" : "Run again"}
            </button>
            <span className="text-xs text-muted">Best: {sim.best} · Worst: {sim.worst}</span>
          </div>
          <AutoResult sim={sim} />
        </>
      )}
    </div>
  );
}

function ManualTab() {
  const [price, setPrice] = useState(0);
  const [sales, setSales] = useState(0);
  const [cost, setCost] = useState(0);
  const [sim, setSim] = useState<PlainSim | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      setSim(
        await api.runManualSimulation({
          price_change_percent: price,
          demand_change_percent: sales,
          unit_cost_change_percent: cost,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not run the simulation");
    } finally {
      setLoading(false);
    }
  }

  const r = sim?.result;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-4">
        <div className="mb-3 text-sm font-medium">Change these, then run</div>
        <Slider label="Change prices" value={price} onChange={setPrice} />
        <Slider label="Change how much you sell" value={sales} onChange={setSales} />
        <Slider label="Change supplier cost" value={cost} onChange={setCost} />
        <button
          onClick={run}
          disabled={loading}
          className="mt-3 rounded bg-ink px-4 py-2 text-sm font-medium text-paper disabled:opacity-40"
        >
          {loading ? "Running…" : "Run"}
        </button>
        {error && <div className="mt-2 text-sm text-red-700">{error}</div>}
      </Card>

      <Card className="p-4">
        <div className="mb-2 text-sm font-medium">Result</div>
        {!sim ? (
          <div className="text-sm text-muted">Set your changes and press Run.</div>
        ) : (
          <>
            <div className="mb-2 text-xs text-muted">
              Today: profit {naira(sim.baseline.net_profit)} · revenue {naira(sim.baseline.revenue)}
            </div>
            <div className="rounded border border-line p-3">
              <div className="text-[11px] uppercase tracking-wide text-muted">If you do this</div>
              <div className="text-lg font-semibold">Profit {naira(r?.net_profit)}</div>
              <div className={`text-sm ${VERDICT_STYLE[r?.verdict ?? ""] ?? ""}`}>
                {(r?.net_profit_delta ?? 0) >= 0 ? "+" : ""}
                {naira(r?.net_profit_delta)} ({(r?.net_profit_pct ?? 0) >= 0 ? "+" : ""}
                {r?.net_profit_pct}%) · {r?.verdict}
              </div>
              <div className="mt-1 text-xs text-muted">Revenue {naira(r?.revenue)}</div>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}

function Slider({ label, value, onChange }: { label: string; value: number; onChange: (n: number) => void }) {
  return (
    <div className="mb-3">
      <div className="mb-1 flex items-center justify-between text-xs">
        <span>{label}</span>
        <span className={`font-medium ${value === 0 ? "text-muted" : ""}`}>
          {value > 0 ? "+" : ""}
          {value}%
        </span>
      </div>
      <input
        type="range"
        min={-30}
        max={30}
        step={5}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full"
      />
    </div>
  );
}

function HistoryTab() {
  const [runs, setRuns] = useState<Simulation[]>([]);
  const [selected, setSelected] = useState<PlainSim | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    api
      .listSimulations()
      .then((r) => setRuns(r.items.filter((s) => s.scenario_type === "auto_explore" || s.scenario_type === "manual")))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function open(id: number) {
    try {
      setSelected(await api.plainSimulation(id));
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-4">
        <div className="mb-2 text-sm font-medium">Past runs</div>
        {loading && <div className="text-sm text-muted">Loading…</div>}
        {!loading && runs.length === 0 && (
          <div className="text-sm text-muted">No saved runs yet.</div>
        )}
        <div className="space-y-1">
          {runs.map((s) => (
            <button
              key={s.id}
              onClick={() => open(s.id)}
              className="block w-full rounded border border-line px-3 py-2 text-left text-sm hover:bg-wash"
            >
              <div className="flex items-center justify-between">
                <span>{s.scenario_type === "auto_explore" ? "Auto explore" : "Manual"}</span>
                <span className="text-xs text-muted">
                  {s.created_at ? new Date(s.created_at).toLocaleString("en-NG", { dateStyle: "medium", timeStyle: "short" }) : ""}
                </span>
              </div>
            </button>
          ))}
        </div>
      </Card>

      <Card className="p-4">
        <div className="mb-2 text-sm font-medium">Run detail</div>
        {!selected ? (
          <div className="text-sm text-muted">Pick a run to see it.</div>
        ) : selected.kind === "auto_explore" ? (
          <AutoResult sim={selected} />
        ) : (
          <div>
            <div className="mb-2 text-xs text-muted">
              Changes: prices {selected.inputs?.price_change_percent ?? 0}% · sales{" "}
              {selected.inputs?.demand_change_percent ?? 0}% · cost{" "}
              {selected.inputs?.unit_cost_change_percent ?? 0}%
            </div>
            {selected.result && (
              <OutcomeRow o={selected.result} baselineProfit={selected.baseline.net_profit} />
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
