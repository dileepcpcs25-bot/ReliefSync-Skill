"""API integration tests against an isolated temporary SQLite database."""
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_empty_database_endpoints(client):
    d = client.get("/api/dashboard").json()
    assert d["disasters"]["total"] == 0 and d["shelters"]["available_capacity"] == 0
    assert d["recent_disasters"] == [] and d["top_priorities"] == []
    assert client.get("/api/intelligence/priority").json()["items"] == []
    assert client.get("/api/intelligence/recommendations").json()["items"] == []
    assert client.get("/api/disasters").json() == {"items": [], "total": 0, "limit": 100, "offset": 0}


# ---------- disasters
def test_disaster_crud_and_filters(client, make):
    d = make.disaster()
    make.disaster(disaster_type="Cyclone", location="Puri", severity="Low", people_affected=5)
    assert client.get(f"/api/disasters/{d['id']}").json()["priority_level"] in {"High", "Medium"}
    assert client.get("/api/disasters", params={"severity": "Low"}).json()["total"] == 1
    assert client.get("/api/disasters", params={"q": "chen"}).json()["total"] == 1
    r = client.patch(f"/api/disasters/{d['id']}", json={"people_affected": 20000})
    assert r.json()["people_affected"] == 20000
    assert client.patch(f"/api/disasters/{d['id']}/status", json={"status": "Monitoring"}).json()["status"] == "Monitoring"
    assert client.delete(f"/api/disasters/{d['id']}").status_code == 204
    assert client.get(f"/api/disasters/{d['id']}").status_code == 404


def test_disaster_validation(client):
    base = {"disaster_type": "Flood", "location": "X", "severity": "High", "people_affected": 1}
    assert client.post("/api/disasters", json={**base, "people_affected": -5}).status_code == 422
    assert client.post("/api/disasters", json={**base, "severity": "Extreme"}).status_code == 422
    assert client.post("/api/disasters", json={**base, "location": "  "}).status_code == 422
    assert client.get("/api/disasters/999").status_code == 404
    assert client.get("/api/disasters/abc").status_code == 422


# ---------- volunteers & assignments
def test_assignment_lifecycle_keeps_availability_consistent(client, make):
    v, d = make.volunteer(), make.disaster()
    a = client.post("/api/assignments", json={"volunteer_id": v["id"], "disaster_id": d["id"], "role": "Medic"})
    assert a.status_code == 201
    assert client.get(f"/api/volunteers/{v['id']}").json()["availability"] == "Assigned"
    # conflicting second assignment is refused
    assert client.post("/api/assignments", json={"volunteer_id": v["id"], "disaster_id": d["id"], "role": "Driver"}).status_code == 409
    # cannot manually flip an assigned volunteer
    assert client.patch(f"/api/volunteers/{v['id']}/availability", json={"availability": "Unavailable"}).status_code == 409
    done = client.patch(f"/api/assignments/{a.json()['id']}/status", json={"status": "Completed"})
    assert done.json()["status"] == "Completed"
    assert client.get(f"/api/volunteers/{v['id']}").json()["availability"] == "Available"
    assert client.patch(f"/api/assignments/{a.json()['id']}/status", json={"status": "Cancelled"}).status_code == 409


def test_assignment_rejections(client, make):
    v, d = make.volunteer(), make.disaster()
    assert client.post("/api/assignments", json={"volunteer_id": 999, "disaster_id": d["id"], "role": "x"}).status_code == 404
    client.patch(f"/api/volunteers/{v['id']}/availability", json={"availability": "Unavailable"})
    assert client.post("/api/assignments", json={"volunteer_id": v["id"], "disaster_id": d["id"], "role": "x"}).status_code == 409


def test_resolving_disaster_releases_volunteers_and_blocks_delete(client, make):
    v, d = make.volunteer(), make.disaster()
    client.post("/api/assignments", json={"volunteer_id": v["id"], "disaster_id": d["id"], "role": "Medic"})
    assert client.delete(f"/api/disasters/{d['id']}").status_code == 409  # has assignment history
    client.patch(f"/api/disasters/{d['id']}/status", json={"status": "Resolved"})
    assert client.get(f"/api/volunteers/{v['id']}").json()["availability"] == "Available"
    assert client.get("/api/assignments").json()["items"][0]["status"] == "Completed"


