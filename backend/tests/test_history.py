from .helpers import CHENNAI, NEAR
def test_historical_event_resource_lookup_uses_saved_records_and_current_state(client, make):
    from urllib.parse import quote

    event = make.disaster(**CHENNAI, status="Resolved")
    volunteer = make.volunteer(name="Nearby responder", **NEAR)
    make.volunteer(name="Unknown position")
    shelter = make.shelter(name="Nearby shelter", **NEAR)
    response = client.get("/api/history/events")
    assert response.status_code == 200
    stored = next(row for row in response.json()["items"] if row["key"] == f"local:{event['id']}")
    assert stored["status"] == "Resolved" and stored["event_at"]
    resources = client.get(f"/api/history/events/{quote(stored['key'], safe='')}/resources", params={"radius_km": 50})
    assert resources.status_code == 200
    data = resources.json()
    assert [row["id"] for row in data["volunteers"]] == [volunteer["id"]]
    assert [row["id"] for row in data["shelters"]] == [shelter["id"]]
    assert data["unlocated"]["volunteers"] == 1
    assert "current database values" in data["resource_time_note"]


def test_historical_resources_reject_missing_location_and_bad_bounds(client, make):
    from urllib.parse import quote

    event = make.disaster()
    key = quote(f"local:{event['id']}", safe="")
    response = client.get(f"/api/history/events/{key}/resources")
    assert response.status_code == 409
    assert client.get("/api/history/events", params={"south": 10}).status_code == 422

