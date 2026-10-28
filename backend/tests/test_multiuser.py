import uuid

from .helpers import CHENNAI, NEAR


def make_account(client, username="operator1", password="Very strong password 2026!"):
    result = client.post("/api/auth/register", json={"username": username, "display_name": "Team Operator", "password": password})
    assert result.status_code == 201, result.text
    return result.json()


def test_password_accounts_hash_password_issue_and_reject_bad_login(client, cfg):
    cfg(app_env="production", operator_api_key="")
    account = make_account(client)
    token = account["token"]
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json() == {"name": "Team Operator", "role": "operator"}
    assert client.post("/api/auth/register", json={"username": "operator1", "display_name": "Duplicate User", "password": "Very strong password 2026!"}).status_code == 409
    assert client.post("/api/auth/login/password", json={"username": "operator1", "password": "wrong"}).status_code == 401
    assert client.post("/api/disasters", json={"disaster_type": "Flood", "location": "Test", "severity": "Low", "people_affected": 1}).status_code == 401
    d = client.post("/api/disasters", headers={"Authorization": f"Bearer {token}"}, json={"disaster_type": "Flood", "location": "Test", "severity": "Low", "people_affected": 1})
    assert d.status_code == 201
    from app.database import SessionLocal
    from app.models import OperatorUser
    db = SessionLocal()
    try:
        record = db.query(OperatorUser).filter_by(username="operator1").one()
        assert record.password_hash != "Very strong password 2026!"
        assert record.password_hash.startswith("pbkdf2_sha256$")
    finally:
        db.close()


def test_account_password_change_requires_current_password(client):
    account = make_account(client, "operator2")
    h = {"Authorization": f"Bearer {account['token']}"}
    assert client.post("/api/auth/change-password", headers=h, json={"current_password": "wrong", "new_password": "Changed strong pass 2026!"}).status_code == 401
    response = client.post("/api/auth/change-password", headers=h, json={"current_password": "Very strong password 2026!", "new_password": "Changed strong pass 2026!"})
    assert response.status_code == 200
    assert client.post("/api/auth/login/password", json={"username": "operator2", "password": "Changed strong pass 2026!"}).status_code == 200
    assert client.post("/api/auth/login/password", json={"username": "operator2", "password": "Very strong password 2026!"}).status_code == 401


def test_operator_can_send_an_in_app_volunteer_alert(client, make):
    account = make_account(client, "dispatcher")
    h = {"Authorization": f"Bearer {account['token']}"}
    d = make.disaster(**CHENNAI, location="Chennai Demo", status="Active")
    make.volunteer(**NEAR, name="Local Responder")
    body = {"audience": "volunteers", "template_key": "volunteer_request", "disaster_id": d["id"], "radius_km": 50,
            "channels": ["in_app"], "instructions": "Report to the demo community hall."}
    campaign = client.post("/api/notifications/campaigns", headers=h, json=body)
    assert campaign.status_code == 201, campaign.text
    cid = campaign.json()["id"]
    preview = client.get(f"/api/notifications/campaigns/{cid}/preview", headers=h)
    assert preview.status_code == 200 and preview.json()["recipient_count"] >= 1
    assert client.post(f"/api/notifications/campaigns/{cid}/approve", headers=h).status_code == 200
    result = client.post(f"/api/notifications/campaigns/{cid}/dispatch", headers=h, json={"confirm": True, "idempotency_key": uuid.uuid4().hex})
    assert result.status_code == 200, result.text
    inbox = client.get("/api/notifications/inbox", headers=h, params={"recipient_type": "volunteer"})
    assert inbox.status_code == 200
    notes = inbox.json()["items"]
    assert any("community hall" in n["body"] for n in notes)
