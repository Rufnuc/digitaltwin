"""Live shipping monitor via aisstream.io (real AIS vessel data).

A single background WebSocket connection streams vessel positions for the China →
Nigeria and Turkey → Nigeria trade lanes and keeps an in-memory store of the
latest position per vessel. Reads are served from that store, so endpoints never
block on the socket.

Provenance: positions are REAL observations from AIS. Whether a vessel will reach
Nigeria is answered two ways, both surfaced honestly:
  * Declared intent — the ship's self-reported AIS destination (+ ETA). Forward-
    looking, but self-reported: an intent signal, not a guarantee.
  * Observed arrival — because we track each vessel by MMSI over time, we record
    where we first saw it (its origin lane) and flag it when it later appears in
    Nigerian waters. That is a confirmed China/Turkey → Nigeria arrival.

Note: state is in-process (fine for a single API worker / dev). A multi-worker
production deployment would move this to Redis or a dedicated collector service.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from app.core.config import settings

logger = logging.getLogger("digitaltwin.shipping")

AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"

# Bounding boxes (each [[lat1,lon1],[lat2,lon2]]): source lanes + the Nigerian coast.
CHINA_BOX = [[18.0, 108.0], [41.0, 127.0]]        # South/East China Sea major ports
TURKEY_BOX = [[35.5, 26.0], [41.5, 37.0]]         # Marmara/Aegean/Med: Ambarlı, Izmir, Mersin
NIGERIA_BOX = [[2.0, 2.0], [8.0, 9.0]]            # Gulf of Guinea (Lagos, Apapa, Onne)
BOUNDING_BOXES = [CHINA_BOX, TURKEY_BOX, NIGERIA_BOX]

# Region labels used for origin tracking and the "source → Nigeria" routes.
CHINA_REGION = "China / Asia"
TURKEY_REGION = "Turkey / Mediterranean"
NIGERIA_REGION = "Nigeria / Gulf of Guinea"
SOURCE_REGIONS = (CHINA_REGION, TURKEY_REGION)

# Nigerian destinations in AIS free-text (port codes / names).
_NG_DEST_TOKENS = ("NGLOS", "NGAPP", "NGTIN", "NGONN", "NGPHC", "LAGOS", "APAPA",
                   "ONNE", "TINCAN", "TIN CAN", "NIGERIA", "PHC", "LEKKI")

_MAX_VESSELS = 1500
_TTL_SECONDS = 60 * 60  # drop vessels not seen for an hour


def _now() -> datetime:
    return datetime.now(timezone.utc)


def classify_region(lat: float | None, lon: float | None) -> str:
    if lat is None or lon is None:
        return "Unknown"
    if 100 <= lon <= 130 and 0 <= lat <= 45:
        return CHINA_REGION
    if 25 <= lon <= 38 and 34 <= lat <= 42:
        return TURKEY_REGION
    if -5 <= lon <= 12 and -8 <= lat <= 12:
        return NIGERIA_REGION
    return "In transit"


def _is_nigeria_bound(destination: str | None) -> bool:
    if not destination:
        return False
    d = destination.upper()
    return any(tok in d for tok in _NG_DEST_TOKENS)


def _format_eta(eta: dict | None) -> str | None:
    """AIS ETA is broadcast as month/day/hour/minute (no year). Render it, or None
    when the ship left the field blank (all zeros / 24 / 60 = 'not available')."""
    if not isinstance(eta, dict):
        return None
    mo, day = eta.get("Month") or 0, eta.get("Day") or 0
    hr, mi = eta.get("Hour"), eta.get("Minute")
    if not mo or not day:
        return None
    hr = 0 if hr in (None, 24) else hr
    mi = 0 if mi in (None, 60) else mi
    return f"{mo:02d}-{day:02d} {hr:02d}:{mi:02d} UTC"


class ShippingStore:
    def __init__(self) -> None:
        self.vessels: dict[int, dict] = {}
        self.connected = False
        self.messages = 0
        self.last_message_at: datetime | None = None
        self.error: str | None = None
        self.started = False

    # --- updates (called from the collector loop) ---
    def _vessel(self, mmsi: int, name: str | None) -> dict:
        v = self.vessels.get(mmsi)
        if v is None:
            v = {"mmsi": mmsi, "name": (name or "").strip() or f"MMSI {mmsi}",
                 "lat": None, "lon": None, "sog": None, "cog": None,
                 "ship_type": None, "destination": None, "eta": None,
                 "region": "Unknown", "origin_region": None,
                 "bound_for_nigeria": False, "arrived_nigeria": False,
                 "first_seen": _now().isoformat(), "last_seen": None}
            self.vessels[mmsi] = v
        elif name and name.strip():
            v["name"] = name.strip()
        return v

    def update_position(self, md: dict, report: dict) -> None:
        mmsi = md.get("MMSI")
        if not mmsi:
            return
        v = self._vessel(mmsi, md.get("ShipName"))
        lat = md.get("latitude", report.get("Latitude"))
        lon = md.get("longitude", report.get("Longitude"))
        v["lat"] = round(lat, 4) if isinstance(lat, int | float) else v["lat"]
        v["lon"] = round(lon, 4) if isinstance(lon, int | float) else v["lon"]
        if isinstance(report.get("Sog"), int | float):
            v["sog"] = report["Sog"]
        if isinstance(report.get("Cog"), int | float):
            v["cog"] = report["Cog"]
        v["region"] = classify_region(v["lat"], v["lon"])
        # Record where we first saw the vessel (its origin lane) so a China- or
        # Turkey-origin ship that later shows up in Nigeria is a confirmed route.
        if v["origin_region"] is None and v["region"] not in ("Unknown", "In transit"):
            v["origin_region"] = v["region"]
        if v["region"] == NIGERIA_REGION:
            v["arrived_nigeria"] = True
        v["last_seen"] = _now().isoformat()
        self._touch()

    def update_static(self, md: dict, static: dict) -> None:
        mmsi = md.get("MMSI")
        if not mmsi:
            return
        v = self._vessel(mmsi, md.get("ShipName"))
        dest = (static.get("Destination") or "").strip()
        if dest:
            v["destination"] = dest
            v["bound_for_nigeria"] = _is_nigeria_bound(dest)
        eta = _format_eta(static.get("Eta"))
        if eta:
            v["eta"] = eta
        if static.get("Type") is not None:
            v["ship_type"] = static.get("Type")
        v["last_seen"] = _now().isoformat()
        self._touch()

    def _touch(self) -> None:
        self.messages += 1
        self.last_message_at = _now()
        if len(self.vessels) > _MAX_VESSELS:
            self._prune()

    def _prune(self) -> None:
        cutoff = _now().timestamp() - _TTL_SECONDS
        stale = [m for m, v in self.vessels.items()
                 if v["last_seen"] and datetime.fromisoformat(v["last_seen"]).timestamp() < cutoff]
        for m in stale:
            self.vessels.pop(m, None)
        # Still too many? keep the most recently seen.
        if len(self.vessels) > _MAX_VESSELS:
            ordered = sorted(
                self.vessels.values(), key=lambda v: v["last_seen"] or "", reverse=True
            )
            self.vessels = {v["mmsi"]: v for v in ordered[:_MAX_VESSELS]}

    # --- reads (served to endpoints) ---
    def snapshot(self, region: str | None = None, nigeria_bound: bool | None = None,
                 origin: str | None = None, nigeria_watch: bool | None = None,
                 limit: int = 200) -> list[dict]:
        rows = [v for v in self.vessels.values() if v["lat"] is not None]
        if region:
            rows = [v for v in rows if v["region"] == region]
        if origin:
            rows = [v for v in rows if v["origin_region"] == origin]
        if nigeria_bound is not None:
            rows = [v for v in rows if v["bound_for_nigeria"] == nigeria_bound]
        if nigeria_watch:
            # Every ship that will (declared) or did (observed) touch Nigeria.
            rows = [v for v in rows if v["bound_for_nigeria"] or v["arrived_nigeria"]]
        rows.sort(key=lambda v: v["last_seen"] or "", reverse=True)
        return rows[:limit]

    def status(self) -> dict:
        by_region: dict[str, int] = {}
        by_origin: dict[str, int] = {}
        ng = 0
        # source lane -> {declared: bound for Nigeria now, arrived: seen in NG waters}
        lanes = {r: {"declared": 0, "arrived": 0} for r in SOURCE_REGIONS}
        for v in self.vessels.values():
            by_region[v["region"]] = by_region.get(v["region"], 0) + 1
            if v["origin_region"]:
                by_origin[v["origin_region"]] = by_origin.get(v["origin_region"], 0) + 1
            if v["bound_for_nigeria"]:
                ng += 1
            src = v["origin_region"]
            if src in lanes:
                if v["bound_for_nigeria"]:
                    lanes[src]["declared"] += 1
                if v["arrived_nigeria"]:
                    lanes[src]["arrived"] += 1
        return {
            "enabled": bool(settings.AISSTREAM_API_KEY),
            "connected": self.connected,
            "vessels_tracked": len(self.vessels),
            "messages_received": self.messages,
            "nigeria_bound": ng,
            "by_region": by_region,
            "by_origin": by_origin,
            # "Will they touch Nigeria?" answered per source lane, two ways.
            "nigeria_watch": {
                "china_declared": lanes[CHINA_REGION]["declared"],
                "china_arrived": lanes[CHINA_REGION]["arrived"],
                "turkey_declared": lanes[TURKEY_REGION]["declared"],
                "turkey_arrived": lanes[TURKEY_REGION]["arrived"],
            },
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "error": self.error,
        }

    # --- persistence (durable state across restarts) ---
    _PERSISTED = ("mmsi", "name", "lat", "lon", "sog", "cog", "ship_type", "destination",
                  "eta", "region", "origin_region", "bound_for_nigeria", "arrived_nigeria",
                  "first_seen", "last_seen")

    def load_from_db(self, session) -> int:
        """Rehydrate the in-memory store from persisted vessel tracks (on startup)."""
        from app.models.shipping import VesselTrack

        rows = session.query(VesselTrack).all()
        for r in rows:
            self.vessels[r.mmsi] = {k: getattr(r, k) for k in self._PERSISTED}
        return len(rows)

    def flush_to_db(self, session) -> int:
        """Upsert the current in-memory vessels into the durable table."""
        from app.models.shipping import VesselTrack

        snapshot = list(self.vessels.values())  # copy — the collector may mutate concurrently
        for v in snapshot:
            row = session.get(VesselTrack, v["mmsi"])
            if row is None:
                session.add(VesselTrack(**{k: v.get(k) for k in self._PERSISTED}))
            else:
                for k in self._PERSISTED:
                    if k != "mmsi":
                        setattr(row, k, v.get(k))
        session.commit()
        return len(snapshot)


# Module-level singleton (the API process's live view).
store = ShippingStore()
_task: asyncio.Task | None = None
_stop = asyncio.Event()

_FLUSH_INTERVAL = 60  # seconds between persisting the store to the DB


async def _flush() -> None:
    """Persist the store off the event loop (sync DB work in a worker thread)."""
    from app.db.session import SessionLocal

    def _work() -> int:
        db = SessionLocal()
        try:
            return store.flush_to_db(db)
        finally:
            db.close()

    try:
        n = await asyncio.get_running_loop().run_in_executor(None, _work)
        logger.debug("shipping: persisted %s vessel tracks", n)
    except Exception as e:  # noqa: BLE001 — persistence must never kill the collector
        logger.warning("shipping: flush failed: %s", e)


async def _run() -> None:
    import websockets  # optional dependency; only imported when shipping is enabled

    backoff = 3
    last_flush = 0.0
    while not _stop.is_set():
        try:
            async with websockets.connect(AISSTREAM_URL, open_timeout=20) as ws:
                await ws.send(json.dumps({
                    "APIKey": settings.AISSTREAM_API_KEY,
                    "BoundingBoxes": BOUNDING_BOXES,
                    "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
                }))
                store.connected = True
                store.error = None
                backoff = 3
                logger.info("aisstream connected; monitoring China & Turkey → Nigeria lanes")
                while not _stop.is_set():
                    raw = await asyncio.wait_for(ws.recv(), timeout=60)
                    msg = json.loads(raw)
                    mt = msg.get("MessageType")
                    md = msg.get("MetaData", {})
                    body = msg.get("Message", {})
                    if mt == "PositionReport":
                        store.update_position(md, body.get("PositionReport", {}))
                    elif mt == "ShipStaticData":
                        store.update_static(md, body.get("ShipStaticData", {}))
                    now = asyncio.get_running_loop().time()
                    if now - last_flush >= _FLUSH_INTERVAL:
                        last_flush = now
                        await _flush()
        except asyncio.CancelledError:
            break
        except Exception as e:  # noqa: BLE001 — keep the collector alive across errors
            store.connected = False
            store.error = f"{type(e).__name__}: {e}"
            logger.warning("aisstream disconnected: %s (retry in %ss)", store.error, backoff)
            try:
                await asyncio.wait_for(_stop.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 60)
    store.connected = False


def start() -> None:
    """Start the background collector if a key is configured (idempotent).

    Rehydrates durable vessel state first so origin/arrival history survives a
    restart, then launches the live WebSocket collector.
    """
    global _task
    if not settings.AISSTREAM_API_KEY or store.started:
        return
    _stop.clear()
    store.started = True
    try:
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            n = store.load_from_db(db)
            if n:
                logger.info("shipping: rehydrated %s vessel tracks from DB", n)
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001 — a cold start (no table yet) must not block
        logger.warning("shipping: could not load persisted tracks: %s", e)
    _task = asyncio.create_task(_run())


async def stop() -> None:
    _stop.set()
    if _task:
        _task.cancel()
    # Persist a final snapshot so nothing observed this session is lost.
    await _flush()
