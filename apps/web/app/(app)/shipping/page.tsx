"use client";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { api, type LaneConditions, type ShippingStatus, type Vessel } from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card, Kpi, ProvenanceBadge } from "@/components/ui";
import { num } from "@/lib/format";

export default function ShippingPage() {
  const [status, setStatus] = useState<ShippingStatus | null>(null);
  const [conditions, setConditions] = useState<LaneConditions | null>(null);
  const [vessels, setVessels] = useState<Vessel[]>([]);
  const [region, setRegion] = useState("");
  const [watchOnly, setWatchOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const st = await api.shippingStatus();
      setStatus(st);
      api.shippingConditions().then(setConditions).catch(() => {
        /* conditions are supplementary — don't fail the whole page */
      });
      const params =
        `?limit=300` + (region ? `&region=${encodeURIComponent(region)}` : "") +
        (watchOnly ? `&nigeria_watch=true` : "");
      const v = await api.shippingVessels(params);
      setVessels(v.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }, [region, watchOnly]);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000); // live refresh
    return () => clearInterval(t);
  }, [load]);

  return (
    <div>
      <PageHeader
        title="Shipping Monitor"
        subtitle="Live vessel positions (real AIS data) on the China → Nigeria and Turkey → Nigeria trade lanes. Positions are real observations; 'bound for Nigeria' is each ship's self-reported destination, and 'arrived' means a tracked China/Turkey vessel has since been seen in Nigerian waters."
      />

      {error && <div className="mb-3 text-sm text-red-700">Error: {error}</div>}

      {status && !status.enabled && (
        <Card className="p-6 text-sm text-muted">
          Shipping monitor is disabled — set <code className="font-mono">AISSTREAM_API_KEY</code> in
          the API environment to stream live AIS data.
        </Card>
      )}

      {status && status.enabled && (
        <>
          <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4">
            <Kpi
              label="Feed"
              value={status.connected ? "Connected" : "Reconnecting…"}
              sub={status.last_message_at ? new Date(status.last_message_at).toLocaleTimeString() : ""}
            />
            <Kpi label="Vessels tracked" value={num(status.vessels_tracked)} />
            <Kpi label="Declared for Nigeria" value={num(status.nigeria_bound)} sub="self-reported" />
            <Kpi label="Messages" value={num(status.messages_received)} />
          </div>

          {/* "Will China / Turkey vessels touch Nigeria?" — declared intent + observed arrival. */}
          <Card className="mb-4 p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-medium">Nigeria watch — by source lane</span>
              <span className="text-[11px] text-muted">
                declared = ship says so · arrived = we saw it in NG waters
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <LaneStat
                lane="China → Nigeria"
                declared={status.nigeria_watch.china_declared}
                arrived={status.nigeria_watch.china_arrived}
                tracked={status.by_origin["China / Asia"] ?? 0}
              />
              <LaneStat
                lane="Turkey → Nigeria"
                declared={status.nigeria_watch.turkey_declared}
                arrived={status.nigeria_watch.turkey_arrived}
                tracked={status.by_origin["Turkey / Mediterranean"] ?? 0}
              />
            </div>
          </Card>

          {conditions && <LaneConditionsCard c={conditions} />}

          <div className="mb-3 flex flex-wrap items-center gap-3">
            <select
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="rounded border border-line px-2 py-1.5 text-sm"
            >
              <option value="">All regions</option>
              {Object.keys(status.by_region).map((r) => (
                <option key={r} value={r}>
                  {r} ({status.by_region[r]})
                </option>
              ))}
            </select>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={watchOnly}
                onChange={(e) => setWatchOnly(e.target.checked)}
              />
              Nigeria watch only (declared or arrived)
            </label>
            <span className="ml-auto text-[11px] text-muted">Auto-refreshing every 15s</span>
          </div>

          <Card className="p-0">
            <div className="flex items-center justify-between border-b border-line px-4 py-2">
              <span className="text-sm font-medium">{vessels.length} vessels</span>
              <ProvenanceBadge origin="REAL" />
            </div>
            {/* Phones: one card per vessel so every field stays visible. */}
            <div className="space-y-2 p-3 sm:hidden">
              {vessels.length === 0 ? (
                <div className="px-1 py-4 text-sm text-muted">
                  No vessels in view yet — data accumulates as ships report.
                </div>
              ) : (
                vessels.map((v) => (
                  <div
                    key={v.mmsi}
                    className={`rounded-lg border border-line p-3 ${
                      v.bound_for_nigeria || v.arrived_nigeria ? "bg-green-500/15" : "bg-paper"
                    }`}
                  >
                    <div className="mb-1 flex flex-wrap items-center gap-2 text-sm font-medium">
                      {v.name}
                      <VesselBadges v={v} />
                    </div>
                    <VRow label="MMSI" value={<span className="text-muted">{v.mmsi}</span>} />
                    <VRow label="Origin" value={shortRegion(v.origin_region)} />
                    <VRow
                      label="Position"
                      value={
                        v.lat != null && v.lon != null ? (
                          <a
                            href={`https://www.google.com/maps?q=${v.lat},${v.lon}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="underline decoration-dotted"
                          >
                            {v.lat.toFixed(2)}, {v.lon.toFixed(2)}
                          </a>
                        ) : (
                          "—"
                        )
                      }
                    />
                    <VRow label="Speed" value={v.sog != null ? `${v.sog} kn` : "—"} />
                    <VRow label="Region" value={v.region} />
                    <VRow label="Destination" value={v.destination ?? "—"} />
                    <VRow label="ETA" value={v.eta ?? "—"} />
                    <VRow
                      label="Seen"
                      value={v.last_seen ? new Date(v.last_seen).toLocaleTimeString() : "—"}
                    />
                  </div>
                ))
              )}
            </div>

            {/* Tablet and up: the full vessel table. */}
            <div className="hidden overflow-x-auto sm:block">
              <table className="min-w-full text-sm">
                <thead className="bg-wash text-left text-xs uppercase tracking-wide text-muted">
                  <tr>
                    {["Vessel", "Origin", "Position", "Speed", "Region", "Destination", "ETA", "Seen"].map(
                      (h) => (
                        <th key={h} className="px-3 py-2 font-medium">
                          {h}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {vessels.length === 0 ? (
                    <tr>
                      <td className="px-3 py-6 text-muted" colSpan={8}>
                        No vessels in view yet — data accumulates as ships report.
                      </td>
                    </tr>
                  ) : (
                    vessels.map((v) => (
                      <tr
                        key={v.mmsi}
                        className={`border-t border-line ${
                          v.bound_for_nigeria || v.arrived_nigeria ? "bg-green-500/15" : ""
                        }`}
                      >
                        <td className="px-3 py-2 font-medium">
                          <div className="flex flex-wrap items-center gap-2">
                            {v.name}
                            <VesselBadges v={v} />
                          </div>
                        </td>
                        <td className="px-3 py-2">{shortRegion(v.origin_region)}</td>
                        <td className="px-3 py-2 tabular-nums">
                          {v.lat != null && v.lon != null ? (
                            <a
                              href={`https://www.google.com/maps?q=${v.lat},${v.lon}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="underline decoration-dotted"
                            >
                              {v.lat.toFixed(2)}, {v.lon.toFixed(2)}
                            </a>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          {v.sog != null ? `${v.sog} kn` : "—"}
                        </td>
                        <td className="px-3 py-2">{v.region}</td>
                        <td className="px-3 py-2">{v.destination ?? "—"}</td>
                        <td className="px-3 py-2 tabular-nums text-[11px]">{v.eta ?? "—"}</td>
                        <td className="px-3 py-2 text-[11px] text-muted">
                          {v.last_seen ? new Date(v.last_seen).toLocaleTimeString() : "—"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

function VRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 py-0.5 text-sm">
      <span className="shrink-0 text-xs uppercase tracking-wide text-muted">{label}</span>
      <span className="min-w-0 break-words text-right tabular-nums">{value}</span>
    </div>
  );
}

// Short label for an origin/region string ("China / Asia" -> "China").
function shortRegion(region: string | null): string {
  if (!region) return "—";
  return region.split(" / ")[0];
}

// Declared-intent and observed-arrival badges for a vessel.
function VesselBadges({ v }: { v: Vessel }) {
  return (
    <>
      {v.arrived_nigeria && (
        <span className="rounded bg-green-700 px-1 py-0.5 text-[9px] text-white">✓ ARRIVED NG</span>
      )}
      {v.bound_for_nigeria && !v.arrived_nigeria && (
        <span className="rounded bg-green-600 px-1 py-0.5 text-[9px] text-white">→ NIGERIA</span>
      )}
    </>
  );
}

// Natural + human factors on the source lanes: live AIS signals + real news.
function LaneConditionsCard({ c }: { c: LaneConditions }) {
  const factorList = (items: LaneConditions["disruptions"]["natural"], kind: string) => (
    <div>
      <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">
        {kind} factors ({items.length})
      </div>
      {items.length === 0 ? (
        <div className="text-xs text-muted">No {kind.toLowerCase()} disruptions in the feed.</div>
      ) : (
        <ul className="space-y-1.5">
          {items.slice(0, 6).map((d, i) => (
            <li key={i} className="text-sm">
              <a
                href={d.source_url ?? "#"}
                target="_blank"
                rel="noopener noreferrer"
                className="underline decoration-dotted"
              >
                {d.title}
              </a>
              <span className="ml-1 text-[11px] text-muted">
                · {d.source} · {d.factors.join(", ")}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  return (
    <Card className="mb-4 p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-medium">Lane conditions — natural &amp; human factors</span>
        <ProvenanceBadge origin="REAL" />
      </div>

      {/* Observed AIS signals per lane. */}
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {c.lanes.map((l) => {
          // Descriptive only — a very high stationary share is worth noting, but ships
          // routinely anchor/berth near ports, so we never assert "congestion".
          const mostlyStill = l.stationary_share != null && l.stationary_share >= 0.85 && l.with_speed >= 10;
          return (
            <div key={l.lane} className="rounded-lg border border-line p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{l.lane.split(" / ")[0]}</span>
                {mostlyStill && (
                  <span className="rounded bg-yellow-500/20 px-1.5 py-0.5 text-[10px] text-yellow-700 dark:text-yellow-300">
                    mostly stationary
                  </span>
                )}
              </div>
              <div className="mt-1 grid grid-cols-3 gap-2 text-center">
                <Metric label="tracked" value={num(l.vessels_tracked)} />
                <Metric label="under way" value={num(l.moving)} />
                <Metric
                  label="median kn"
                  value={l.median_speed_kn != null ? String(l.median_speed_kn) : "—"}
                />
              </div>
              <div className="mt-1 text-[11px] text-muted">
                {l.stationary} sitting still
                {l.stationary_share != null ? ` (${Math.round(l.stationary_share * 100)}%)` : ""} —
                anchored, berthed or waiting
              </div>
            </div>
          );
        })}
      </div>

      {/* Real disruption news split into natural / human factors. */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {factorList(c.disruptions.natural, "Natural")}
        {factorList(c.disruptions.human, "Human")}
      </div>
      <div className="mt-3 border-t border-line pt-2 text-[11px] text-muted">{c.note}</div>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded bg-wash py-1">
      <div className="text-sm font-semibold tabular-nums">{value}</div>
      <div className="text-[10px] uppercase text-muted">{label}</div>
    </div>
  );
}

// One source lane's Nigeria-watch counts.
function LaneStat({
  lane,
  declared,
  arrived,
  tracked,
}: {
  lane: string;
  declared: number;
  arrived: number;
  tracked: number;
}) {
  return (
    <div className="rounded-lg border border-line p-3">
      <div className="text-sm font-medium">{lane}</div>
      <div className="mt-1 flex items-baseline gap-4">
        <span>
          <span className="text-2xl font-semibold tabular-nums">{declared}</span>{" "}
          <span className="text-xs text-muted">declared</span>
        </span>
        <span>
          <span className="text-2xl font-semibold tabular-nums text-green-700 dark:text-green-300">
            {arrived}
          </span>{" "}
          <span className="text-xs text-muted">arrived</span>
        </span>
      </div>
      <div className="mt-1 text-[11px] text-muted">{tracked} vessels tracked from this lane</div>
    </div>
  );
}
