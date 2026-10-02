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

    const send = (pos: GeolocationPosition) => {
      const now = Date.now();
      if (now - lastSent.current < MIN_SEND_MS) return;
      lastSent.current = now;
      api
        .locationPing({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy ?? null,
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
