"""Shipping monitor store logic (no network — the WebSocket is not exercised)."""
from __future__ import annotations

from app.services.shipping.collector import ShippingStore, classify_region


def test_region_classification():
    assert classify_region(31.2, 121.5) == "China / Asia"        # Shanghai
    assert classify_region(6.4, 3.4) == "Nigeria / Gulf of Guinea"  # Lagos
    assert classify_region(-34.0, 18.0) == "In transit"          # off South Africa
    assert classify_region(None, None) == "Unknown"


def test_position_and_static_updates_and_nigeria_flag():
    s = ShippingStore()
    s.update_position({"MMSI": 111, "ShipName": "EVER GIVEN", "latitude": 6.4, "longitude": 3.4},
                      {"Sog": 12.5, "Cog": 210})
    s.update_static({"MMSI": 111}, {"Destination": "NGLOS", "Type": 70})

    v = s.vessels[111]
    assert v["name"] == "EVER GIVEN"
    assert v["region"] == "Nigeria / Gulf of Guinea"
    assert v["sog"] == 12.5
    assert v["bound_for_nigeria"] is True         # NGLOS = Lagos
    assert v["destination"] == "NGLOS"

    # A vessel bound elsewhere is not flagged.
    s.update_position({"MMSI": 222, "ShipName": "MAERSK", "latitude": 31.2, "longitude": 121.5}, {})
    s.update_static({"MMSI": 222}, {"Destination": "SGSIN"})
    assert s.vessels[222]["bound_for_nigeria"] is False


def test_snapshot_filters():
    s = ShippingStore()
    s.update_position({"MMSI": 1, "ShipName": "A", "latitude": 6.4, "longitude": 3.4}, {})
    s.update_static({"MMSI": 1}, {"Destination": "APAPA"})
    s.update_position({"MMSI": 2, "ShipName": "B", "latitude": 31.2, "longitude": 121.5}, {})

    assert len(s.snapshot()) == 2
    assert len(s.snapshot(region="China / Asia")) == 1
    ng = s.snapshot(nigeria_bound=True)
    assert len(ng) == 1 and ng[0]["mmsi"] == 1

    st = s.status()
    assert st["vessels_tracked"] == 2 and st["nigeria_bound"] == 1


def test_shipping_status_endpoint(client, auth_headers):
    r = client.get("/api/v1/shipping/status", headers=auth_headers("VIEWER"))
    assert r.status_code == 200
    body = r.json()
    # Disabled in tests (no key) — reported honestly, never faked.
    assert body["enabled"] is False
    assert body["vessels_tracked"] == 0
