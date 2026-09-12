"use client";
import { useCallback, useEffect, useState } from "react";
import { api, type ShippingStatus, type Vessel } from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card, Kpi, ProvenanceBadge } from "@/components/ui";
import { num } from "@/lib/format";

export default function ShippingPage() {
  const [status, setStatus] = useState<ShippingStatus | null>(null);
  const [vessels, setVessels] = useState<Vessel[]>([]);
  const [region, setRegion] = useState("");
  const [ngOnly, setNgOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const st = await api.shippingStatus();
      setStatus(st);
      const params =
        `?limit=300` + (region ? `&region=${encodeURIComponent(region)}` : "") +
        (ngOnly ? `&nigeria_bound=true` : "");
      const v = await api.shippingVessels(params);
      setVessels(v.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }, [region, ngOnly]);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000); // live refresh
    return () => clearInterval(t);
  }, [load]);

  return (
    <div>
      <PageHeader
        title="Shipping Monitor"
        subtitle="Live vessel positions (real AIS data) on the China ↔ Nigeria trade lanes. Positions are real observations; 'bound for Nigeria' is derived from each ship's self-reported destination."
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
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Kpi
              label="Feed"
              value={status.connected ? "Connected" : "Reconnecting…"}
              sub={status.last_message_at ? new Date(status.last_message_at).toLocaleTimeString() : ""}
            />
            <Kpi label="Vessels tracked" value={num(status.vessels_tracked)} />
            <Kpi label="Bound for Nigeria" value={num(status.nigeria_bound)} />
            <Kpi label="Messages" value={num(status.messages_received)} />
          </div>

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
              <input type="checkbox" checked={ngOnly} onChange={(e) => setNgOnly(e.target.checked)} />
              Nigeria-bound only
            </label>
            <span className="ml-auto text-[11px] text-muted">Auto-refreshing every 15s</span>
          </div>

          <Card className="p-0">
            <div className="flex items-center justify-between border-b border-line px-4 py-2">
              <span className="text-sm font-medium">{vessels.length} vessels</span>
              <ProvenanceBadge origin="REAL" />
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-wash text-left text-xs uppercase tracking-wide text-muted">
                  <tr>
                    {["Vessel", "MMSI", "Position", "Speed", "Region", "Destination", "Seen"].map(
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
                      <td className="px-3 py-6 text-muted" colSpan={7}>
                        No vessels in view yet — data accumulates as ships report.
                      </td>
                    </tr>
                  ) : (
                    vessels.map((v) => (
                      <tr
                        key={v.mmsi}
                        className={`border-t border-line ${v.bound_for_nigeria ? "bg-green-500/15" : ""}`}
                      >
                        <td className="px-3 py-2 font-medium">
                          {v.name}
                          {v.bound_for_nigeria && (
                            <span className="ml-2 rounded bg-green-600 px-1 py-0.5 text-[9px] text-white">
                              → NIGERIA
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 tabular-nums text-muted">{v.mmsi}</td>
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
