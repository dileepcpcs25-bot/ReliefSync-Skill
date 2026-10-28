from app.constants import STATUS_RULE

from .helpers import CHENNAI

def test_priority_response_carries_status_rule_and_factors(client, make):
    make.disaster(severity="Critical", people_affected=20000)
    r = client.get("/api/intelligence/priority").json()
    assert "disclaimer" not in r and r["status_rule"] == "Resolved incidents are excluded."
    e = r["items"][0]
    assert e["label"].startswith("Estimate") and "status multiplier" in e["method"]
    f = {x["name"]: x for x in e["factors"]}
    assert f["Severity"]["points"] == 55 and f["People affected"]["points"] == 30 and f["Status multiplier"]["points"] == 1.0
    assert "unverified" in f["People affected"]["basis"].lower() and "not independently verified" in f["Severity"]["basis"]
    assert e["score"] == round((f["Severity"]["points"] + f["People affected"]["points"]) * f["Status multiplier"]["points"])


def test_resolved_incidents_are_excluded_from_rankings_but_kept(client, make):
    a, b = make.disaster(location="A"), make.disaster(location="B")
    client.patch(f"/api/disasters/{b['id']}/status", json={"status": "Resolved"})
    ids = [i["disaster"]["id"] for i in client.get("/api/intelligence/priority").json()["items"]]
    assert ids == [a["id"]]
    assert client.get(f"/api/disasters/{b['id']}").status_code == 200                       # record preserved for history
    detail = client.get(f"/api/intelligence/priority/{b['id']}").json()
    assert detail["ranked"] is False and detail["entry"]["score"] == 0 and detail["status_rule"] == STATUS_RULE
    assert client.get(f"/api/intelligence/priority/{a['id']}").json()["ranked"] is True
    assert client.get("/api/intelligence/priority/9999").status_code == 404


def test_recommendations_also_state_the_rule(client, make):
    r = client.get("/api/intelligence/recommendations").json()
    assert "disclaimer" not in r and r["status_rule"] == STATUS_RULE


def test_resolved_incidents_are_excluded_from_active_map_alerts(client, make):
    live = make.disaster(location="Live", **CHENNAI)
    done = make.disaster(location="Done", **CHENNAI)
    client.patch(f"/api/disasters/{done['id']}/status", json={"status": "Resolved"})
    feats = client.get("/api/map/features", params={"layers": "disasters"}).json()
    assert [f["id"] for f in feats["features"]] == [live["id"]]
    assert "disclaimer" not in feats and feats["status_rule"] == STATUS_RULE
    hist = client.get("/api/map/features", params={"layers": "disasters", "include_resolved": True}).json()
    assert {f["id"] for f in hist["features"]} == {live["id"], done["id"]}


def test_map_features_layers_filters_labels_and_privacy(client, make, net):
    d = make.disaster(**CHENNAI, severity="High")
    make.disaster(location="Low one", severity="Low", **CHENNAI)
    make.disaster(location="No coords")
    make.shelter(**CHENNAI)
    make.item(**CHENNAI)
    make.volunteer(latitude=12.92491, longitude=80.10009)
    m = client.get("/api/map/features", params={"layers": "disasters,shelters,inventory,volunteers"}).json()
    kinds = sorted({f["kind"] for f in m["features"]})
    assert kinds == ["disaster", "inventory", "shelter", "volunteer"] and m["missing_coordinates"]["disasters"] == 1
    vol = next(f for f in m["features"] if f["kind"] == "volunteer")
    assert (vol["latitude"], vol["longitude"]) == (12.92, 80.1) and vol["approximate"] is True       # rounded ~1 km
    dis = next(f for f in m["features"] if f["id"] == d["id"])
    assert "Operational record" in dis["label"] and dis["details"]["priority_score"] > 0
    only_high = client.get("/api/map/features", params={"layers": "disasters", "severity": "High"}).json()
    assert [f["id"] for f in only_high["features"]] == [d["id"]]
    box = client.get("/api/map/features", params={"layers": "disasters", "west": 0, "east": 10, "south": 0, "north": 10}).json()
    assert box["count"] == 0


def test_map_hides_volunteers_from_public_when_auth_enabled(client, make, cfg):
    make.volunteer(**CHENNAI)
    cfg(operator_api_key="k")
    pub = client.get("/api/map/features", params={"layers": "volunteers"}).json()
    assert pub["features"] == [] and pub["volunteers_hidden"] is True
    op = client.get("/api/map/features", params={"layers": "volunteers"}, headers={"X-Operator-Key": "k"}).json()
    assert len(op["features"]) == 1 and op["volunteers_hidden"] is False


def test_map_external_layer_is_labelled_unverified(client, make, net):
    from .test_external import usgs_payload

    net.add("earthquake.usgs.gov", json=usgs_payload())
    client.post("/api/external/refresh", json={"sources": ["usgs"]})
    m = client.get("/api/map/features", params={"layers": "external", "source": "usgs"}).json()
    f = m["features"][0]
    assert f["kind"] == "external" and "unverified" in f["label"].lower() and f["severity_label"].startswith("Estimate") and f["retrieved_at"] and f["source"] == "USGS"
