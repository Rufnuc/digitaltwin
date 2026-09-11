"use client";
import { useEffect, useState } from "react";
import {
  api,
  type AgentCompareResult,
  type AgentRoster,
  type AgentSimResult,
} from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card, LineChart, ProvenanceBadge } from "@/components/ui";
import { money, num, pct } from "@/lib/format";

export default function AgentsPage() {
  const [roster, setRoster] = useState<AgentRoster | null>(null);
  const [priceChange, setPriceChange] = useState(5);
  const [horizon, setHorizon] = useState(12);
  const [iterations, setIterations] = useState(400);
  const [result, setResult] = useState<AgentSimResult | null>(null);
  const [compare, setCompare] = useState<AgentCompareResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.agentsRoster().then(setRoster).catch(() => {});
  }, []);

  async function runSim() {
    setBusy(true);
    setError(null);
    try {
      setResult(
        await api.agentSimulate({
          policy: { price_change_percent: priceChange },
          horizon_months: horizon,
          iterations,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function runCompare() {
    setBusy(true);
    setError(null);
    try {
      setCompare(
        await api.agentCompare({
          strategies: [
            { name: "Hold", price_change_percent: 0 },
            { name: "Raise 5%", price_change_percent: 5 },
            { name: "Raise 10%", price_change_percent: 10 },
            { name: "Raise 15%", price_change_percent: 15 },
          ],
          horizon_months: horizon,
          iterations,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Digital Twin (Multi-Agent Simulation)"
        subtitle="Simulated customer, supplier, competitor and market agents — calibrated from real history, driven by explicit assumptions — play the business forward month by month. Outcomes are forecasts with uncertainty, never facts."
      />

      {roster && (
        <Card className="mb-4 p-4">
          <div className="mb-2 text-sm font-medium">The agents</div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {roster.agents.map((a) => (
              <div key={a.agent} className="rounded border border-line p-2 text-xs">
                <div className="font-medium">
                  {a.agent} <span className="text-muted">· {a.count}</span>
                </div>
                <div className="text-muted">{a.behaviour}</div>
                <div className="mt-1 text-[10px] text-muted">
                  calibrated from: {a.calibrated_from}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="p-4">
          <div className="mb-3 text-sm font-medium">Policy under test</div>
          <Field label="Price change (%)">
            <input type="number" value={priceChange} onChange={(e) => setPriceChange(+e.target.value)} className={inp} />
          </Field>
          <Field label="Horizon (months)">
            <input type="number" value={horizon} onChange={(e) => setHorizon(+e.target.value)} className={inp} />
          </Field>
          <Field label="Iterations (Monte Carlo)">
            <input type="number" value={iterations} onChange={(e) => setIterations(+e.target.value)} className={inp} />
          </Field>
          <button onClick={runSim} disabled={busy} className={btn}>
            {busy ? "Simulating…" : "Run simulation"}
          </button>
          <button onClick={runCompare} disabled={busy} className={btnOutline}>
            Compare strategies
          </button>
          {error && <div className="mt-2 text-sm text-red-700">{error}</div>}
        </Card>

        <Card className="p-4 lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-medium">Forecast</div>
            {result && <ProvenanceBadge origin={result.provenance.outcome} />}
          </div>
          {!result ? (
            <div className="text-sm text-muted">Run a simulation to see the forecast.</div>
          ) : (
            <>
              <div className="mb-3 grid grid-cols-2 gap-3 md:grid-cols-4">
                <Stat label="Median cum. net" value={money(result.cumulative_net_profit.p50)} />
                <Stat label="P5 … P95" value={`${money(result.cumulative_net_profit.p5)} … ${money(result.cumulative_net_profit.p95)}`} small />
                <Stat label="P(loss)" value={pct(result.probability_of_cumulative_loss)} danger={result.probability_of_cumulative_loss > 0.4} />
                <Stat label="Customers end" value={`${num(result.expected_active_customers_end)} / ${num(result.customers_start)}`} />
              </div>
              <div className="mb-1 text-xs text-muted">Median monthly net profit</div>
              <LineChart
                data={result.monthly_net_profit_path.map((p) => ({
                  period: `M${p.month}`,
                  revenue: p.p50,
                }))}
              />
              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Labelled title="Calibration" tag={result.provenance.calibration}>
                  {Object.entries(result.calibration).map(([k, v]) => (
                    <Row key={k} k={k} v={v} />
                  ))}
                </Labelled>
                <Labelled title="Assumptions" tag={result.provenance.behaviour}>
                  {Object.entries(result.assumptions).map(([k, v]) => (
                    <Row key={k} k={k} v={v} />
                  ))}
                </Labelled>
              </div>
            </>
          )}
        </Card>
      </div>

      {compare && (
        <Card className="mt-4 p-4">
          <div className="mb-2 text-sm">
            Best expected strategy:{" "}
            <span className="font-medium">{compare.best_by_expected_profit}</span>
          </div>
          <div className="overflow-x-auto rounded border border-line">
            <table className="min-w-full text-sm">
              <thead className="bg-wash text-left text-xs uppercase tracking-wide text-muted">
                <tr>
                  {["Strategy", "Expected cum. net", "P5", "P95", "P(loss)", "Cust. end"].map((h) => (
                    <th key={h} className="px-3 py-2">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {compare.strategies.map((s) => (
                  <tr
                    key={s.name}
                    className={`border-t border-line tabular-nums ${
                      s.name === compare.best_by_expected_profit ? "bg-green-50" : ""
                    }`}
                  >
                    <td className="px-3 py-2 font-medium">{s.name}</td>
                    <td className="px-3 py-2">{money(s.expected_cumulative_net_profit)}</td>
                    <td className="px-3 py-2">{money(s.p5)}</td>
                    <td className="px-3 py-2">{money(s.p95)}</td>
                    <td className="px-3 py-2">{pct(s.probability_of_loss)}</td>
                    <td className="px-3 py-2">{num(s.expected_active_customers_end)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

const inp = "w-full rounded border border-line px-2 py-1.5 text-sm outline-none focus:border-ink";
const btn = "mt-2 w-full rounded bg-ink px-3 py-2 text-sm font-medium text-paper disabled:opacity-50";
const btnOutline = "mt-2 w-full rounded border border-line px-3 py-2 text-sm hover:bg-wash disabled:opacity-50";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-3">
      <label className="mb-1 block text-xs text-muted">{label}</label>
      {children}
    </div>
  );
}
function Stat({ label, value, danger, small }: { label: string; value: string; danger?: boolean; small?: boolean }) {
  return (
    <div className="rounded border border-line p-2">
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`font-semibold tabular-nums ${small ? "text-xs" : "text-lg"} ${danger ? "text-red-700" : ""}`}>
        {value}
      </div>
    </div>
  );
}
function Labelled({ title, tag, children }: { title: string; tag: string; children: React.ReactNode }) {
  return (
    <div className="rounded border border-line p-2">
      <div className="mb-1 flex items-center gap-2">
        <span className="text-xs font-medium">{title}</span>
        <ProvenanceBadge origin={tag} />
      </div>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}
function Row({ k, v }: { k: string; v: number }) {
  return (
    <div className="flex justify-between text-[11px]">
      <span className="font-mono text-muted">{k}</span>
      <span className="tabular-nums">{v}</span>
    </div>
  );
}
