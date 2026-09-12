"use client";
import { useState } from "react";
import { api, type ImpactAssessment } from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card, ProvenanceBadge } from "@/components/ui";
import { money } from "@/lib/format";

export default function ImpactPage() {
  const [assessments, setAssessments] = useState<ImpactAssessment[] | null>(null);
  const [note, setNote] = useState("");
  const [alertsMsg, setAlertsMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(createAlerts: boolean) {
    setBusy(true);
    setError(null);
    setAlertsMsg(null);
    try {
      const r = await api.impactScan(createAlerts);
      setAssessments(r.assessments);
      setNote(r.note);
      if (!r.has_market_data) {
        setError("No market data yet — refresh Market Intelligence first.");
      } else if (createAlerts) {
        setAlertsMsg(`${r.alerts_created} alert(s) raised on the dashboard.`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="News → Business Impact"
        subtitle="Turns real market signals into a quantified, labelled assessment: FACT → ASSUMPTION → POSSIBLE IMPACT → SIMULATION → ACTION. Possibility is never presented as certainty."
      />

      <div className="mb-4 flex items-center gap-3">
        <button
          onClick={() => run(true)}
          disabled={busy}
          className="rounded bg-ink px-4 py-2 text-sm font-medium text-paper disabled:opacity-50"
        >
          {busy ? "Assessing…" : "Run impact scan"}
        </button>
        <button
          onClick={() => run(false)}
          disabled={busy}
          className="rounded border border-line px-3 py-2 text-sm hover:bg-wash disabled:opacity-50"
        >
          Preview (no alerts)
        </button>
        {alertsMsg && <span className="text-xs text-green-700 dark:text-green-300">{alertsMsg}</span>}
        {error && <span className="text-sm text-red-700">{error}</span>}
      </div>

      {assessments && assessments.length > 0 && (
        <>
          <div className="space-y-4">
            {assessments.map((a) => (
              <AssessmentCard key={a.driver} a={a} />
            ))}
          </div>
          <p className="mt-3 text-xs text-muted">{note}</p>
        </>
      )}
    </div>
  );
}

function Section({ label, tag, children }: { label: string; tag?: string; children: React.ReactNode }) {
  return (
    <div className="mb-2">
      <div className="mb-0.5 flex items-center gap-2">
        <span className="font-mono text-[10px] uppercase tracking-wide text-muted">{label}</span>
        {tag && <ProvenanceBadge origin={tag} />}
      </div>
      <div className="text-sm">{children}</div>
    </div>
  );
}

function AssessmentCard({ a }: { a: ImpactAssessment }) {
  const net = a.simulation.results.find((r) => r.metric === "net_profit");
  const gp = a.simulation.results.find((r) => r.metric === "gross_profit");
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-base font-semibold">{a.title}</div>
        <span
          className={`rounded border px-2 py-0.5 text-[10px] font-mono ${
            a.materiality.material
              ? "border-red-500/40 bg-red-500/15 text-red-700 dark:text-red-300"
              : "border-line text-muted"
          }`}
        >
          {a.materiality.material ? "MATERIAL" : "minor"} · net{" "}
          {a.materiality.net_profit_change_percent > 0 ? "+" : ""}
          {a.materiality.net_profit_change_percent}%
        </span>
      </div>

      <Section label="Fact (observed)" tag={a.provenance.fact}>
        <a
          href={a.fact.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="hover:underline"
        >
          {a.fact.label}: <span className="font-medium">{a.fact.value} {a.fact.unit}</span>
        </a>{" "}
        <span className="text-muted">
          ({a.fact.period} · {a.fact.source})
        </span>
      </Section>

      <Section label="Assumption (mapping)" tag={a.provenance.mapping}>
        {String(a.assumptions.note ?? "")} → {a.lever.field}{" "}
        <span className="font-medium">{a.lever.value}%</span>
      </Section>

      <Section label="Possible impact">
        <ul className="ml-4 list-disc text-muted">
          {Object.entries(a.possible_impact).map(([k, v]) => (
            <li key={k}>
              <span className="font-medium capitalize">{k}:</span>{" "}
              {Array.isArray(v)
                ? `${v.length} affected`
                : String(v)}
            </li>
          ))}
        </ul>
      </Section>

      <Section label="Simulation (model output)" tag={a.provenance.numbers}>
        <div className="tabular-nums">
          {gp && (
            <span>
              Gross profit {money(gp.baseline)} → {money(gp.scenario)} ({gp.change_percent}%);{" "}
            </span>
          )}
          {net && (
            <span className={net.change_percent < 0 ? "text-red-700" : "text-green-700"}>
              net profit {money(net.baseline)} → {money(net.scenario)} ({net.change_percent}%)
            </span>
          )}
        </div>
      </Section>

      <div className="mt-2 rounded border border-line bg-wash p-2 text-xs">
        <div className="mb-1">
          <span className="font-medium">Risk:</span> {a.risk}
        </div>
        <div>
          <span className="font-medium">Recommended action:</span> {a.recommended_action}
        </div>
      </div>
    </Card>
  );
}
