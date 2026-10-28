from .helpers import CHENNAI, FAR, NEAR


def setup_incident(make, **kw):
    return make.disaster(**CHENNAI, disaster_type="Flood", **kw)


def vol(make, name, pos, **kw):
    return make.volunteer(name=name, **pos, **kw)


# ------------------------------------------------------------------ volunteers
def test_nearby_volunteers_radius_availability_assignment_and_skills(client, make):
    d = setup_incident(make)
    boat = vol(make, "Boat Expert", NEAR, skills="boat, first aid")
    plain = vol(make, "No Skills", NEAR, skills="cooking")
    far = vol(make, "Far Away", FAR, skills="boat")
    off = vol(make, "Unavailable", NEAR, skills="boat")
    client.patch(f"/api/volunteers/{off['id']}/availability", json={"availability": "Unavailable"})
    busy = vol(make, "Busy", NEAR, skills="boat")
    other = make.disaster(location="Elsewhere", **CHENNAI)
    assert client.post("/api/assignments", json={"volunteer_id": busy["id"], "disaster_id": other["id"], "role": "x"}).status_code == 201
    nopos = make.volunteer(name="Unknown Position")

    r = client.get(f"/api/disasters/{d['id']}/nearby-volunteers", params={"radius_km": 50}).json()
    names = [c["name"] for c in r["candidates"]]
    assert names == ["Boat Expert", "No Skills"]                       # ranked by suitability, then distance
    assert r["candidates"][0]["score"] > r["candidates"][1]["score"]
    assert 15 < r["candidates"][0]["distance_km"] < 35
    assert "boat" in r["candidates"][0]["matched_skills"] and "straight line" in r["candidates"][0]["reason"]
    assert r["candidates"][0]["suggested_role"] == "Water rescue support"
    ex = r["excluded"]
    assert ex["outside radius"] == 1 and ex["position unknown"] == 1
    assert ex["not available (Assigned)"] == 1 and ex["not available (Unavailable)"] == 1
    assert boat["id"] == r["candidates"][0]["volunteer_id"] and plain and far and nopos


def test_active_assignment_conflict_is_excluded_even_if_availability_flag_is_stale(client, make):
    from app.database import SessionLocal
    from app.models import Volunteer

    d = setup_incident(make)
    v = vol(make, "Stale", NEAR, skills="boat")
    other = make.disaster(location="Elsewhere", **CHENNAI)
    client.post("/api/assignments", json={"volunteer_id": v["id"], "disaster_id": other["id"], "role": "x"})
    with SessionLocal() as db:                      # simulate inconsistent data: flag says Available, assignment still Active
        db.get(Volunteer, v["id"]).availability = "Available"
        db.commit()
    r = client.get(f"/api/disasters/{d['id']}/nearby-volunteers").json()
    assert r["candidates"] == [] and r["excluded"] == {"already on an active assignment": 1}


def test_nearby_volunteers_never_expose_phone_or_coordinates(client, make):
    d = setup_incident(make)
    vol(make, "Asha", NEAR, skills="first aid")
    text = client.get(f"/api/disasters/{d['id']}/nearby-volunteers").text
    assert "98765" not in text and "phone" not in text and "latitude" not in text and "12.9249" not in text


def test_skill_filter_and_larger_radius(client, make):
    d = setup_incident(make)
    vol(make, "Boat", NEAR, skills="boat")
    vol(make, "Cook", NEAR, skills="cooking")
    vol(make, "FarBoat", FAR, skills="boat")
    r = client.get(f"/api/disasters/{d['id']}/nearby-volunteers", params={"radius_km": 400, "skills": "boat", "require_skill_match": True}).json()
    assert {c["name"] for c in r["candidates"]} == {"Boat", "FarBoat"} and r["excluded"]["no matching skills"] == 1
    assert r["candidates"][0]["name"] == "Boat"                         # closer wins at equal suitability


def test_nearby_requires_active_incident_with_position(client, make):
    no_pos = make.disaster()
    assert client.get(f"/api/disasters/{no_pos['id']}/nearby-volunteers").status_code == 409
    resolved = setup_incident(make)
    client.patch(f"/api/disasters/{resolved['id']}/status", json={"status": "Resolved"})
    assert client.get(f"/api/disasters/{resolved['id']}/nearby-volunteers").status_code == 409
    assert client.get(f"/api/disasters/{resolved['id']}/nearby-shelters").status_code == 409
    assert client.get("/api/disasters/9999/nearby-volunteers").status_code == 404
    assert client.get(f"/api/disasters/{no_pos['id']}/nearby-volunteers", params={"radius_km": 99999}).status_code in (409, 422)


