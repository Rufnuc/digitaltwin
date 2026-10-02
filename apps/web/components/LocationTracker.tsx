"use client";
import { useEffect, useRef } from "react";
import { api, getToken } from "@/lib/api";

// Sends the logged-in user's location to the API while the app is open (company
// device). The browser still requires a one-time permission grant; if it is denied
// or unavailable we stay silent. The server throttles/decides what to store, but we
// also rate-limit here so we never ping more than once a minute.
const MIN_SEND_MS = 60_000;

export function LocationTracker() {
  const lastSent = useRef(0);

  useEffect(() => {
    if (typeof navigator === "undefined" || !navigator.geolocation) return;
    if (!getToken()) return; // only when logged in

    // Resolve a readable address in the browser (uses the device's own network, so it
    // works even if the server can't reach the internet). Best-effort; null on failure.
    const geocode = async (lat: number, lng: number): Promise<string | null> => {
      try {
        const r = await fetch(
          `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=jsonv2&zoom=18`,
          { headers: { Accept: "application/json" } },
        );
        if (!r.ok) return null;
        const j = await r.json();
        return j.display_name ?? null;
      } catch {
        return null;
      }
    };

    const send = async (pos: GeolocationPosition) => {
      const now = Date.now();
      if (now - lastSent.current < MIN_SEND_MS) return;
      lastSent.current = now;
      const address = await geocode(pos.coords.latitude, pos.coords.longitude);
      api
        .locationPing({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy ?? null,
          address,
        })
        .catch(() => {
          /* offline / not permitted — ignore */
        });
    };

    const watchId = navigator.geolocation.watchPosition(send, () => {}, {
      enableHighAccuracy: true,
      maximumAge: 30_000,
      timeout: 27_000,
    });
    return () => navigator.geolocation.clearWatch(watchId);
  }, []);

  return null;
}
