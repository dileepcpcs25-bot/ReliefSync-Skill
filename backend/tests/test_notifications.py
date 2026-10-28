import re
import uuid

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import NotificationDelivery
from app.services.notification_templates import NEUTRAL_PUBLIC_LINE, TEMPLATES, render_base

from .helpers import CHENNAI, FAR, NEAR

LIVE = dict(notifications_mode="live", twilio_account_sid="ACtest", twilio_auth_token="tok", twilio_from_number="+15550001111")


# ------------------------------------------------------------------ helpers
def incident(make, **kw):
    return make.disaster(**CHENNAI, disaster_type="Flood", location="Chennai", **kw)


def new_campaign(client, disaster, audience="volunteers", template="volunteer_request", channels=("in_app",), **kw):
    r = client.post("/api/notifications/campaigns", json={"audience": audience, "template_key": template, "disaster_id": disaster["id"], "radius_km": 50,
                                                          "channels": list(channels), **kw})
    assert r.status_code == 201, r.text
    return r.json()


def approve(client, c):
    r = client.post(f"/api/notifications/campaigns/{c['id']}/approve")
    assert r.status_code == 200, r.text
    return r.json()


def dispatch(client, c, key=None, confirm=True):
    return client.post(f"/api/notifications/campaigns/{c['id']}/dispatch", json={"confirm": confirm, "idempotency_key": key or uuid.uuid4().hex})


def deliveries(client, c, **params):
    return client.get(f"/api/notifications/campaigns/{c['id']}/deliveries", params=params).json()


def consenting_volunteer(make, client, name="Asha", pos=NEAR, **kw):
    v = make.volunteer(name=name, **pos, sms_opt_in=True, **kw)
    return v


# ------------------------------------------------------------------ drafting / validation
def test_draft_validation(client, make):
    d = incident(make)
    base = {"audience": "volunteers", "template_key": "volunteer_request", "disaster_id": d["id"], "radius_km": 50, "channels": ["in_app"]}
    post = lambda **kw: client.post("/api/notifications/campaigns", json={**base, **kw})
    assert post(template_key="nope").status_code == 422
    assert post(template_key="shelter_preparedness").status_code == 422                  # template/audience mismatch
    assert post(channels=["email"]).status_code == 422                                   # volunteers have no email channel
    assert post(channels=[]).status_code == 422
    assert post(radius_km=0).status_code == 422 and post(radius_km=9999).status_code == 422
    assert post(disaster_id=9999).status_code == 404
    assert post(template_key="all_clear").status_code == 409                             # incident not resolved yet
    nopos = make.disaster()
    assert post(disaster_id=nopos["id"]).status_code == 409
    assert post().status_code == 201


def test_resolved_incidents_cannot_have_active_campaigns(client, make):
    d = incident(make)
    client.patch(f"/api/disasters/{d['id']}/status", json={"status": "Resolved"})
    r = client.post("/api/notifications/campaigns", json={"audience": "volunteers", "template_key": "volunteer_request", "disaster_id": d["id"], "channels": ["in_app"]})
    assert r.status_code == 409 and "Resolved incidents are excluded" in r.json()["detail"]
    client.patch(f"/api/disasters/{d['id']}/status", json={"status": "Active"})        # record itself is untouched
    assert client.get(f"/api/disasters/{d['id']}").json()["status"] == "Active"


def test_campaign_approved_then_incident_resolved_cannot_dispatch(client, make):
    d = incident(make)
    make.volunteer(name="A", **NEAR)
    c = approve(client, new_campaign(client, d))
    client.patch(f"/api/disasters/{d['id']}/status", json={"status": "Resolved"})
    r = dispatch(client, c)
    assert r.status_code == 409 and "Resolved incidents are excluded" in r.json()["detail"]
    assert deliveries(client, c)["total"] == 0