def test_operator_approval_creates_assignment_and_rechecks(client, make):
    d = setup_incident(make)
    v = vol(make, "Asha", NEAR, skills="first aid")
    body = {"volunteer_id": v["id"], "role": "First-aid support", "radius_km": 50}
    assert client.post(f"/api/disasters/{d['id']}/nearby-volunteers/approve-assignment", json=body).status_code == 422   # no confirm
    ok = client.post(f"/api/disasters/{d['id']}/nearby-volunteers/approve-assignment", json={**body, "confirm": True})
    assert ok.status_code == 201 and ok.json()["status"] == "Active"
    assert client.get(f"/api/volunteers/{v['id']}").json()["availability"] == "Assigned"
    # second approval: availability is re-checked, so no conflicting assignment is created
    again = client.post(f"/api/disasters/{d['id']}/nearby-volunteers/approve-assignment", json={**body, "confirm": True})
    assert again.status_code == 409
    assert client.get("/api/assignments", params={"volunteer_id": v["id"]}).json()["total"] == 1


def test_approval_refuses_volunteer_who_moved_out_of_radius_or_unavailable(client, make):
    d = setup_incident(make)
    far = vol(make, "Far", FAR)
    r = client.post(f"/api/disasters/{d['id']}/nearby-volunteers/approve-assignment", json={"volunteer_id": far["id"], "role": "x", "radius_km": 50, "confirm": True})
    assert r.status_code == 409


def test_nearby_volunteers_need_operator_when_auth_enabled(client, make, cfg):
    d = setup_incident(make)
    vol(make, "Asha", NEAR)
    cfg(operator_api_key="k")
    assert client.get(f"/api/disasters/{d['id']}/nearby-volunteers").status_code == 401
    assert client.get(f"/api/disasters/{d['id']}/nearby-volunteers", headers={"X-Operator-Key": "k"}).status_code == 200


def test_public_volunteer_list_masks_phone_and_hides_coordinates_when_auth_enabled(client, make, cfg):
    make.volunteer(name="Asha", **NEAR)
    cfg(operator_api_key="k")
    public = client.get("/api/volunteers").json()["items"][0]
    assert "98765" not in public["phone"] and public["phone"].endswith("10") and public["latitude"] is None
    operator = client.get("/api/volunteers", headers={"X-Operator-Key": "k"}).json()["items"][0]
    assert operator["phone"] == "+91 98765 43210" and operator["latitude"] == NEAR["latitude"]


def test_production_without_key_refuses_operator_actions(client, cfg):
    cfg(app_env="production", operator_api_key="")
    r = client.post("/api/external/refresh", json={})
    assert r.status_code == 401 and "sign in" in r.json()["detail"].lower()


# ------------------------------------------------------------------ shelters
def test_nearby_shelters_capacity_distance_and_labels(client, make):
    d = setup_incident(make)
    make.shelter(name="Near Open", **NEAR, total_capacity=100, current_occupancy=40)
    make.shelter(name="Near Full", **NEAR, total_capacity=50, current_occupancy=50)
    make.shelter(name="Far", **FAR)
    make.shelter(name="No Position")
    r = client.get(f"/api/disasters/{d['id']}/nearby-shelters", params={"radius_km": 50}).json()
    assert [s["name"] for s in r["items"]] == ["Near Open"]
    s = r["items"][0]
    assert s["available_capacity"] == 60 and s["total_capacity"] == 100 and s["current_occupancy"] == 40
    assert "not travel distance" in s["distance_label"] and s["last_updated"] and s["directions_url"].startswith("https://www.openstreetmap.org/directions")
    assert r["excluded"] == {"no available capacity": 1, "outside radius": 1, "position unknown": 1}
    full = client.get(f"/api/disasters/{d['id']}/nearby-shelters", params={"radius_km": 50, "include_full": True}).json()
    assert {x["name"] for x in full["items"]} == {"Near Open", "Near Full"}


def test_nearby_shelters_with_route_estimates(client, make, net):
    d = setup_incident(make)
    make.shelter(name="Camp", **NEAR)
    net.add("router.project-osrm.org", json={"code": "Ok", "routes": [{"distance": 31500.0, "duration": 2400.0, "geometry": {"type": "LineString", "coordinates": [[80.27, 13.08], [80.10, 12.92]]}}]})
    s = client.get(f"/api/disasters/{d['id']}/nearby-shelters", params={"with_routes": True}).json()["items"][0]
    assert s["route"]["distance_km"] == 31.5 and s["route"]["duration_min"] == 40.0 and "Estimate" in s["route"]["label"]
    assert s["route"]["geometry"][0] == [13.08, 80.27] and s["straight_line_km"] < s["route"]["distance_km"]
    assert "/route/v1/driving/80.270700,13.082700;80.100000,12.924900" in net.urls()[0]       # lon,lat order per OSRM docs