def test_volunteer_phone_validation(client):
    r = client.post("/api/volunteers", json={"name": "A", "phone": "abc", "location": "X"})
    assert r.status_code == 422


# ---------- inventory
def test_inventory_adjust_and_constraints(client, make):
    i = make.item()
    assert client.patch(f"/api/inventory/{i['id']}/adjust", json={"delta": -40}).json()["quantity"] == 60
    assert client.patch(f"/api/inventory/{i['id']}/adjust", json={"delta": -61}).status_code == 409
    assert client.get(f"/api/inventory/{i['id']}").json()["quantity"] == 60
    assert client.patch(f"/api/inventory/{i['id']}/adjust", json={"delta": 0}).status_code == 422
    assert client.post("/api/inventory", json={**i, "quantity": -1}).status_code == 422
    assert client.post("/api/inventory", json={"name": i["name"], "category": "Water", "quantity": 1, "unit": "L", "storage_location": i["storage_location"]}).status_code == 409


def test_low_stock_filter(client, make):
    make.item(name="Low", quantity=5, low_stock_threshold=10)
    make.item(name="Fine", quantity=500, low_stock_threshold=10)
    assert [x["name"] for x in client.get("/api/inventory", params={"low_stock": True}).json()["items"]] == ["Low"]
    assert client.get("/api/dashboard").json()["inventory"]["low_stock"] == 1


# ---------- shelters
def test_shelter_capacity_rules(client):
    ok = client.post("/api/shelters", json={"name": "School", "location": "Chennai", "total_capacity": 100, "current_occupancy": 40})
    s = ok.json()
    assert s["available_capacity"] == 60
    assert client.post("/api/shelters", json={"name": "B", "location": "X", "total_capacity": 0}).status_code == 422
    assert client.post("/api/shelters", json={"name": "B", "location": "X", "total_capacity": 10, "current_occupancy": 11}).status_code == 422
    assert client.patch(f"/api/shelters/{s['id']}/occupancy", json={"current_occupancy": 101}).status_code == 409
    assert client.patch(f"/api/shelters/{s['id']}/occupancy", json={"current_occupancy": -1}).status_code == 422
    assert client.patch(f"/api/shelters/{s['id']}", json={"total_capacity": 30}).status_code == 409
    assert client.patch(f"/api/shelters/{s['id']}/occupancy", json={"current_occupancy": 100}).json()["available_capacity"] == 0


# ---------- allocations & stock accounting
def _alloc(client, d, i, qty):
    return client.post("/api/allocations", json={"disaster_id": d["id"], "item_id": i["id"], "quantity": qty, "destination": "Camp 1"})


def test_allocation_deducts_stock_once_and_rejects_overdraw(client, make):
    d, i = make.disaster(), make.item(quantity=100)
    assert _alloc(client, d, i, 30).status_code == 201
    assert client.get(f"/api/inventory/{i['id']}").json()["quantity"] == 70
    over = _alloc(client, d, i, 71)
    assert over.status_code == 409 and "Insufficient" in over.json()["detail"]
    assert client.get(f"/api/inventory/{i['id']}").json()["quantity"] == 70  # rolled back, unchanged
    assert _alloc(client, d, i, 0).status_code == 422


def test_cancel_restores_stock_exactly_once(client, make):
    d, i = make.disaster(), make.item(quantity=100)
    a = _alloc(client, d, i, 40).json()
    assert client.patch(f"/api/allocations/{a['id']}/status", json={"status": "Cancelled"}).json()["status"] == "Cancelled"
    assert client.get(f"/api/inventory/{i['id']}").json()["quantity"] == 100
    for _ in range(3):  # repeated cancellation must not restore again
        assert client.patch(f"/api/allocations/{a['id']}/status", json={"status": "Cancelled"}).status_code == 409
    assert client.get(f"/api/inventory/{i['id']}").json()["quantity"] == 100


