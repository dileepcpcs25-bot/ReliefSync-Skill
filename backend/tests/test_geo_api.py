import pytest

from .helpers import CHENNAI


def test_create_disaster_with_coordinates(client, make):
    d = make.disaster(**CHENNAI)
    assert d["latitude"] == CHENNAI["latitude"] and d["location_source"] == "manual" and d["location_approximate"] is False


def test_disaster_without_coordinates_is_still_valid_and_coordinates_are_not_invented(client, make):
    d = make.disaster()
    assert d["latitude"] is None and d["longitude"] is None and d["location_source"] is None


@pytest.mark.parametrize("body", [{"latitude": 91, "longitude": 0}, {"latitude": 0, "longitude": 181}, {"latitude": 10}, {"longitude": 10}, {"latitude": "x", "longitude": 1}])
def test_invalid_or_partial_coordinates_rejected(client, body):
    base = {"disaster_type": "Flood", "location": "X", "severity": "High", "people_affected": 1}
    assert client.post("/api/disasters", json={**base, **body}).status_code == 422


def test_update_sets_position_and_source(client, make):
    d = make.disaster()
    r = client.patch(f"/api/disasters/{d['id']}", json={"latitude": 12.5, "longitude": 79.5, "location_source": "geocoded", "location_approximate": True})
    assert r.status_code == 200
    assert (r.json()["location_source"], r.json()["location_approximate"]) == ("geocoded", True)


def test_all_entities_accept_coordinates(client, make):
    assert make.shelter(**CHENNAI)["latitude"] == CHENNAI["latitude"]
    assert make.item(**CHENNAI)["longitude"] == CHENNAI["longitude"]
    assert make.volunteer(**CHENNAI)["latitude"] == CHENNAI["latitude"]
    d, item = make.disaster(), make.item(name="Rice", category="Food")
    r = client.post("/api/allocations", json={"disaster_id": d["id"], "item_id": item["id"], "quantity": 5, "destination": "Ward 3",
                                              "destination_latitude": 13.0, "destination_longitude": 80.2})
    assert r.status_code == 201 and r.json()["destination_latitude"] == 13.0
    bad = client.post("/api/allocations", json={"disaster_id": d["id"], "item_id": item["id"], "quantity": 5, "destination": "x", "destination_latitude": 13.0})
    assert bad.status_code == 422


def test_location_pickable_on_map_is_recorded(client, make):
    s = make.shelter(**CHENNAI, location_source="map")
    assert s["location_source"] == "map"


def test_allocation_destination_can_be_set_later(client, make):
    d, item = make.disaster(), make.item(name="Rice", category="Food")
    a = client.post("/api/allocations", json={"disaster_id": d["id"], "item_id": item["id"], "quantity": 1, "destination": "Ward 3"}).json()
    assert a["destination_latitude"] is None
    r = client.patch(f"/api/allocations/{a['id']}", json={"destination_latitude": 13.0, "destination_longitude": 80.2})
    assert r.status_code == 200 and r.json()["destination_latitude"] == 13.0
    assert client.patch(f"/api/allocations/{a['id']}", json={"destination_latitude": 13.0}).status_code == 422

def test_map_status_and_date_filters_are_applied_to_incidents(client, make):
    from datetime import date, timedelta

    active = make.disaster(**CHENNAI, status="Active")
    resolved = make.disaster(location="Past", status="Resolved", latitude=13.09, longitude=80.28)
    default = client.get("/api/map/features", params={"layers": "disasters"}).json()
    assert {f["id"] for f in default["features"] if f["kind"] == "disaster"} == {active["id"]}
    past = client.get("/api/map/features", params={"layers": "disasters", "status": "Resolved"}).json()
    assert {f["id"] for f in past["features"] if f["kind"] == "disaster"} == {resolved["id"]}
    future = (date.today() + timedelta(days=1)).isoformat()
    assert client.get("/api/map/features", params={"layers": "disasters", "since": future}).json()["features"] == []
    assert client.get("/api/map/features", params={"since": future, "until": "2020-01-01"}).status_code == 422
    assert client.get("/api/map/features", params={"status": "Unknown"}).status_code == 422
