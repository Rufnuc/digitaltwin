"""Shipping monitor store logic (no network — the WebSocket is not exercised)."""
from __future__ import annotations

from app.services.shipping.collector import ShippingStore, classify_region


def test_region_classification():
    assert classify_region(31.2, 121.5) == "China / Asia"        # Shanghai
    assert classify_region(40.96, 28.7) == "Turkey / Mediterranean"  # Ambarlı (Istanbul)
    assert classify_region(36.8, 34.6) == "Turkey / Mediterranean"  # Mersin
    assert classify_region(6.4, 3.4) == "Nigeria / Gulf of Guinea"  # Lagos
    assert classify_region(-34.0, 18.0) == "In transit"          # off South Africa
    assert classify_region(None, None) == "Unknown"


def test_origin_tracking_and_confirmed_arrival():
    """A Turkey-origin vessel later seen in Nigerian waters is a confirmed route."""
    s = ShippingStore()
    # First sighting: off Mersin, Turkey.
    s.update_position({"MMSI": 555, "ShipName": "BOSPHORUS", "latitude": 36.8, "longitude": 34.6}, {})
    v = s.vessels[555]
    assert v["origin_region"] == "Turkey / Mediterranean"
    assert v["arrived_nigeria"] is False

    # Same vessel later reports from Lagos — origin stays Turkey, now arrived.
    s.update_position({"MMSI": 555, "latitude": 6.4, "longitude": 3.4}, {})
    v = s.vessels[555]
    assert v["origin_region"] == "Turkey / Mediterranean"  # unchanged
    assert v["region"] == "Nigeria / Gulf of Guinea"
    assert v["arrived_nigeria"] is True

    watch = s.status()["nigeria_watch"]
    assert watch["turkey_arrived"] == 1


def test_eta_parsing_and_watch_filter():
    s = ShippingStore()
    s.update_position({"MMSI": 9, "ShipName": "C", "latitude": 31.2, "longitude": 121.5}, {})
    s.update_static({"MMSI": 9}, {"Destination": "NGLOS", "Eta": {"Month": 5, "Day": 12,
                                                                  "Hour": 14, "Minute": 30}})
    v = s.vessels[9]
    assert v["eta"] == "05-12 14:30 UTC"
    # A blank ETA (all zeros) is left as None rather than shown as 00-00.
    s.update_static({"MMSI": 9}, {"Eta": {"Month": 0, "Day": 0, "Hour": 24, "Minute": 60}})
    assert s.vessels[9]["eta"] == "05-12 14:30 UTC"  # kept prior good value

    # nigeria_watch returns declared + arrived.
    assert len(s.snapshot(nigeria_watch=True)) == 1


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


def test_persistence_round_trip(db):
    """Vessel state persisted to the DB is rehydrated into a fresh store."""
    s = ShippingStore()
    s.update_position({"MMSI": 700, "ShipName": "PERSISTENT", "latitude": 36.8, "longitude": 34.6},
                      {"Sog": 10})
    s.update_static({"MMSI": 700}, {"Destination": "NGLOS"})
    assert s.flush_to_db(db) == 1

    fresh = ShippingStore()
    assert fresh.load_from_db(db) == 1
    v = fresh.vessels[700]
    assert v["name"] == "PERSISTENT"
    assert v["origin_region"] == "Turkey / Mediterranean"
    assert v["bound_for_nigeria"] is True

    # A second flush updates in place rather than duplicating.
    s.update_position({"MMSI": 700, "latitude": 6.4, "longitude": 3.4}, {})
    s.flush_to_db(db)
    from app.models.shipping import VesselTrack
    assert db.query(VesselTrack).count() == 1
    assert db.get(VesselTrack, 700).arrived_nigeria is True


def test_shipping_status_endpoint(client, auth_headers):
    r = client.get("/api/v1/shipping/status", headers=auth_headers("VIEWER"))
    assert r.status_code == 200
    body = r.json()
    # Disabled in tests (no key) — reported honestly, never faked.
    assert body["enabled"] is False
    assert body["vessels_tracked"] == 0