# ------------------------------------------------------------------ preview
def test_preview_shows_message_recipients_exclusions_and_no_private_data(client, make):
    d = incident(make, people_affected=1200)
    make.volunteer(name="Near Skilled", **NEAR, skills="boat")
    make.volunteer(name="Too Far", **FAR)
    c = new_campaign(client, d, required_skills="boat")
    p = client.get(f"/api/notifications/campaigns/{c['id']}/preview").json()
    assert p["recipient_count"] == 1 and p["recipients"][0]["label"].endswith("Near Skilled") and p["recipients"][0]["distance_km"] > 10
    assert p["channels"]["in_app"]["eligible"] == 1 and "No cost" in p["channels"]["in_app"]["cost"]
    assert p["mode"] == "development" and any("DEVELOPMENT MODE" in w for w in p["warnings"])
    assert "not independently verified" in p["body"] and "unverified estimate" in p["body"] and "1,200" in p["body"]
    assert "Approximate distance from the incident" in p["sample_personalised_body"]
    assert p["target_area"] == {"latitude": CHENNAI["latitude"], "longitude": CHENNAI["longitude"], "radius_km": 50} and p["requires_approval"] is True
    assert p["excluded"]["outside radius"] == 1
    text = str(p)
    assert "98765" not in text and "12.9249" not in text
    assert "decision_support_note" not in p


def test_preview_cost_information_only_when_configured(client, make, cfg):
    d = incident(make)
    consenting_volunteer(make, client)
    c = new_campaign(client, d, channels=("in_app", "sms"))
    assert "not configured" in client.get(f"/api/notifications/campaigns/{c['id']}/preview").json()["channels"]["sms"]["cost"]
    cfg(sms_cost_per_message="0.0083 USD")
    assert client.get(f"/api/notifications/campaigns/{c['id']}/preview").json()["channels"]["sms"]["cost"].startswith("1 x 0.0083 USD")


def test_edit_draft_changes_preview_but_approved_campaigns_are_locked(client, make):
    d = incident(make)
    make.volunteer(name="A", **NEAR)
    c = new_campaign(client, d)
    r = client.patch(f"/api/notifications/campaigns/{c['id']}", json={"instructions": "Meet at the school gate."})
    assert r.status_code == 200 and "school gate" in client.get(f"/api/notifications/campaigns/{c['id']}/preview").json()["body"]
    assert client.patch(f"/api/notifications/campaigns/{c['id']}", json={"channels": ["email"]}).status_code == 422
    approve(client, c)
    assert client.patch(f"/api/notifications/campaigns/{c['id']}", json={"instructions": "x"}).status_code == 409


# ------------------------------------------------------------------ approval & dispatch gates
def test_nothing_can_be_dispatched_without_approval_and_confirmation(client, make):
    d = incident(make)
    make.volunteer(name="A", **NEAR)
    c = new_campaign(client, d)
    assert dispatch(client, c).status_code == 409                                        # Draft
    approve(client, c)
    assert dispatch(client, c, confirm=False).status_code == 422                          # no explicit confirmation
    assert deliveries(client, c)["total"] == 0
    assert dispatch(client, c).status_code == 200


def test_cannot_approve_when_there_are_no_eligible_recipients(client, make):
    d = incident(make)
    c = new_campaign(client, d)
    r = client.post(f"/api/notifications/campaigns/{c['id']}/approve")
    assert r.status_code == 409 and "no eligible recipients" in r.json()["detail"].lower()


def test_content_changed_after_approval_blocks_dispatch(client, make):
    d = incident(make)
    make.volunteer(name="A", **NEAR)
    c = approve(client, new_campaign(client, d))
    client.patch(f"/api/disasters/{d['id']}", json={"location": "Somewhere else entirely"})      # message text depends on it
    r = dispatch(client, c)
    assert r.status_code == 409 and "changed after approval" in r.json()["detail"]


