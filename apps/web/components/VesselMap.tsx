"use client";
import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Vessel } from "@/lib/api";

// Colour a vessel by its origin lane; Nigeria-bound/arrived overrides to green.
function colorFor(v: Vessel): string {
  if (v.arrived_nigeria) return "#15803d"; // arrived — dark green
  if (v.bound_for_nigeria) return "#22c55e"; // declared — green
  if (v.origin_region === "China / Asia") return "#3b82f6"; // blue
  if (v.origin_region === "Turkey / Mediterranean") return "#f59e0b"; // amber
  return "#9ca3af"; // unknown origin — grey
}

function popupHtml(v: Vessel): string {
  const esc = (s: unknown) =>
    String(s ?? "—").replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] as string,
    );
  const tag = v.arrived_nigeria
    ? " · ✓ arrived NG"
    : v.bound_for_nigeria
      ? " · → Nigeria"
      : "";
  return `<div style="font-size:12px;line-height:1.5">
    <strong>${esc(v.name)}</strong>${tag}<br/>
    MMSI ${esc(v.mmsi)}<br/>
    Origin: ${esc(v.origin_region?.split(" / ")[0])}<br/>
    Speed: ${v.sog != null ? esc(v.sog) + " kn" : "—"}<br/>
    Dest: ${esc(v.destination)}<br/>
    ETA: ${esc(v.eta)}
  </div>`;
}

export function VesselMap({ vessels }: { vessels: Vessel[] }) {
  const elRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);
  const fittedRef = useRef(false);

  // Initialise the map once.
  useEffect(() => {
    if (mapRef.current || !elRef.current) return;
    const map = L.map(elRef.current, { worldCopyJump: true, minZoom: 2 }).setView([15, 40], 3);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 12,
    }).addTo(map);
    layerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      layerRef.current = null;
    };
  }, []);

  // Redraw markers whenever the vessel list changes.
  useEffect(() => {
    const layer = layerRef.current;
    const map = mapRef.current;
    if (!layer || !map) return;
    layer.clearLayers();
    const pts: [number, number][] = [];
    for (const v of vessels) {
      if (v.lat == null || v.lon == null) continue;
      pts.push([v.lat, v.lon]);
      const highlighted = v.bound_for_nigeria || v.arrived_nigeria;
      L.circleMarker([v.lat, v.lon], {
        radius: highlighted ? 6 : 4,
        color: "#00000033",
        weight: 1,
        fillColor: colorFor(v),
        fillOpacity: 0.9,
      })
        .bindPopup(popupHtml(v))
        .addTo(layer);
    }
    // Fit to the vessels once, so the user lands on the populated area.
    if (!fittedRef.current && pts.length > 0) {
      map.fitBounds(L.latLngBounds(pts).pad(0.2), { maxZoom: 5 });
      fittedRef.current = true;
    }
  }, [vessels]);

  return (
    <div className="overflow-hidden rounded-lg border border-line">
      <div ref={elRef} style={{ height: 380, width: "100%" }} className="z-0" />
    </div>
  );
}
