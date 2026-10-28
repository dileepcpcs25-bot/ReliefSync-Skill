"""External observations: parsing documented response shapes, failure handling, dedupe, caching, honesty."""
from datetime import datetime, timezone

import httpx
import pytest

from app.models import ExternalEvent, ExternalFetchLog
from app.services import external_ingest
from app.services.external_sources import parse_firms_csv, parse_gdacs, parse_usgs, usgs_magnitude_band
from app.services.httpclient import ExternalApiError

MS = int(datetime(2026, 10, 24, 6, 0, tzinfo=timezone.utc).timestamp() * 1000)


def usgs_payload():
    return {"type": "FeatureCollection", "metadata": {"status": 200, "count": 5}, "features": [
        {"type": "Feature", "id": "us1000abc", "properties": {"mag": 6.4, "place": "10 km N of Sendai", "time": MS, "updated": MS + 60000, "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us1000abc",
                                                              "alert": "orange", "tsunami": 1, "sig": 630, "status": "reviewed", "type": "earthquake", "title": "M 6.4 - 10 km N of Sendai", "magType": "mww"},
         "geometry": {"type": "Point", "coordinates": [141.0, 38.3, 25.0]}},
        {"type": "Feature", "id": "us2000small", "properties": {"mag": 4.6, "place": "Somewhere", "time": MS, "type": "earthquake"}, "geometry": {"type": "Point", "coordinates": [10.0, 20.0, 5]}},
        {"type": "Feature", "id": "bad-coords", "properties": {"mag": 5}, "geometry": {"type": "Point", "coordinates": [200.0, 95.0, 1]}},   # invalid range
        {"type": "Feature", "id": "no-geometry", "properties": {"mag": 5}, "geometry": None},
        {"type": "Feature", "properties": {"mag": 5}, "geometry": {"type": "Point", "coordinates": [1, 2, 3]}},                               # no id
    ]}


def gdacs_payload():
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [141.05, 38.28]}, "properties": {
            "eventtype": "EQ", "eventid": 1557413, "episodeid": 1724396, "name": "Earthquake in Japan", "alertlevel": "Green", "alertscore": 1, "country": "Japan", "iso3": "JPN",
            "fromdate": "2026-10-24T06:01:10", "todate": "2026-10-24T06:01:10", "datemodified": "2026-10-24T07:00:00", "iscurrent": "true", "source": "NEIC",
            "severitydata": {"severity": 6.2, "severitytext": "Magnitude 6.2M, Depth:30km", "severityunit": "M"}, "url": {"report": "https://www.gdacs.org/report.aspx?eventid=1557413&eventtype=EQ"}}},
        {"type": "Feature", "geometry": {"type": "Polygon"}, "bbox": [90, 10, 100, 20], "properties": {
            "eventtype": "FL", "eventid": 99, "name": "Flood in Myanmar", "alertlevel": "Orange", "country": "Myanmar", "fromdate": "2026-10-20T00:00:00", "iscurrent": True}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [None, None]}, "properties": {"eventtype": "TC", "eventid": 5}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 1]}, "properties": {"eventtype": "", "eventid": None}},
    ]}