# ------------------------------------------------------------------ in-app end to end
def test_in_app_notifications_end_to_end_with_audit_trail(client, make):
    d = incident(make)
    v = make.volunteer(name="Asha", **NEAR, skills="first aid")
    make.volunteer(name="Far", **FAR)
    c = new_campaign(client, d, instructions="Report to the community hall.")
    approve(client, c)
    r = dispatch(client, c).json()
    assert r["status"] == "Dispatched" and r["deliveries"] == {"recorded_in_app": 1} and r["replayed"] is False
    dv = deliveries(client, c)["items"][0]
    assert dv["status"] == "recorded_in_app" and dv["provider"] == "in-app" and "not an SMS or email" in dv["detail"]
    inbox = client.get("/api/notifications/inbox", params={"recipient_type": "volunteer", "recipient_id": v["id"]}).json()["items"]
    assert len(inbox) == 1 and "community hall" in inbox[0]["body"] and "In-app notification" in inbox[0]["label"] and inbox[0]["read_at"] is None
    assert client.post(f"/api/notifications/inbox/{inbox[0]['id']}/read").json()["read_at"]
    assert client.get("/api/notifications/inbox", params={"unread_only": True}).json()["items"] == []
    full = client.get(f"/api/notifications/campaigns/{c['id']}").json()
    assert full["status"] == "Dispatched" and full["approved_by"] and full["dispatched_by"] and full["mode_at_dispatch"] == "development"
    actions = [a["action"] for a in client.get("/api/notifications/audit", params={"entity_type": "campaign", "entity_id": c["id"]}).json()["items"]]
    assert {"campaign.drafted", "campaign.approved", "campaign.dispatch_started", "campaign.dispatch_finished"} <= set(actions)
    assert "98765" not in str(client.get("/api/notifications/audit").json())                 # audit never stores contact details


def test_campaigns_persist_and_are_listed_with_history(client, make):
    d = incident(make)
    make.volunteer(name="A", **NEAR)
    c = new_campaign(client, d)
    approve(client, c)
    dispatch(client, c)
    listing = client.get("/api/notifications/campaigns", params={"status": "Dispatched"}).json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == c["id"] and listing["items"][0]["disaster_label"].startswith("Flood")
    assert client.get("/api/notifications/campaigns", params={"status": "Draft"}).json()["total"] == 0


# ------------------------------------------------------------------ development mode is safe
def test_development_mode_never_contacts_anyone(client, make, net, cfg):
    cfg(**{**LIVE, "notifications_mode": "development"})               # credentials present, but development mode is on
    d = incident(make)
    consenting_volunteer(make, client)
    c = approve(client, new_campaign(client, d, channels=("in_app", "sms")))
    r = dispatch(client, c).json()
    assert net.calls == []                                               # no outbound request of any kind
    assert r["deliveries"] == {"recorded_in_app": 1, "simulated": 1} and r["status"] == "Dispatched"
    sms = deliveries(client, c, status="simulated")["items"][0]
    assert sms["provider"] == "development-simulator" and "nothing was sent" in sms["detail"].lower()
    assert deliveries(client, c)["status_meaning"]["simulated"].startswith("Development mode")
    assert not any(x["status"] == "accepted_by_provider" for x in deliveries(client, c)["items"])


def test_default_configuration_is_development_mode():
    from app.config import Settings

    assert Settings().notifications_mode == "development" and Settings().live_mode is False


# ------------------------------------------------------------------ consent & eligibility
def test_sms_requires_recorded_consent_and_valid_number(client, make):
    d = incident(make)
    make.volunteer(name="No Consent", **NEAR)                                            # sms_opt_in defaults to False
    make.volunteer(name="Bad Number", **NEAR, phone="12345 678", sms_opt_in=True)
    make.volunteer(name="Good", **NEAR, phone="+91 98765 43211", sms_opt_in=True)
    c = new_campaign(client, d, channels=("sms",))
    p = client.get(f"/api/notifications/campaigns/{c['id']}/preview").json()
    assert p["channels"]["sms"]["eligible"] == 1 and p["recipients"][0]["label"].endswith("Good")
    assert p["excluded"]["no SMS consent recorded"] == 1 and p["excluded"]["phone number is not in international (+country code) format"] == 1
    assert p["recipients"][0]["address_masked"].endswith("11") and "9876543211" not in str(p)


