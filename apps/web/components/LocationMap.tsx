"use client";
import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { UserLocationLatest, UserLocationPoint } from "@/lib/api";

const esc = (s: unknown) =>
  String(s ?? "—").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] as string,
  );

export function LocationMap({
  people,
  trail,
  onSelect,
}: {
  people: UserLocationLatest[];
  trail: UserLocationPoint[];
  onSelect: (userId: number) => void;
}) {
  const elRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const pinsRef = useRef<L.LayerGroup | null>(null);
  const trailRef = useRef<L.LayerGroup | null>(null);
  const fittedRef = useRef(false);

  useEffect(() => {
    if (mapRef.current || !elRef.current) return;
    const map = L.map(elRef.current, { minZoom: 2 }).setView([9.08, 8.68], 6); // Nigeria
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 19,
    }).addTo(map);
    pinsRef.current = L.layerGroup().addTo(map);
    trailRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Pins: latest position per user.
  useEffect(() => {
    const layer = pinsRef.current;
    const map = mapRef.current;
    if (!layer || !map) return;
    layer.clearLayers();
    const pts: [number, number][] = [];
    for (const p of people) {
      pts.push([p.lat, p.lng]);
      const when = p.recorded_at
        ? new Date(p.recorded_at).toLocaleString("en-NG", { dateStyle: "medium", timeStyle: "short" })
        : "—";
      L.circleMarker([p.lat, p.lng], {
        radius: 7,
        color: "#00000033",
        weight: 1,
        fillColor: "#2563eb",
        fillOpacity: 0.9,
      })
        .bindPopup(
          `<div style="font-size:12px;line-height:1.5"><strong>${esc(p.user_name)}</strong>` +
            `<br/>${esc(p.role)}<br/>last seen ${esc(when)}` +
            `<br/>±${p.accuracy != null ? Math.round(p.accuracy) + "m" : "—"}</div>`,
        )
        .on("click", () => onSelect(p.user_id))
        .addTo(layer);
    }
    if (!fittedRef.current && pts.length > 0) {
      map.fitBounds(L.latLngBounds(pts).pad(0.3), { maxZoom: 13 });
      fittedRef.current = true;
    }
  }, [people, onSelect]);

  // Trail: history for the selected user.
  useEffect(() => {
    const layer = trailRef.current;
    const map = mapRef.current;
    if (!layer || !map) return;
    layer.clearLayers();
    if (trail.length === 0) return;
    const pts: [number, number][] = trail.map((p) => [p.lat, p.lng]);
    L.polyline(pts, { color: "#f59e0b", weight: 3, opacity: 0.8 }).addTo(layer);
    for (const p of trail) {
      L.circleMarker([p.lat, p.lng], {
        radius: 3,
        color: "#f59e0b",
        fillColor: "#f59e0b",
        fillOpacity: 0.8,
      }).addTo(layer);
    }
    map.fitBounds(L.latLngBounds(pts).pad(0.3), { maxZoom: 15 });
  }, [trail]);

  return (
    <div className="overflow-hidden rounded-lg border border-line">
      <div ref={elRef} style={{ height: 460, width: "100%" }} className="z-0" />
    </div>
  );
}