FIRMS_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
-33.1,148.2,340.1,0.4,0.4,2026-10-24,0142,N,VIIRS,h,2.0NRT,300.2,75.5,N
-33.2,148.3,330.0,0.4,0.4,2026-10-24,0142,N,VIIRS,l,2.0NRT,300.2,3.0,N
-33.3,148.4,335.0,0.4,0.4,2026-10-24,0142,N,VIIRS,n,2.0NRT,300.2,12.0,N
abc,148.4,335.0,0.4,0.4,2026-10-24,0142,N,VIIRS,n,2.0NRT,300.2,12.0,N
"""


# ------------------------------------------------------------------ parsing
def test_parse_usgs_normalises_and_skips_invalid():
    res = parse_usgs(usgs_payload())
    assert [e.external_id for e in res.events] == ["us1000abc", "us2000small"]
    assert res.skipped == 3
    quake = res.events[0]
    assert (quake.latitude, quake.longitude, quake.depth_km, quake.magnitude) == (38.3, 141.0, 25.0, 6.4)
    assert quake.severity_estimate == "High" and quake.source_alert_level == "orange"
    assert quake.observed_at == datetime(2026, 10, 24, 6, 0, tzinfo=timezone.utc) and quake.source_updated_at > quake.observed_at
    assert res.events[1].severity_estimate == "Low"


@pytest.mark.parametrize("payload", [None, [], {}, {"features": "nope"}, "404 File Not Found"])
def test_parse_usgs_rejects_malformed_payloads(payload):
    with pytest.raises(ExternalApiError) as exc:
        parse_usgs(payload)
    assert exc.value.kind == "malformed"


def test_magnitude_bands():
    assert [usgs_magnitude_band(m) for m in (None, 4.9, 5.0, 6.0, 7.0)] == ["Low", "Low", "Medium", "High", "Critical"]


def test_parse_gdacs():
    res = parse_gdacs(gdacs_payload())
    assert [e.external_id for e in res.events] == ["EQ-1557413", "FL-99"]
    assert res.skipped == 2
    eq, fl = res.events
    assert eq.event_type == "earthquake" and eq.severity_estimate == "Low" and eq.magnitude == 6.2 and eq.country == "Japan"
    assert eq.observed_at == datetime(2026, 10, 24, 6, 1, 10, tzinfo=timezone.utc)  # offset-less GDACS time is UTC
    assert fl.severity_estimate == "High" and (fl.latitude, fl.longitude) == (15.0, 95.0) and fl.attributes["location_approximate"] is True


def test_parse_gdacs_malformed():
    with pytest.raises(ExternalApiError):
        parse_gdacs({"nope": 1})


def test_parse_firms_drops_low_confidence_and_bad_rows():
    res = parse_firms_csv(FIRMS_CSV, "VIIRS_SNPP_NRT")
    assert len(res.events) == 2 and res.skipped == 1
    assert res.events[0].magnitude == 75.5 and res.events[0].severity_estimate == "Medium"  # highest FRP first
    assert res.events[0].attributes["note"].startswith("Thermal anomaly")


def test_parse_firms_error_text_is_not_csv():
    with pytest.raises(ExternalApiError):
        parse_firms_csv("Invalid MAP_KEY.", "VIIRS_SNPP_NRT")


def test_parse_firms_row_cap():
    rows = "\n".join(f"{10+i/100},20,300,1,1,2026-10-24,0100,N,VIIRS,h,2,300,{i},N" for i in range(10))
    res = parse_firms_csv("latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n" + rows, "S", max_rows=3)
    assert len(res.events) == 3 and res.truncated


# ------------------------------------------------------------------ refresh through the API
def test_refresh_stores_events_with_source_and_retrieval_time(client, net):
    net.add("earthquake.usgs.gov", json=usgs_payload())
    net.add("gdacs.org", json=gdacs_payload())
    r = client.post("/api/external/refresh", json={"sources": ["usgs", "gdacs"]})
    assert r.status_code == 200
    by = {x["source"]: x for x in r.json()["results"]}
    assert by["usgs"]["status"] == "ok" and by["usgs"]["new"] == 2 and by["usgs"]["skipped"] == 3
    items = client.get("/api/external/events", params={"include_duplicates": True}).json()["items"]
    assert len(items) == 4
    e = next(i for i in items if i["external_id"] == "us1000abc")
    assert e["source"] == "usgs" and e["retrieved_at"] and e["observed_at"].startswith("2026-10-24")
    assert "unverified" in e["label"].lower() and e["severity_label"].startswith("Estimate")
    assert e["review_status"] == "Unreviewed"
    status = client.get("/api/external/status").json()["sources"]
    assert next(s for s in status if s["source"] == "usgs")["last_success_at"]


def test_event_is_deduplicated_by_source_id_and_updated_in_place(client, net):
    net.add("earthquake.usgs.gov", json=usgs_payload())
    client.post("/api/external/refresh", json={"sources": ["usgs"], "force": True})
    changed = usgs_payload()
    changed["features"][0]["properties"]["mag"] = 6.9
    net.routes.clear()
    net.add("earthquake.usgs.gov", json=changed)
    r = client.post("/api/external/refresh", json={"sources": ["usgs"], "force": True}).json()["results"][0]
    assert (r["new"], r["updated"]) == (0, 2)
    items = client.get("/api/external/events").json()["items"]
    assert len(items) == 2 and next(i for i in items if i["external_id"] == "us1000abc")["magnitude"] == 6.9


def test_same_earthquake_from_two_sources_is_linked_not_double_counted(client, net):
    net.add("earthquake.usgs.gov", json=usgs_payload())
    net.add("gdacs.org", json=gdacs_payload())
    client.post("/api/external/refresh", json={"sources": ["usgs", "gdacs"]})
    visible = client.get("/api/external/events", params={"event_type": "earthquake"}).json()["items"]
    assert sorted(i["source"] for i in visible) == ["usgs", "usgs"]            # GDACS twin hidden
    everything = client.get("/api/external/events", params={"event_type": "earthquake", "include_duplicates": True}).json()["items"]
    twin = next(i for i in everything if i["source"] == "gdacs")
    assert twin["duplicate_of_id"] is not None                                  # kept, just linked


def test_different_quakes_are_not_merged(client, db_session=None):
    from app.database import SessionLocal
    from app.services.external_sources import NormalizedEvent

    t = datetime(2026, 10, 24, 6, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:
        external_ingest.upsert_events(db, [
            NormalizedEvent("usgs", "a", "earthquake", "A", 10, 10, "Low", observed_at=t, magnitude=5.0),
            NormalizedEvent("gdacs", "EQ-1", "earthquake", "B", 10, 10, "Low", observed_at=t, magnitude=7.5),     # magnitude too different
            NormalizedEvent("gdacs", "EQ-2", "earthquake", "C", 40, 10, "Low", observed_at=t, magnitude=5.0),     # too far
        ])
        assert external_ingest.link_cross_source_duplicates(db) == 0


@pytest.mark.parametrize("route,expected", [
    ({"status": 500}, "HTTP 500"),
    ({"status": 503}, "HTTP 503"),
    ({"exc": httpx.ReadTimeout("slow")}, "Timed out"),
    ({"exc": httpx.ConnectError("down")}, "Could not reach"),
    ({"status": 404}, "HTTP 404"),
    ({"status": 429}, "rate limit"),
    ({"status": 200, "text": "404 File Not Found"}, "not valid JSON"),
    ({"status": 200, "json": {"features": "x"}}, "no 'features'"),
])
def test_api_failures_are_reported_and_nothing_is_fabricated(client, net, route, expected):
    net.add("earthquake.usgs.gov", **route)
    r = client.post("/api/external/refresh", json={"sources": ["usgs"]})
    assert r.status_code == 200
    result = r.json()["results"][0]
    assert result["status"] == "error" and expected in result["message"]
    assert client.get("/api/external/events").json()["items"] == []            # no invented events
    st = next(s for s in client.get("/api/external/status").json()["sources"] if s["source"] == "usgs")
    assert st["last_status"] == "error" and st["last_success_at"] is None


def test_failure_keeps_previously_stored_events(client, net):
    net.add("earthquake.usgs.gov", json=usgs_payload())
    client.post("/api/external/refresh", json={"sources": ["usgs"], "force": True})
    net.routes.clear()
    net.add("earthquake.usgs.gov", status=500)
    client.post("/api/external/refresh", json={"sources": ["usgs"], "force": True})
    assert len(client.get("/api/external/events").json()["items"]) == 2
    st = next(s for s in client.get("/api/external/status").json()["sources"] if s["source"] == "usgs")
    assert st["last_status"] == "error" and st["last_success_at"]              # old success time still shown


def test_transient_5xx_is_retried_once(client, net):
    net.add("earthquake.usgs.gov", status=503, times=1)
    net.add("earthquake.usgs.gov", json=usgs_payload())
    r = client.post("/api/external/refresh", json={"sources": ["usgs"]}).json()["results"][0]
    assert r["status"] == "ok" and len(net.calls) == 2


def test_firms_without_key_is_not_configured_and_makes_no_request(client, net):
    r = client.post("/api/external/refresh", json={"sources": ["firms"]}).json()["results"][0]
    assert r["status"] == "not_configured" and net.calls == []
    assert next(s for s in client.get("/api/external/status").json()["sources"] if s["source"] == "firms")["configured"] is False


def test_firms_with_key_fetches_documented_url_and_never_returns_the_key(client, net, cfg):
    cfg(firms_map_key="SECRETKEY123", firms_area="68,6,98,36")
    net.add("firms.modaps.eosdis.nasa.gov", text=FIRMS_CSV)
    r = client.post("/api/external/refresh", json={"sources": ["firms"]})
    assert "/api/area/csv/SECRETKEY123/VIIRS_SNPP_NRT/68,6,98,36/2" in net.urls()[0]
    assert "SECRETKEY123" not in r.text and "SECRETKEY123" not in client.get("/api/external/events").text
    assert r.json()["results"][0]["new"] == 2


def test_cache_prevents_repeat_requests(client, net, cfg):
    cfg(manual_refresh_floor_seconds=0)
    net.add("earthquake.usgs.gov", json=usgs_payload())
    client.post("/api/external/refresh", json={"sources": ["usgs"]})
    again = client.post("/api/external/refresh", json={"sources": ["usgs"]}).json()["results"][0]
    assert again["status"] == "cached" and len(net.calls) == 1
    forced = client.post("/api/external/refresh", json={"sources": ["usgs"], "force": True}).json()["results"][0]
    assert forced["status"] == "ok" and len(net.calls) == 2


def test_minimum_interval_applies_even_to_forced_refresh(client, net, cfg):
    cfg(manual_refresh_floor_seconds=60)
    net.add("earthquake.usgs.gov", json=usgs_payload())
    client.post("/api/external/refresh", json={"sources": ["usgs"], "force": True})
    r = client.post("/api/external/refresh", json={"sources": ["usgs"], "force": True}).json()["results"][0]
    assert r["status"] == "cached" and len(net.calls) == 1


def test_list_filters(client, net):
    net.add("earthquake.usgs.gov", json=usgs_payload())
    net.add("gdacs.org", json=gdacs_payload())
    client.post("/api/external/refresh", json={"sources": ["usgs", "gdacs"]})
    get = lambda **p: client.get("/api/external/events", params=p).json()["items"]
    assert {e["source"] for e in get(source="gdacs")} == {"gdacs"}
    assert {e["event_type"] for e in get(event_type="flood")} == {"flood"}
    assert [e["external_id"] for e in get(severity="High", include_duplicates=True)] == ["us1000abc", "FL-99"] or {e["external_id"] for e in get(severity="High", include_duplicates=True)} == {"us1000abc", "FL-99"}
    assert get(since="2026-10-25") == [] and len(get(since="2026-10-24")) >= 2
    assert {e["external_id"] for e in get(west=140, east=142, south=37, north=39)} == {"us1000abc"}
    assert get(west=0, east=1, south=0, north=1) == []


def test_external_events_are_not_disasters_until_an_operator_promotes_them(client, net, make):
    net.add("earthquake.usgs.gov", json=usgs_payload())
    client.post("/api/external/refresh", json={"sources": ["usgs"]})
    assert client.get("/api/disasters").json()["total"] == 0 and client.get("/api/intelligence/priority").json()["items"] == []
    ev = client.get("/api/external/events").json()["items"][0]
    r = client.post(f"/api/external/events/{ev['id']}/promote", json={"people_affected": 10, "notes": "checked with USGS page"})
    assert r.status_code == 201
    d = client.get(f"/api/disasters/{r.json()['disaster_id']}").json()
    assert d["status"] == "Monitoring" and d["origin"] == "external_promoted" and d["location_source"] == "external" and d["location_approximate"]
    assert "UNVERIFIED" in d["description"]
    assert client.post(f"/api/external/events/{ev['id']}/promote", json={}).status_code == 409


def test_refreshing_never_overwrites_a_promoted_or_manual_incident(client, net):
    net.add("earthquake.usgs.gov", json=usgs_payload())
    client.post("/api/external/refresh", json={"sources": ["usgs"], "force": True})
    ev = client.get("/api/external/events").json()["items"][0]
    did = client.post(f"/api/external/events/{ev['id']}/promote", json={"people_affected": 7}).json()["disaster_id"]
    client.patch(f"/api/disasters/{did}", json={"description": "Operator wrote this", "people_affected": 99})
    changed = usgs_payload()
    changed["features"][0]["properties"]["mag"] = 7.9
    net.routes.clear()
    net.add("earthquake.usgs.gov", json=changed)
    client.post("/api/external/refresh", json={"sources": ["usgs"], "force": True})
    d = client.get(f"/api/disasters/{did}").json()
    assert d["description"] == "Operator wrote this" and d["people_affected"] == 99
    assert client.get(f"/api/external/events/{ev['id']}").json()["review_status"] == "Promoted"   # review state preserved


def test_review_and_dismissed_events_are_hidden(client, net):
    net.add("earthquake.usgs.gov", json=usgs_payload())
    client.post("/api/external/refresh", json={"sources": ["usgs"]})
    ev = client.get("/api/external/events").json()["items"][0]
    assert client.post(f"/api/external/events/{ev['id']}/review", json={"status": "Dismissed"}).status_code == 200
    assert len(client.get("/api/external/events").json()["items"]) == 1
    assert len(client.get("/api/external/events", params={"include_dismissed": True}).json()["items"]) == 2


def test_refresh_and_promote_require_operator_credentials(client, net, cfg):
    cfg(operator_api_key="s3cret")
    assert client.post("/api/external/refresh", json={}).status_code == 401
    assert client.post("/api/external/refresh", json={}, headers={"X-Operator-Key": "wrong"}).status_code == 401
    net.add("earthquake.usgs.gov", json=usgs_payload())
    net.add("gdacs.org", json=gdacs_payload())
    ok = client.post("/api/external/refresh", json={"sources": ["usgs"]}, headers={"X-Operator-Key": "s3cret"})
    assert ok.status_code == 200
    assert client.get("/api/external/events").status_code == 200       # reading observations stays public


def test_weather_is_fetched_cached_and_attributed(client, net):
    net.add("api.open-meteo.com", json={"current": {"time": "2026-10-24T06:00", "temperature_2m": 27.5, "wind_speed_10m": 12.0, "precipitation": 0.2, "weather_code": 61, "wind_gusts_10m": 30.0},
                                         "current_units": {"temperature_2m": "°C"}, "daily": {"precipitation_sum": [12.5], "wind_gusts_10m_max": [41.0]}})
    r = client.get("/api/external/weather", params={"lat": 13.08, "lng": 80.27}).json()
    assert r["temperature_c"] == 27.5 and r["summary"] == "Slight rain" and r["today_precipitation_sum_mm"] == 12.5
    assert r["source"] == "open-meteo" and "Open-Meteo" in r["attribution"] and r["retrieved_at"] and r["cached"] is False
    assert client.get("/api/external/weather", params={"lat": 13.08, "lng": 80.27}).json()["cached"] is True and len(net.calls) == 1


def test_weather_failure_is_a_clear_502(client, net):
    net.add("api.open-meteo.com", status=500)
    r = client.get("/api/external/weather", params={"lat": 1, "lng": 2})
    assert r.status_code == 502 and "unavailable" in r.json()["detail"]
    assert client.get("/api/external/weather", params={"lat": 100, "lng": 2}).status_code == 422


def test_fetch_log_rows_recorded(client, net):
    net.add("earthquake.usgs.gov", json=usgs_payload())
    client.post("/api/external/refresh", json={"sources": ["usgs"]})
    from app.database import SessionLocal

    with SessionLocal() as db:
        log = db.query(ExternalFetchLog).one()
        assert log.status == "ok" and log.events_new == 2 and log.finished_at >= log.started_at
        assert db.query(ExternalEvent).count() == 2