def test_status_transitions(client, make):
    d, i = make.disaster(), make.item()
    a = _alloc(client, d, i, 10).json()
    assert client.patch(f"/api/allocations/{a['id']}/status", json={"status": "In Transit"}).status_code == 200
    assert client.patch(f"/api/allocations/{a['id']}/status", json={"status": "Delivered"}).status_code == 200
    assert client.patch(f"/api/allocations/{a['id']}/status", json={"status": "Cancelled"}).status_code == 409  # delivered goods can't be reversed
    assert client.get(f"/api/inventory/{i['id']}").json()["quantity"] == 90
    assert client.patch(f"/api/allocations/{a['id']}", json={"destination": "Camp 2"}).status_code == 409


def test_allocation_requires_valid_unresolved_disaster_and_protects_history(client, make):
    d, i = make.disaster(), make.item()
    assert client.post("/api/allocations", json={"disaster_id": 999, "item_id": i["id"], "quantity": 1, "destination": "x"}).status_code == 404
    a = _alloc(client, d, i, 5)
    assert a.status_code == 201
    assert client.delete(f"/api/inventory/{i['id']}").status_code == 409
    client.patch(f"/api/disasters/{d['id']}/status", json={"status": "Resolved"})
    assert _alloc(client, d, i, 1).status_code == 409


def test_concurrent_allocations_never_overdraw(client, make):
    d, i = make.disaster(), make.item(quantity=100)

    def attempt(_):
        with TestClient(client.app) as c:
            return c.post("/api/allocations", json={"disaster_id": d["id"], "item_id": i["id"], "quantity": 20, "destination": "Camp"}).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(attempt, range(8)))
    assert codes.count(201) == 5 and codes.count(409) == 3
    assert client.get(f"/api/inventory/{i['id']}").json()["quantity"] == 0


# ---------- intelligence & dashboard
def test_priority_ranking_and_recommendations_do_not_mutate_stock(client, make):
    big = make.disaster(severity="Critical", people_affected=50_000, location="Big")
    make.disaster(severity="Low", people_affected=10, location="Small")
    make.disaster(severity="High", people_affected=5000, location="Done", status="Resolved")
    i = make.item(quantity=1000)
    pr = client.get("/api/intelligence/priority").json()
    assert [e["disaster"]["id"] for e in pr["items"]][0] == big["id"] and len(pr["items"]) == 2
    assert "disclaimer" not in pr and pr["status_rule"] == "Resolved incidents are excluded."
    recs = client.get("/api/intelligence/recommendations").json()["items"]
    assert recs and all(r["suggested_quantity"] <= r["available_quantity"] for r in recs)
    assert sum(r["suggested_quantity"] for r in recs if r["item_id"] == i["id"]) <= 1000
    assert client.get(f"/api/inventory/{i['id']}").json()["quantity"] == 1000


def test_dashboard_reflects_database(client, make):
    d, v, i = make.disaster(severity="Critical", people_affected=100_000), make.volunteer(), make.item()
    make.volunteer(name="Ben", phone="1234567")
    client.post("/api/shelters", json={"name": "S", "location": "X", "total_capacity": 200, "current_occupancy": 50})
    client.post("/api/assignments", json={"volunteer_id": v["id"], "disaster_id": d["id"], "role": "Lead"})
    _alloc(client, d, i, 10)
    s = client.get("/api/dashboard").json()
    assert s["disasters"]["active"] == 1 and s["disasters"]["critical_priority"] == 1
    assert (s["volunteers"]["total"], s["volunteers"]["available"], s["volunteers"]["assigned"]) == (2, 1, 1)
    assert s["assignments"]["active"] == 1 and s["allocations"]["active"] == 1
    assert s["inventory"]["total_units"] == 90 and s["shelters"]["available_capacity"] == 150


def test_data_persists_across_engine_restart(client, make):
    from app.database import engine

    d = make.disaster()
    engine.dispose()  # drop pooled connections, as a process restart would
    with TestClient(client.app) as fresh:
        assert fresh.get(f"/api/disasters/{d['id']}").json()["location"] == "Chennai"
