from datetime import datetime, timezone

from app.services.eonet import parse_eonet
from app.services.httpclient import ExternalApiError
import pytest


def test_parse_eonet_point_and_polygon_locations():
    parsed = parse_eonet({"type": "FeatureCollection", "features": [
        {"id": "EONET_1", "geometry": {"type": "Point", "coordinates": [77.2, 13.1]},
         "properties": {"title": "Storm", "categories": [{"id": "severeStorms", "title": "Severe Storms"}],
                        "geometry": [{"date": "2026-10-25T00:00:00Z"}], "sources": [{"url": "https://example.org/event"}]}},
        {"id": "EONET_2", "geometry": {"type": "Polygon", "coordinates": [[[70, 10], [80, 10], [80, 20], [70, 20], [70, 10]]]}, "properties": {"title": "Fire"}},
        {"id": "EONET_BAD", "geometry": {"type": "Point", "coordinates": [250, 0]}, "properties": {}},
    ]})
    assert len(parsed.events) == 2 and parsed.skipped == 1
    point, polygon = parsed.events
    assert (point.latitude, point.longitude, point.event_type) == (13.1, 77.2, "severe storms")
    assert point.observed_at == datetime(2026, 10, 25, tzinfo=timezone.utc)
    assert polygon.attributes["location_approximate"] is True
    assert (polygon.latitude, polygon.longitude) == (15, 75)


def test_parse_eonet_collapses_event_track_to_latest_point():
    parsed = parse_eonet({"type": "FeatureCollection", "features": [
        {"id": "feature-old", "geometry": {"type": "Point", "coordinates": [80, 13]},
         "properties": {"id": "EONET_track", "date": "2026-10-24T00:00:00Z", "title": "Cyclone", "magnitudeValue": 25,
                        "magnitudeUnit": "kts", "categories": [{"title": "Severe Storms"}]}},
        {"id": "feature-new", "geometry": {"type": "Point", "coordinates": [82, 15]},
         "properties": {"id": "EONET_track", "date": "2026-10-25T00:00:00Z", "title": "Cyclone", "magnitudeValue": 40,
                        "magnitudeUnit": "kts", "categories": [{"title": "Severe Storms"}]}}
    ]})
    assert len(parsed.events) == 1
    assert parsed.events[0].longitude == 82 and parsed.events[0].magnitude == 40
    assert parsed.events[0].observed_at == datetime(2026, 10, 25, tzinfo=timezone.utc)


@pytest.mark.parametrize("payload", [None, {}, {"features": "bad"}])
def test_parse_eonet_rejects_invalid_shapes(payload):
    with pytest.raises(ExternalApiError):
        parse_eonet(payload)


def test_eonet_refresh_persists_and_filters_region(client, net):
    net.add("eonet.gsfc.nasa.gov", json={"type": "FeatureCollection", "features": [
        {"id": "EONET_1", "geometry": {"type": "Point", "coordinates": [77.2, 13.1]},
         "properties": {"title": "Storm in India", "categories": [{"id": "severeStorms", "title": "Severe Storms"}],
                        "geometry": [{"date": "2026-10-25T00:00:00Z"}], "sources": [{"url": "https://example.org/event"}]}}
    ]})
    result = client.post("/api/external/refresh", json={"sources": ["eonet"]}).json()["results"][0]
    assert result["status"] == "ok" and result["new"] == 1
    regional = client.get("/api/external/events", params={"source": "eonet", "west": 60, "south": 5, "east": 100, "north": 38})
    assert regional.status_code == 200 and regional.json()["total"] == 1
    assert "NASA" in regional.json()["items"][0]["attribution"]
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["external_observations"]["eonet"] == 1
    assert dashboard["recent_external_events"][0]["source"] == "eonet"
    assert dashboard["regional_overview"][0]["observations"] == 1
    assert dashboard["observation_coverage"]["unique_observations"] == 1