def test_availability_and_conflicts_are_rechecked_at_dispatch(client, make):
    d = incident(make)
    a, b = make.volunteer(name="A", **NEAR), make.volunteer(name="B", **NEAR)
    c = approve(client, new_campaign(client, d))
    other = make.disaster(location="Other", **CHENNAI)
    client.post("/api/assignments", json={"volunteer_id": a["id"], "disaster_id": other["id"], "role": "x"})   # A becomes busy after approval
    client.patch(f"/api/volunteers/{b['id']}/availability", json={"availability": "Unavailable"})              # B becomes unavailable
    r = dispatch(client, c)
    assert r.status_code == 409 and "no eligible recipients" in r.json()["detail"].lower()


# ------------------------------------------------------------------ duplicates & cooldown
def test_duplicate_dispatch_is_prevented(client, make):
    d = incident(make)
    make.volunteer(name="A", **NEAR)
    c = approve(client, new_campaign(client, d))
    key = "dispatch-key-0001"
    first = dispatch(client, c, key).json()
    replay = dispatch(client, c, key).json()                                              # double click / network retry
    assert replay["replayed"] is True and replay["deliveries"] == first["deliveries"]
    assert dispatch(client, c, "a-different-key-2").status_code == 409                    # a second, different attempt is refused
    assert deliveries(client, c)["total"] == 1
    inbox = client.get("/api/notifications/inbox").json()
    assert inbox["total"] == 1