def test_route_failure_does_not_hide_the_shelter(client, make, net):
    d = setup_incident(make)
    make.shelter(name="Camp", **NEAR)
    net.add("router.project-osrm.org", status=500)
    s = client.get(f"/api/disasters/{d['id']}/nearby-shelters", params={"with_routes": True}).json()["items"][0]
    assert s["route"] is None and "HTTP 500" in s["route_error"] and s["straight_line_km"] > 0


def test_route_endpoint_and_caching(client, net):
    net.add("router.project-osrm.org", json={"code": "Ok", "routes": [{"distance": 1000, "duration": 120}]})
    p = {"from_lat": 13, "from_lng": 80, "to_lat": 13.01, "to_lng": 80.01, "geometry": False}
    first, second = client.get("/api/geo/route", params=p).json(), client.get("/api/geo/route", params=p).json()
    assert first["distance_km"] == 1.0 and first["cached"] is False and second["cached"] is True and len(net.calls) == 1
    net.routes.clear()
    net.add("router.project-osrm.org", json={"code": "NoRoute", "routes": []})
    assert client.get("/api/geo/route", params={**p, "to_lat": 1.0}).status_code == 502


def test_routing_can_be_disabled(client, cfg):
    cfg(routing_enabled=False)
    assert client.get("/api/geo/route", params={"from_lat": 1, "from_lng": 1, "to_lat": 2, "to_lng": 2}).status_code == 502


# ------------------------------------------------------------------ geocoding
NOMINATIM_ONE = [{"lat": "13.0836939", "lon": "80.270186", "display_name": "Chennai, Tamil Nadu, India", "importance": 0.74, "type": "city", "osm_type": "relation", "osm_id": 1, "address": {"country": "India"}}]
NOMINATIM_AMBIGUOUS = [
    {"lat": "39.78", "lon": "-89.65", "display_name": "Springfield, Illinois, USA", "importance": 0.62, "type": "city"},
    {"lat": "42.10", "lon": "-72.59", "display_name": "Springfield, Massachusetts, USA", "importance": 0.60, "type": "city"},
]


def test_geocode_returns_candidates_source_and_caches(client, net):
    net.add("nominatim.openstreetmap.org", json=NOMINATIM_ONE)
    r = client.get("/api/geo/geocode", params={"q": "Chennai"}).json()
    assert r["candidates"][0]["latitude"] == 13.0836939 and r["ambiguous"] is False and r["source"] == "nominatim"
    assert "OpenStreetMap" in r["attribution"] and r["cached"] is False
    assert client.get("/api/geo/geocode", params={"q": "  chennai "}).json()["cached"] is True
    assert len(net.calls) == 1
    assert "format=jsonv2" in net.urls()[0] and net.calls[0].headers["user-agent"]


def test_ambiguous_geocode_is_flagged_not_assumed(client, net):
    net.add("nominatim.openstreetmap.org", json=NOMINATIM_AMBIGUOUS)
    r = client.get("/api/geo/geocode", params={"q": "Springfield"}).json()
    assert r["ambiguous"] is True and len(r["candidates"]) == 2


def test_geocode_failure_and_validation(client, net):
    net.add("nominatim.openstreetmap.org", status=429)
    assert client.get("/api/geo/geocode", params={"q": "Chennai"}).status_code == 502
    assert client.get("/api/geo/geocode", params={"q": "ab"}).status_code == 422


def test_geocode_missing_fills_only_unambiguous_and_never_overwrites(client, make, net):
    keep = make.disaster(location="Chennai", **CHENNAI)                       # already has coordinates: must not change
    a = make.disaster(location="Chennai Central")
    b = make.disaster(location="Springfield")
    c = make.disaster(location="Nowhereville")
    net.add("q=Chennai+Central", json=NOMINATIM_ONE)
    net.add("q=Springfield", json=NOMINATIM_AMBIGUOUS)
    net.add("q=Nowhereville", json=[])
    r = client.post("/api/geo/geocode-missing", json={"entity": "disasters", "limit": 10}).json()
    assert [x["id"] for x in r["applied"]] == [a["id"]] and [x["id"] for x in r["ambiguous"]] == [b["id"]] and [x["id"] for x in r["not_found"]] == [c["id"]]
    got = client.get(f"/api/disasters/{a['id']}").json()
    assert got["location_source"] == "geocoded" and got["location_approximate"] is True and got["latitude"] == 13.0836939
    assert client.get(f"/api/disasters/{b['id']}").json()["latitude"] is None            # ambiguous: left alone
    assert client.get(f"/api/disasters/{keep['id']}").json()["latitude"] == CHENNAI["latitude"]
    assert not any("q=Chennai&" in u or u.endswith("q=Chennai") for u in net.urls())    # the record that had coordinates was never queried
