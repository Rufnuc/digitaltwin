"use client";
import { useEffect, useState } from "react";
import { api, type Comparison, type Simulation, type Tornado } from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card, ProvenanceBadge } from "@/components/ui";
import { money, pct } from "@/lib/format";

type Tab = "scenario" | "montecarlo" | "sensitivity" | "compare";
const TABS: { id: Tab; label: string }[] = [
  { id: "scenario", label: "Scenario" },
  { id: "montecarlo", label: "Monte Carlo" },
  { id: "sensitivity", label: "Sensitivity" },
  { id: "compare", label: "Compare" },
];

const SCENARIO_TYPES = [
  { id: "price_change", label: "Price change", param: "price_change_percent" },
  { id: "demand_change", label: "Demand change", param: "demand_change_percent" },
  { id: "supplier_cost_change", label: "Supplier cost change", param: "unit_cost_change_percent" },
];

function fmt(metric: string, v: number | undefined) {
  if (v == null) return "—";
  if (metric === "gross_margin") return pct(v);
  if (metric === "units") return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return money(v);
}

export default function SimulationsPage() {
  const [tab, setTab] = useState<Tab>("scenario");
  return (
    <div>
      <PageHeader
        title="Simulations"
        subtitle="Structured scenario → deterministic engine → explained results. Numbers come from the engine, never from an LLM."
      />
      <div className="mb-4 flex gap-1 border-b border-line">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              tab === t.id ? "border-ink font-medium" : "border-transparent text-muted"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "scenario" && <ScenarioTab />}
      {tab === "montecarlo" && <MonteCarloTab />}
      {tab === "sensitivity" && <SensitivityTab />}
      {tab === "compare" && <CompareTab />}
    </div>
  );
}