def test_database_forbids_duplicate_delivery_rows(client, make):
    d = incident(make)
    make.volunteer(name="A", **NEAR)
    c = approve(client, new_campaign(client, d))
    dispatch(client, c)
    with SessionLocal() as db:
        db.add(NotificationDelivery(campaign_id=c["id"], recipient_type="volunteer", recipient_id=1, channel="in_app"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_cooldown_blocks_repeat_notifications_to_same_recipient(client, make, cfg):
    d = incident(make)
    make.volunteer(name="A", **NEAR)
    first = approve(client, new_campaign(client, d))
    dispatch(client, first)
    second = new_campaign(client, d, template="incident_update")
    p = client.get(f"/api/notifications/campaigns/{second['id']}/preview").json()
    assert p["recipient_count"] == 0 and any("cooldown" in k for k in p["excluded"])
    assert client.post(f"/api/notifications/campaigns/{second['id']}/approve").status_code == 409
    cfg(notification_cooldown_minutes=0)                                                  # configurable
    assert client.get(f"/api/notifications/campaigns/{second['id']}/preview").json()["recipient_count"] == 1


def test_cancel_draft_and_approved_only(client, make):
    d = incident(make)
    make.volunteer(name="A", **NEAR)
    c = new_campaign(client, d)
    assert client.post(f"/api/notifications/campaigns/{c['id']}/cancel").json()["status"] == "Cancelled"
    assert client.post(f"/api/notifications/campaigns/{c['id']}/cancel").status_code == 409
    assert client.post(f"/api/notifications/campaigns/{c['id']}/approve").status_code == 409


# ------------------------------------------------------------------ live mode: honest delivery status
def test_live_mode_sms_is_reported_as_accepted_not_delivered(client, make, net, cfg):
    cfg(**LIVE)
    d = incident(make)
    consenting_volunteer(make, client, phone="+91 98765 43210")
    net.add("api.twilio.com/2010-04-01/Accounts/ACtest/Messages.json", status=201, json={"sid": "SM123", "status": "queued"})
    c = approve(client, new_campaign(client, d, channels=("sms",)))
    assert dispatch(client, c).json()["deliveries"] == {"accepted_by_provider": 1}
    dv = deliveries(client, c)["items"][0]
    assert dv["status"] == "accepted_by_provider" and dv["provider_message_id"] == "SM123" and "not confirmed" in dv["detail"]
    assert all(x["status"] != "delivered" for x in deliveries(client, c)["items"])
    req = net.calls[0]
    body = req.content.decode()
    assert req.headers["authorization"].startswith("Basic ") and "To=%2B919876543210" in body and "From=%2B15550001111" in body
    assert "Flood" in body and "tok" not in body
    assert len(net.calls) == 1


def test_provider_failure_is_recorded_and_retry_never_duplicates(client, make, net, cfg):
    cfg(**LIVE)
    d = incident(make)
    make.volunteer(name="A", **NEAR, phone="+91 98765 43210", sms_opt_in=True)
    make.volunteer(name="B", **NEAR, phone="+91 98765 43211", sms_opt_in=True)
    net.add("api.twilio.com", status=500, times=1)                                          # first send fails
    net.add("api.twilio.com", status=201, json={"sid": "SMok", "status": "queued"})
    c = approve(client, new_campaign(client, d, channels=("in_app", "sms")))
    r = dispatch(client, c).json()
    assert r["status"] == "Partially Failed" and r["deliveries"] == {"recorded_in_app": 2, "failed": 1, "accepted_by_provider": 1}
    failed = deliveries(client, c, status="failed")["items"][0]
    assert "Provider error" in failed["detail"] and failed["attempts"] == 1
    sends_before = len(net.calls)
    retry = client.post(f"/api/notifications/campaigns/{c['id']}/retry-failed", json={"confirm": True}).json()
    assert retry["status"] == "Dispatched" and retry["deliveries"] == {"recorded_in_app": 2, "accepted_by_provider": 2}
    assert len(net.calls) == sends_before + 1                                                # only the failed one was re-sent
    assert deliveries(client, c)["total"] == 4
    assert sorted(x["attempts"] for x in deliveries(client, c, status="accepted_by_provider")["items"]) == [1, 2]
    assert client.post(f"/api/notifications/campaigns/{c['id']}/retry-failed", json={"confirm": True}).status_code == 409   # nothing left to retry
    assert client.get("/api/notifications/inbox").json()["total"] == 2                         # no duplicate in-app records either


def test_retry_needs_confirmation_and_respects_max_attempts(client, make, net, cfg):
    cfg(**LIVE, notification_max_attempts=2)
    d = incident(make)
    consenting_volunteer(make, client)
    net.add("api.twilio.com", status=500)
    c = approve(client, new_campaign(client, d, channels=("sms",)))
    assert dispatch(client, c).json()["status"] == "Failed"
    assert client.post(f"/api/notifications/campaigns/{c['id']}/retry-failed", json={"confirm": False}).status_code == 422
    assert client.post(f"/api/notifications/campaigns/{c['id']}/retry-failed", json={"confirm": True}).json()["status"] == "Failed"
    assert client.post(f"/api/notifications/campaigns/{c['id']}/retry-failed", json={"confirm": True}).status_code == 409    # 2 attempts used


def test_timeout_and_network_errors_become_failed_deliveries(client, make, net, cfg):
    cfg(**LIVE)
    d = incident(make)
    consenting_volunteer(make, client)
    net.add("api.twilio.com", exc=httpx.ConnectTimeout("t"))
    c = approve(client, new_campaign(client, d, channels=("sms",)))
    dispatch(client, c)
    dv = deliveries(client, c)["items"][0]
    assert dv["status"] == "failed" and "Timed out" in dv["detail"]


def test_live_mode_without_credentials_fails_honestly_and_never_pretends(client, make, net, cfg):
    cfg(notifications_mode="live")                                                          # no Twilio credentials
    d = incident(make)
    consenting_volunteer(make, client)
    c = approve(client, new_campaign(client, d, channels=("in_app", "sms")))
    p = client.get(f"/api/notifications/campaigns/{c['id']}/preview").json()
    assert any("not configured" in w for w in p["warnings"]) and p["channels"]["sms"]["will_contact_real_people"] is False
    r = dispatch(client, c).json()
    assert r["status"] == "Partially Failed" and r["deliveries"] == {"recorded_in_app": 1, "failed": 1}
    assert "not configured" in deliveries(client, c, status="failed")["items"][0]["detail"] and net.calls == []


def test_status_endpoint_reports_channels_without_secrets(client, cfg):
    cfg(**LIVE)
    s = client.get("/api/notifications/status").json()
    assert s["mode"] == "live" and s["sms"]["available"] is True and s["email"]["available"] is False and s["browser_push"]["available"] is False
    assert "tok" not in str(s) and "ACtest" not in str(s)


# ------------------------------------------------------------------ shelters
def test_shelter_notification_does_not_change_recorded_availability(client, make):
    d = incident(make)
    near = make.shelter(name="Hall", **NEAR, total_capacity=100, current_occupancy=90)
    make.shelter(name="Far", **FAR)
    c = approve(client, new_campaign(client, d, audience="shelters", template="shelter_preparedness"))
    r = dispatch(client, c).json()
    assert r["deliveries"] == {"recorded_in_app": 1}
    note = client.get("/api/notifications/inbox", params={"recipient_type": "shelter", "recipient_id": near["id"]}).json()["items"][0]
    assert "10 of 100 places free" in note["body"] and "does not change that record" in note["body"] and "confirm your shelter's current status" in note["body"]
    assert f"#/map?disaster={d['id']}" in note["body"]
    after = client.get(f"/api/shelters/{near['id']}").json()
    assert (after["current_occupancy"], after["total_capacity"], after["available_capacity"]) == (90, 100, 10)


# ------------------------------------------------------------------ residents
def sub(client, **kw):
    body = {"channel": "email", "contact": "resident@example.com", "area_label": "Central Chennai", "latitude": 13.0827, "longitude": 80.2707, "radius_km": 25, "consent": True, **kw}
    return client.post("/api/subscriptions", json=body)


def active_sub(client, **kw):
    r = sub(client, **kw)
    assert r.status_code == 202, r.text
    assert client.post("/api/subscriptions/confirm", json={"token": r.json()["dev_confirm_token"]}).status_code == 200
    return r


def test_subscription_requires_consent_and_valid_contact(client):
    assert sub(client, consent=False).status_code == 422
    assert sub(client, contact="not-an-email").status_code == 422
    assert sub(client, channel="sms", contact="98765").status_code == 422
    assert sub(client, latitude=95).status_code == 422
    assert sub(client, radius_km=0).status_code == 422


def test_subscription_stores_coarse_area_masks_contacts_and_needs_confirmation(client, net):
    r = sub(client, latitude=13.08271, longitude=80.27069).json()
    assert r["confirmation"] == "simulated" and net.calls == []                          # dev mode: simulated, nothing sent
    listing = client.get("/api/subscriptions").json()
    s = listing["items"][0]
    assert (s["area_latitude"], s["area_longitude"]) == (13.1, 80.3) and s["status"] == "Pending"
    assert s["contact_masked"] == "r***@example.com" and "resident@example.com" not in str(listing) and listing["counts"] == {"Pending": 1}
    assert client.post("/api/subscriptions/confirm", json={"token": "x" * 20}).status_code == 404
    assert client.post("/api/subscriptions/confirm", json={"token": r["dev_confirm_token"]}).json()["status"] == "active"
    assert client.post("/api/subscriptions/confirm", json={"token": r["dev_confirm_token"]}).status_code == 404   # single use


def test_confirmation_code_is_never_returned_in_live_mode(client, net, cfg, monkeypatch):
    cfg(notifications_mode="live", smtp_host="smtp.invalid", smtp_from="alerts@example.org")
    import app.services.notification_providers as prov

    sent = []
    monkeypatch.setattr(prov.SmtpEmailProvider, "send", lambda self, ch, to, subj, body: (sent.append((to, body)), prov.ProviderResult("accepted_by_provider", "smtp-email"))[1])
    r = sub(client).json()
    assert "dev_confirm_token" not in r and sent and sent[0][0] == "resident@example.com" and "confirm your alert subscription" in sent[0][1]


def test_resubscribing_does_not_reveal_whether_a_contact_exists(client):
    active_sub(client)
    again = sub(client)
    assert again.status_code == 202 and "dev_confirm_token" not in again.json() and again.json()["message"].startswith("If this contact is valid")


def test_resident_campaign_reaches_only_active_matching_subscribers_and_never_includes_casualty_numbers(client, make):
    d = incident(make, people_affected=4321)
    active_sub(client, contact="in.area@example.com")
    active_sub(client, contact="other.city@example.com", latitude=12.97, longitude=77.59, area_label="Bengaluru")
    sub(client, contact="pending@example.com")
    gone = active_sub(client, contact="left@example.com")
    c = new_campaign(client, d, audience="residents", template="public_safety_info", channels=("email",), verified_info="Roads on the east side are closed (confirmed by the district office).")
    p = client.get(f"/api/notifications/campaigns/{c['id']}/preview").json()
    assert p["recipient_count"] == 2                                                         # in.area + left (not yet unsubscribed)
    unsub_token = client.get("/api/subscriptions").json()  # operator view has no tokens
    assert "unsubscribe_token" not in str(unsub_token)
    assert "4,321" not in p["body"] and "4321" not in p["body"] and "unverified estimate" not in p["body"]
    assert "Roads on the east side are closed" in p["body"] and "Verified instructions are only included when entered by an authorised operator" in p["body"]
    assert p["excluded"]["incident outside the subscriber's chosen area"] == 1 and p["excluded"]["subscription pending"] == 1
    assert any("cannot reach every phone" in w for w in p["warnings"])
    assert gone


def test_unsubscribe_removes_recipient_and_messages_contain_opt_out_link(client, make, cfg):
    d = incident(make)
    active_sub(client, channel="sms", contact="+91 98765 43299")
    from app.database import SessionLocal
    from app.models import Subscription

    with SessionLocal() as db:
        token = db.query(Subscription).one().unsubscribe_token
    c = approve(client, new_campaign(client, d, audience="residents", template="public_safety_info", channels=("sms",)))
    dispatch(client, c)
    from app.services.notification_service import delivery_message

    with SessionLocal() as db:
        from app.models import NotificationCampaign

        camp, dv = db.get(NotificationCampaign, c["id"]), db.query(NotificationDelivery).one()
        _subject, text = delivery_message(db, camp, dv)
    assert f"#/alerts?unsubscribe={token}" in text and len(text) < 520 and "ReliefSync:" in text
    assert client.post("/api/subscriptions/unsubscribe", json={"token": token}).json()["status"] == "unsubscribed"
    assert client.post("/api/subscriptions/unsubscribe", json={"token": token}).json()["status"] == "unsubscribed"   # idempotent
    assert client.post("/api/subscriptions/unsubscribe", json={"token": "z" * 24}).status_code == 404
    again = new_campaign(client, d, audience="residents", template="incident_update", channels=("sms",))
    p = client.get(f"/api/notifications/campaigns/{again['id']}/preview").json()
    assert p["recipient_count"] == 0 and p["excluded"]["subscription unsubscribed"] == 1


def test_unsubscribed_person_can_opt_in_again_only_with_fresh_consent(client):
    r = active_sub(client)
    from app.database import SessionLocal
    from app.models import Subscription

    with SessionLocal() as db:
        token = db.query(Subscription).one().unsubscribe_token
    client.post("/api/subscriptions/unsubscribe", json={"token": token})
    again = sub(client)
    assert again.status_code == 202 and again.json()["dev_confirm_token"]
    assert client.get("/api/subscriptions").json()["items"][0]["status"] == "Pending" and r


def test_public_feed_alert_end_to_end_and_resolved_rules(client, make):
    d = incident(make)
    c = approve(client, new_campaign(client, d, audience="residents", template="public_safety_info", channels=("in_app",)))
    assert dispatch(client, c).json()["deliveries"] == {"recorded_in_app": 1}
    feed = client.get("/api/notifications/public-alerts").json()
    assert len(feed["items"]) == 1 and feed["items"][0]["incident_status"] == "Active" and NEUTRAL_PUBLIC_LINE in feed["items"][0]["body"]
    assert "Not an official warning system" in feed["notice"]
    client.patch(f"/api/disasters/{d['id']}/status", json={"status": "Resolved"})
    assert client.get("/api/notifications/public-alerts").json()["items"] == []               # resolved: no longer an active alert
    assert len(client.get("/api/notifications/public-alerts", params={"include_resolved": True}).json()["items"]) == 1
    ac = approve(client, new_campaign(client, d, audience="residents", template="all_clear", channels=("in_app",)))
    dispatch(client, ac)
    kinds = [i["kind"] for i in client.get("/api/notifications/public-alerts").json()["items"]]
    assert kinds == ["all_clear"]


# ------------------------------------------------------------------ message safety
@pytest.mark.parametrize("key", list(TEMPLATES))
def test_templates_never_invent_instructions_or_emergency_numbers(make, client, key):
    class D:
        id, disaster_type, location, severity, people_affected, status, location_approximate = 7, "Flood", "Chennai", "High", 5000, "Active", False

    for audience in TEMPLATES[key].audiences:
        subject, body = render_base(key, audience, D)
        low = (subject + body).lower()
        assert "evacuat" not in low and "must leave" not in low and "casualt" not in low and "dead" not in low and "death" not in low
        assert not re.search(r"\b(911|112|999|100|108|101)\b", low)                              # no invented emergency numbers
        if audience == "residents":
            assert "5,000" not in body and "5000" not in body                                    # no casualty / people-affected figures
            assert NEUTRAL_PUBLIC_LINE in body or key == "all_clear"
        else:
            assert "not independently verified" in body or key == "all_clear"
    assert TEMPLATES[key].purpose


def test_all_clear_only_after_resolution(client, make):
    d = incident(make)
    assert client.post("/api/notifications/campaigns", json={"audience": "residents", "template_key": "all_clear", "disaster_id": d["id"], "channels": ["in_app"]}).status_code == 409


# ------------------------------------------------------------------ authorisation, rate limiting
def test_operator_endpoints_require_key_but_public_ones_do_not(client, make, cfg):
    d = incident(make)
    cfg(operator_api_key="topsecret")
    h = {"X-Operator-Key": "topsecret", "X-Operator-Name": "Priya"}
    body = {"audience": "residents", "template_key": "public_safety_info", "disaster_id": d["id"], "channels": ["in_app"]}
    assert client.post("/api/notifications/campaigns", json=body).status_code == 401
    assert client.get("/api/notifications/campaigns").status_code == 401
    assert client.get("/api/notifications/audit").status_code == 401
    assert client.get("/api/notifications/inbox").status_code == 401
    assert client.get("/api/subscriptions").status_code == 401
    created = client.post("/api/notifications/campaigns", json=body, headers=h)
    assert created.status_code == 201 and created.json()["created_by"] == "Priya"
    cid = created.json()["id"]
    for path in ("approve",):
        assert client.post(f"/api/notifications/campaigns/{cid}/{path}").status_code == 401
    assert client.post(f"/api/notifications/campaigns/{cid}/dispatch", json={"confirm": True, "idempotency_key": "k" * 10}).status_code == 401
    assert client.post(f"/api/notifications/campaigns/{cid}/approve", headers=h).status_code == 200
    assert client.get("/api/notifications/public-alerts").status_code == 200                      # public
    assert sub(client).status_code == 202                                                           # public
    audit = client.get("/api/notifications/audit", headers=h).json()["items"]
    assert {"Priya"} <= {a["actor"] for a in audit}


def test_public_endpoints_are_rate_limited(client, cfg):
    cfg(rate_limit_public_per_minute=3)
    codes = [sub(client, contact=f"p{i}@example.com").status_code for i in range(5)]
    assert codes == [202, 202, 202, 429, 429]


def test_resident_channels_validated(client, make):
    d = incident(make)
    r = client.post("/api/notifications/campaigns", json={"audience": "shelters", "template_key": "shelter_preparedness", "disaster_id": d["id"], "channels": ["sms"]})
    assert r.status_code == 422
