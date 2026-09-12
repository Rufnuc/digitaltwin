"""Live shipping monitor via aisstream.io (real AIS vessel data).

A single background WebSocket connection streams vessel positions for the China →
Nigeria trade lanes and keeps an in-memory store of the latest position per
vessel. Reads are served from that store, so endpoints never block on the socket.

Provenance: positions are REAL observations from AIS. The "bound for Nigeria" flag
is derived from each vessel's self-reported AIS destination (an ASSUMPTION about
intent, not a guarantee).

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

# Bounding boxes (each [[lat1,lon1],[lat2,lon2]]): China ports and the Nigerian coast.
CHINA_BOX = [[18.0, 108.0], [41.0, 127.0]]        # South/East China Sea major ports
NIGERIA_BOX = [[2.0, 2.0], [8.0, 9.0]]            # Gulf of Guinea (Lagos, Apapa, Onne)
BOUNDING_BOXES = [CHINA_BOX, NIGERIA_BOX]

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
        return "China / Asia"
    if -5 <= lon <= 12 and -8 <= lat <= 12:
        return "Nigeria / Gulf of Guinea"
    return "In transit"


def _is_nigeria_bound(destination: str | None) -> bool:
    if not destination:
        return False
    d = destination.upper()
    return any(tok in d for tok in _NG_DEST_TOKENS)


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
                 "ship_type": None, "destination": None, "region": "Unknown",
                 "bound_for_nigeria": False, "last_seen": None}
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
                 limit: int = 200) -> list[dict]:
        rows = [v for v in self.vessels.values() if v["lat"] is not None]
        if region:
            rows = [v for v in rows if v["region"] == region]
        if nigeria_bound is not None:
            rows = [v for v in rows if v["bound_for_nigeria"] == nigeria_bound]
        rows.sort(key=lambda v: v["last_seen"] or "", reverse=True)
        return rows[:limit]

    def status(self) -> dict:
        by_region: dict[str, int] = {}
        ng = 0
        for v in self.vessels.values():
            by_region[v["region"]] = by_region.get(v["region"], 0) + 1
            if v["bound_for_nigeria"]:
                ng += 1
        return {
            "enabled": bool(settings.AISSTREAM_API_KEY),
            "connected": self.connected,
            "vessels_tracked": len(self.vessels),
            "messages_received": self.messages,
            "nigeria_bound": ng,
            "by_region": by_region,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "error": self.error,
        }


# Module-level singleton (the API process's live view).
store = ShippingStore()
_task: asyncio.Task | None = None
_stop = asyncio.Event()


async def _run() -> None:
    import websockets  # optional dependency; only imported when shipping is enabled

    backoff = 3
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
                logger.info("aisstream connected; monitoring China↔Nigeria lanes")
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
    """Start the background collector if a key is configured (idempotent)."""
    global _task
    if not settings.AISSTREAM_API_KEY or store.started:
        return
    _stop.clear()
    store.started = True
    _task = asyncio.create_task(_run())


async def stop() -> None:
    _stop.set()
    if _task:
        _task.cancel()