/* ---------------- Deterministic scenario ---------------- */
function ScenarioTab() {
  const [type, setType] = useState(SCENARIO_TYPES[0]);
  const [name, setName] = useState("Raise prices 10%");
  const [change, setChange] = useState(10);
  const [elasticity, setElasticity] = useState(-0.8);
  const [horizon, setHorizon] = useState(12);
  const [current, setCurrent] = useState<Simulation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const created = await api.createSimulation({
        name,
        scenario_type: type.id,
        parameters: { [type.param]: change },
        assumptions: { price_elasticity: elasticity },
        horizon_months: horizon,
      });
      setCurrent(await api.runSimulation(created.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card className="p-4">
        <div className="mb-3 text-sm font-medium">Scenario builder</div>
        <Field label="Name">
          <input value={name} onChange={(e) => setName(e.target.value)} className={inp} />
        </Field>
        <Field label="Scenario type">
          <select
            value={type.id}
            onChange={(e) => setType(SCENARIO_TYPES.find((s) => s.id === e.target.value)!)}
            className={inp}
          >
            {SCENARIO_TYPES.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Change (%)">
          <input
            type="number"
            value={change}
            onChange={(e) => setChange(Number(e.target.value))}
            className={inp}
          />
        </Field>
        <Field label="Price elasticity (ASSUMPTION)">
          <input
            type="number"
            step="0.1"
            value={elasticity}
            onChange={(e) => setElasticity(Number(e.target.value))}
            className={inp}
          />
        </Field>
        <Field label="Horizon (months)">
          <input
            type="number"
            value={horizon}
            onChange={(e) => setHorizon(Number(e.target.value))}
            className={inp}
          />
        </Field>
        <button onClick={run} disabled={busy} className={btn}>
          {busy ? "Running…" : "Run simulation"}
        </button>
        {error && <div className="mt-2 text-sm text-red-700">{error}</div>}
      </Card>

      <Card className="p-4 lg:col-span-2">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-sm font-medium">Results</div>
          {current && (
            <span className="font-mono text-[11px] text-muted">
              {current.model_name} v{current.model_version} · {current.status}
            </span>
          )}
        </div>
        {!current ? (
          <Muted>Run a scenario to see results.</Muted>
        ) : (
          <>
            <ResultsTable results={current.results} />
            <div className="mt-3 flex items-center gap-2">
              <ProvenanceBadge origin="MODEL_OUTPUT" />
              <span className="text-[11px] text-muted">input: {current.input_data_version}</span>
            </div>
            <AssumptionsBlock a={current.assumptions} />
          </>
        )}
      </Card>
    </div>
  );
}

function ResultsTable({ results }: { results: Simulation["results"] }) {
  return (
    <div className="overflow-x-auto rounded border border-line">
      <table className="min-w-full text-sm">
        <thead className="bg-wash text-left text-xs uppercase tracking-wide text-muted">
          <tr>
            {["Metric", "Baseline", "Scenario", "Change"].map((h) => (
              <th key={h} className="px-3 py-2">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {results.map((r) => (
            <tr key={r.metric} className="border-t border-line">
              <td className="px-3 py-2 font-medium">{r.metric}</td>
              <td className="px-3 py-2 tabular-nums">{fmt(r.metric, r.baseline?.value)}</td>
              <td className="px-3 py-2 tabular-nums">{fmt(r.metric, r.scenario?.value)}</td>
              <td
                className={`px-3 py-2 tabular-nums ${
                  (r.delta?.percent ?? 0) >= 0 ? "text-green-700" : "text-red-700"
                }`}
              >
                {r.delta ? `${r.delta.percent > 0 ? "+" : ""}${r.delta.percent}%` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------------- Monte Carlo ---------------- */
interface MCSummary {
  iterations: number;
  probability_of_loss: number;
  probability_of_target: number | null;
  sensitivity: { variable: string; correlation: number }[];
}
function MonteCarloTab() {
  const [priceMean, setPriceMean] = useState(5);
  const [priceStd, setPriceStd] = useState(4);
  const [costMean, setCostMean] = useState(4);
  const [costStd, setCostStd] = useState(3);
  const [iterations, setIterations] = useState(10000);
  const [result, setResult] = useState<Simulation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.monteCarlo({
        name: "Monte Carlo run",
        parameters: {
          distributions: {
            price_pct: { type: "normal", mean: priceMean, std: priceStd },
            unit_cost_pct: { type: "normal", mean: costMean, std: costStd },
          },
        },
        iterations,
        target_metric: "net_profit",
        target_threshold: 0,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  const mc = result?.assumptions?.monte_carlo as MCSummary | undefined;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card className="p-4">
        <div className="mb-3 text-sm font-medium">Uncertainty inputs</div>
        <p className="mb-3 text-[11px] text-muted">
          Each variable is sampled from a normal distribution (% change). Outputs are a
          distribution, never a single certain number.
        </p>
        <TwoCol label="Price % (mean / std)">
          <input type="number" value={priceMean} onChange={(e) => setPriceMean(+e.target.value)} className={inp} />
          <input type="number" value={priceStd} onChange={(e) => setPriceStd(+e.target.value)} className={inp} />
        </TwoCol>
        <TwoCol label="Unit cost % (mean / std)">
          <input type="number" value={costMean} onChange={(e) => setCostMean(+e.target.value)} className={inp} />
          <input type="number" value={costStd} onChange={(e) => setCostStd(+e.target.value)} className={inp} />
        </TwoCol>
        <Field label="Iterations">
          <input type="number" value={iterations} onChange={(e) => setIterations(+e.target.value)} className={inp} />
        </Field>
        <button onClick={run} disabled={busy} className={btn}>
          {busy ? "Simulating…" : "Run Monte Carlo"}
        </button>
        {error && <div className="mt-2 text-sm text-red-700">{error}</div>}
      </Card>

      <Card className="p-4 lg:col-span-2">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-sm font-medium">Outcome distribution</div>
          {result && <ProvenanceBadge origin="FORECAST" />}
        </div>
        {!result || !mc ? (
          <Muted>Run a Monte Carlo simulation to see the distribution.</Muted>
        ) : (
          <>
            <div className="mb-3 grid grid-cols-3 gap-3">
              <Stat label="Iterations" value={mc.iterations.toLocaleString()} />
              <Stat label="P(loss)" value={pct(mc.probability_of_loss)} danger={mc.probability_of_loss > 0.1} />
              <Stat label="P(net ≥ 0)" value={mc.probability_of_target == null ? "—" : pct(mc.probability_of_target)} />
            </div>
            <div className="overflow-x-auto rounded border border-line">
              <table className="min-w-full text-sm">
                <thead className="bg-wash text-left text-xs uppercase tracking-wide text-muted">
                  <tr>
                    {["Metric", "P5", "P25", "Median", "P75", "P95", "Mean"].map((h) => (
                      <th key={h} className="px-2 py-2">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.results.map((r) => {
                    const s = r.scenario as Record<string, number>;
                    return (
                      <tr key={r.metric} className="border-t border-line tabular-nums">
                        <td className="px-2 py-1.5 font-medium">{r.metric}</td>
                        <td className="px-2 py-1.5">{fmt(r.metric, s.p5)}</td>
                        <td className="px-2 py-1.5">{fmt(r.metric, s.p25)}</td>
                        <td className="px-2 py-1.5">{fmt(r.metric, s.p50)}</td>
                        <td className="px-2 py-1.5">{fmt(r.metric, s.p75)}</td>
                        <td className="px-2 py-1.5">{fmt(r.metric, s.p95)}</td>
                        <td className="px-2 py-1.5">{fmt(r.metric, s.mean)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="mt-4">
              <div className="mb-2 text-xs font-medium text-muted">
                Sensitivity — correlation of each input with net profit
              </div>
              <Bars
                rows={mc.sensitivity.map((s) => ({
                  label: s.variable,
                  value: Math.abs(s.correlation),
                  raw: s.correlation,
                }))}
              />
            </div>
          </>
        )}
      </Card>
    </div>
  );
}

/* ---------------- Sensitivity (tornado) ---------------- */
function SensitivityTab() {
  const [elasticity, setElasticity] = useState(-0.8);
  const [result, setResult] = useState<Tornado | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setResult(
        await api.sensitivity({
          parameters: {},
          assumptions: { price_elasticity: elasticity },
          target_metric: "net_profit",
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  const max = result ? Math.max(...result.ranking.map((r) => r.swing), 1) : 1;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card className="p-4">
        <div className="mb-3 text-sm font-medium">Tornado analysis</div>
        <p className="mb-3 text-[11px] text-muted">
          Each lever is varied between default low/high bounds, one at a time. Ranked by the
          swing it causes in net profit — “what matters most?”
        </p>
        <Field label="Price elasticity (ASSUMPTION)">
          <input type="number" step="0.1" value={elasticity} onChange={(e) => setElasticity(+e.target.value)} className={inp} />
        </Field>
        <button onClick={run} disabled={busy} className={btn}>
          {busy ? "Analysing…" : "Run sensitivity"}
        </button>
        {error && <div className="mt-2 text-sm text-red-700">{error}</div>}
      </Card>

      <Card className="p-4 lg:col-span-2">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-sm font-medium">Impact on net profit</div>
          {result && <ProvenanceBadge origin="MODEL_OUTPUT" />}
        </div>
        {!result ? (
          <Muted>Run the analysis to see the tornado ranking.</Muted>
        ) : (
          <div>
            <div className="mb-3 text-xs text-muted">Base net profit: {money(result.base_value)}</div>
            <div className="space-y-2">
              {result.ranking.map((r) => (
                <div key={r.variable}>
                  <div className="mb-0.5 flex justify-between text-xs">
                    <span className="font-mono">{r.variable}</span>
                    <span className="text-muted">
                      {money(r.low_value)} … {money(r.high_value)} · swing {money(r.swing)}
                    </span>
                  </div>
                  <div className="h-3 w-full rounded bg-wash">
                    <div
                      className="h-3 rounded bg-ink"
                      style={{ width: `${(r.swing / max) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

/* ---------------- Compare ---------------- */
function CompareTab() {
  const [rows, setRows] = useState([
    { name: "Raise 10%", pct: 10 },
    { name: "Raise 5%", pct: 5 },
    { name: "Hold", pct: 0 },
  ]);
  const [elasticity, setElasticity] = useState(-0.8);
  const [result, setResult] = useState<Comparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const scenarios = rows.map((r) => ({
        name: r.name,
        parameters: r.pct === 0 ? {} : { price_change_percent: r.pct },
        assumptions: { price_elasticity: elasticity },
      }));
      setResult(await api.compare(scenarios));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <Card className="mb-4 p-4">
        <div className="mb-3 text-sm font-medium">Strategies (price change %)</div>
        <div className="flex flex-wrap items-end gap-3">
          {rows.map((r, i) => (
            <div key={i} className="flex items-end gap-1">
              <div>
                <label className="mb-1 block text-xs text-muted">Name</label>
                <input
                  value={r.name}
                  onChange={(e) =>
                    setRows((rs) => rs.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))
                  }
                  className="w-28 rounded border border-line px-2 py-1.5 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted">%</label>
                <input
                  type="number"
                  value={r.pct}
                  onChange={(e) =>
                    setRows((rs) => rs.map((x, j) => (j === i ? { ...x, pct: +e.target.value } : x)))
                  }
                  className="w-16 rounded border border-line px-2 py-1.5 text-sm"
                />
              </div>
            </div>
          ))}
          <div>
            <label className="mb-1 block text-xs text-muted">Elasticity</label>
            <input
              type="number"
              step="0.1"
              value={elasticity}
              onChange={(e) => setElasticity(+e.target.value)}
              className="w-20 rounded border border-line px-2 py-1.5 text-sm"
            />
          </div>
          <button onClick={run} disabled={busy} className={btn + " w-auto px-4"}>
            {busy ? "Comparing…" : "Compare"}
          </button>
        </div>
        {error && <div className="mt-2 text-sm text-red-700">{error}</div>}
      </Card>

      {result && (
        <Card className="p-4">
          <div className="mb-2 text-sm">
            Best by net profit:{" "}
            <span className="font-medium">{result.best_by_net_profit}</span>
          </div>
          <div className="overflow-x-auto rounded border border-line">
            <table className="min-w-full text-sm">
              <thead className="bg-wash text-left text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-3 py-2">Strategy</th>
                  {result.metrics.map((m) => (
                    <th key={m} className="px-3 py-2">
                      {m}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr className="border-t border-line bg-wash/50 tabular-nums">
                  <td className="px-3 py-2 font-medium">Baseline</td>
                  {result.metrics.map((m) => (
                    <td key={m} className="px-3 py-2">
                      {fmt(m, result.baseline[m])}
                    </td>
                  ))}
                </tr>
                {result.scenarios.map((s) => (
                  <tr
                    key={s.name}
                    className={`border-t border-line tabular-nums ${
                      s.name === result.best_by_net_profit ? "bg-green-500/15" : ""
                    }`}
                  >
                    <td className="px-3 py-2 font-medium">{s.name}</td>
                    {result.metrics.map((m) => (
                      <td key={m} className="px-3 py-2">
                        {fmt(m, s.values[m])}
                      </td>
                    ))}
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

/* ---------------- shared bits ---------------- */
const inp = "w-full rounded border border-line px-2 py-1.5 text-sm outline-none focus:border-ink";
const btn = "mt-2 w-full rounded bg-ink px-3 py-2 text-sm font-medium text-paper disabled:opacity-50";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-3">
      <label className="mb-1 block text-xs text-muted">{label}</label>
      {children}
    </div>
  );
}
function TwoCol({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-3">
      <label className="mb-1 block text-xs text-muted">{label}</label>
      <div className="grid grid-cols-2 gap-2">{children}</div>
    </div>
  );
}
function Stat({ label, value, danger }: { label: string; value: string; danger?: boolean }) {
  return (
    <div className="rounded border border-line p-2">
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`text-lg font-semibold tabular-nums ${danger ? "text-red-700" : ""}`}>
        {value}
      </div>
    </div>
  );
}
function Bars({ rows }: { rows: { label: string; value: number; raw: number }[] }) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <div className="space-y-1.5">
      {rows.map((r) => (
        <div key={r.label}>
          <div className="mb-0.5 flex justify-between text-xs">
            <span className="font-mono">{r.label}</span>
            <span className="text-muted">r = {r.raw}</span>
          </div>
          <div className="h-2.5 w-full rounded bg-wash">
            <div
              className={`h-2.5 rounded ${r.raw >= 0 ? "bg-ink" : "bg-red-600"}`}
              style={{ width: `${(r.value / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
function AssumptionsBlock({ a }: { a: Record<string, unknown> }) {
  return (
    <div className="mt-3">
      <div className="text-xs font-medium text-muted">Assumptions</div>
      <pre className="mt-1 overflow-x-auto rounded border border-line bg-wash p-2 text-[11px]">
        {JSON.stringify(a, null, 2)}
      </pre>
    </div>
  );
}
const Muted = ({ children }: { children: React.ReactNode }) => (
  <div className="text-sm text-muted">{children}</div>
);
