import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from ..config import settings
from ..dependencies import DbSession, Limit, Offset, OperatorDep, RateLimiter, audit, commit, conflict, get_or_404, paginate
from ..models import AuditLog, Disaster, InAppNotification, NotificationCampaign, NotificationDelivery, Subscription
from ..schemas_ext import CampaignCreate, CampaignUpdate, DispatchRequest, RetryRequest, SubscriptionCreate, TokenRequest
from ..services import notification_service as svc
from ..services.geo import coarsen
from ..services.notification_providers import channel_status, get_provider, mask_contact, normalise_phone, valid_email
from ..services.notification_templates import TEMPLATES

router = APIRouter(tags=["Notifications"])
_public_limit = RateLimiter("subscriptions")

CONSENT_TEXT = ("I agree to receive occasional incident alerts for the area I selected at the contact I gave. "
                "I understand alerts are informational, may be incomplete, and are not an official warning system. "
                "I can unsubscribe at any time using the link in every message.")


def campaign_out(c: NotificationCampaign) -> dict:
    return {
        "id": c.id, "audience": c.audience, "template_key": c.template_key, "template": TEMPLATES[c.template_key].label,
        "disaster_id": c.disaster_id, "disaster_label": c.disaster.label, "disaster_status": c.disaster.status,
        "radius_km": c.radius_km, "channels": svc.parse_channels(c.channels), "required_skills": c.required_skills,
        "instructions": c.instructions, "verified_info": c.verified_info, "status": c.status, "created_by": c.created_by,
        "approved_by": c.approved_by, "approved_at": c.approved_at, "dispatched_by": c.dispatched_by, "dispatched_at": c.dispatched_at,
        "mode_at_dispatch": c.mode_at_dispatch, "created_at": c.created_at, "updated_at": c.updated_at,
    }


def _campaign(db, campaign_id: int) -> NotificationCampaign:
    return get_or_404(db, NotificationCampaign, campaign_id, "Campaign")


# ------------------------------------------------------------------ operator: configuration
@router.get("/notifications/status")
def notification_status(_op: OperatorDep):
    return {**channel_status(), "cooldown_minutes": settings.notification_cooldown_minutes, "max_attempts": settings.notification_max_attempts,
            "operator_auth": "multi-user password accounts" if not settings.operator_api_key else "shared operator key",
            "environment": settings.app_env}


@router.get("/notifications/templates")
def templates(_op: OperatorDep):
    return [{"key": t.key, "label": t.label, "audiences": list(t.audiences), "purpose": t.purpose} for t in TEMPLATES.values()]


# ------------------------------------------------------------------ operator: campaigns
@router.post("/notifications/campaigns", status_code=201)
def create_campaign(body: CampaignCreate, db: DbSession, op: OperatorDep):
    d = get_or_404(db, Disaster, body.disaster_id, "Disaster")
    channels = list(dict.fromkeys(body.channels))
    svc.validate_fields(body.audience, body.template_key, channels, body.radius_km, d)
    c = NotificationCampaign(audience=body.audience, template_key=body.template_key, disaster_id=d.id, radius_km=body.radius_km,
                             channels=",".join(channels), required_skills=body.required_skills, instructions=body.instructions,
                             verified_info=body.verified_info, created_by=op.name)
    db.add(c)
    db.flush()
    audit(db, op.name, "campaign.drafted", "campaign", c.id, audience=c.audience, template=c.template_key, disaster_id=d.id)
    commit(db)
    db.refresh(c)
    return campaign_out(c)


@router.get("/notifications/campaigns")
def list_campaigns(db: DbSession, _op: OperatorDep, limit: Limit = 50, offset: Offset = 0, status: str | None = None, disaster_id: int | None = None):
    stmt = select(NotificationCampaign).order_by(NotificationCampaign.created_at.desc(), NotificationCampaign.id.desc())
    if status:
        stmt = stmt.where(NotificationCampaign.status == status)
    if disaster_id:
        stmt = stmt.where(NotificationCampaign.disaster_id == disaster_id)
    page = paginate(db, stmt, limit, offset)
    page["items"] = [campaign_out(c) for c in page["items"]]
    return page


@router.get("/notifications/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, db: DbSession, _op: OperatorDep):
    c = _campaign(db, campaign_id)
    return {**campaign_out(c), "summary": svc.summary(db, c)}


@router.patch("/notifications/campaigns/{campaign_id}")
def update_campaign(campaign_id: int, body: CampaignUpdate, db: DbSession, op: OperatorDep):
    c = _campaign(db, campaign_id)
    if c.status != "Draft":
        raise conflict(f"Only a Draft can be edited (this campaign is {c.status}).")
    data = body.model_dump(exclude_none=True)
    if "channels" in data:
        data["channels"] = list(dict.fromkeys(data["channels"]))
    merged = {"template_key": c.template_key, "radius_km": c.radius_km, "channels": data.get("channels", svc.parse_channels(c.channels))}
    merged.update({k: v for k, v in data.items() if k in ("template_key", "radius_km")})
    svc.validate_fields(c.audience, merged["template_key"], merged["channels"], merged["radius_km"], c.disaster)
    for k, v in data.items():
        setattr(c, k, ",".join(v) if k == "channels" else v)
    audit(db, op.name, "campaign.edited", "campaign", c.id, fields=sorted(data))
    commit(db)
    return campaign_out(c)


@router.get("/notifications/campaigns/{campaign_id}/preview")
def preview_campaign(campaign_id: int, db: DbSession, _op: OperatorDep):
    return svc.preview(db, _campaign(db, campaign_id))


@router.post("/notifications/campaigns/{campaign_id}/approve")
def approve_campaign(campaign_id: int, db: DbSession, op: OperatorDep):
    c = _campaign(db, campaign_id)
    svc.approve(db, c, op.name)
    commit(db)
    return campaign_out(c)


@router.post("/notifications/campaigns/{campaign_id}/dispatch")
def dispatch_campaign(campaign_id: int, body: DispatchRequest, db: DbSession, op: OperatorDep):
    return svc.dispatch(db, _campaign(db, campaign_id), op.name, body.idempotency_key, body.confirm)


@router.post("/notifications/campaigns/{campaign_id}/retry-failed")
def retry_campaign(campaign_id: int, body: RetryRequest, db: DbSession, op: OperatorDep):
    return svc.retry_failed(db, _campaign(db, campaign_id), op.name, body.confirm)


@router.post("/notifications/campaigns/{campaign_id}/cancel")
def cancel_campaign(campaign_id: int, db: DbSession, op: OperatorDep):
    c = _campaign(db, campaign_id)
    if c.status not in ("Draft", "Approved"):
        raise conflict(f"A {c.status} campaign cannot be cancelled.")
    c.status = "Cancelled"
    audit(db, op.name, "campaign.cancelled", "campaign", c.id)
    commit(db)
    return campaign_out(c)


@router.get("/notifications/campaigns/{campaign_id}/deliveries")
def deliveries(campaign_id: int, db: DbSession, _op: OperatorDep, limit: Limit = 100, offset: Offset = 0, status: str | None = None):
    _campaign(db, campaign_id)
    stmt = select(NotificationDelivery).where(NotificationDelivery.campaign_id == campaign_id).order_by(NotificationDelivery.id)
    if status:
        stmt = stmt.where(NotificationDelivery.status == status)
    page = paginate(db, stmt, limit, offset)
    page["items"] = [{"id": x.id, "recipient_type": x.recipient_type, "recipient_id": x.recipient_id, "channel": x.channel,
                      "address_masked": x.address_masked, "status": x.status, "provider": x.provider, "provider_message_id": x.provider_message_id,
                      "detail": x.detail, "attempts": x.attempts, "last_attempt_at": x.last_attempt_at} for x in page["items"]]
    page["status_meaning"] = {
        "recorded_in_app": "A record was created inside ReliefSync. No SMS or email was sent.",
        "simulated": "Development mode: nothing was sent to anyone.",
        "accepted_by_provider": "The SMS/email provider accepted the message. Delivery to the person is NOT confirmed.",
        "failed": "The attempt failed; see detail.", "pending": "Not attempted yet.", "skipped": "Not sent."}
    return page


# ------------------------------------------------------------------ in-app notifications
def _note(n: InAppNotification) -> dict:
    return {"id": n.id, "campaign_id": n.campaign_id, "recipient_type": n.recipient_type, "recipient_id": n.recipient_id, "disaster_id": n.disaster_id,
            "title": n.title, "body": n.body, "link": n.link, "created_at": n.created_at, "read_at": n.read_at,
            "label": "In-app notification (a record inside ReliefSync, not an SMS or email)"}


@router.get("/notifications/inbox")
def inbox(db: DbSession, _op: OperatorDep, recipient_type: str | None = None, recipient_id: int | None = None, unread_only: bool = False,
          limit: Limit = 50, offset: Offset = 0):
    """Operator view of in-app notifications. (Volunteers and shelter coordinators do not have logins in this version.)"""
    stmt = select(InAppNotification).order_by(InAppNotification.created_at.desc(), InAppNotification.id.desc())
    if recipient_type:
        stmt = stmt.where(InAppNotification.recipient_type == recipient_type)
    if recipient_id is not None:
        stmt = stmt.where(InAppNotification.recipient_id == recipient_id)
    if unread_only:
        stmt = stmt.where(InAppNotification.read_at.is_(None))
    page = paginate(db, stmt, limit, offset)
    page["items"] = [_note(n) for n in page["items"]]
    return page


@router.post("/notifications/inbox/{note_id}/read")
def mark_read(note_id: int, db: DbSession, _op: OperatorDep):
    n = get_or_404(db, InAppNotification, note_id, "Notification")
    n.read_at = n.read_at or datetime.now(timezone.utc)
    commit(db)
    return _note(n)


@router.get("/notifications/public-alerts")
def public_alerts(db: DbSession, limit: int = Query(20, ge=1, le=100), include_resolved: bool = False):
    """The public alert feed (no login). Alerts for resolved incidents are hidden unless they are all-clear notices."""
    stmt = (
        select(InAppNotification, NotificationCampaign, Disaster)
        .join(NotificationCampaign, NotificationCampaign.id == InAppNotification.campaign_id)
        .join(Disaster, Disaster.id == NotificationCampaign.disaster_id)
        .where(InAppNotification.recipient_type == "public")
        .order_by(InAppNotification.created_at.desc(), InAppNotification.id.desc())
    )
    items = []
    for n, c, d in db.execute(stmt.limit(limit * 3)):
        if d.status == "Resolved" and c.template_key != "all_clear" and not include_resolved:
            continue
        items.append({**_note(n), "incident_status": d.status, "kind": "all_clear" if c.template_key == "all_clear" else "alert"})
        if len(items) >= limit:
            break
    return {"items": items, "notice": "Informational alerts entered by ReliefSync operators. Not an official warning system. "
            "Follow your local emergency-management authority."}


@router.get("/notifications/audit")
def audit_log(db: DbSession, _op: OperatorDep, limit: Limit = 100, offset: Offset = 0, entity_type: str | None = None, entity_id: int | None = None):
    stmt = select(AuditLog).order_by(AuditLog.at.desc(), AuditLog.id.desc())
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    page = paginate(db, stmt, limit, offset)
    page["items"] = [{"id": a.id, "at": a.at, "actor": a.actor, "action": a.action, "entity_type": a.entity_type, "entity_id": a.entity_id, "detail": a.detail}
                     for a in page["items"]]
    return page


# ------------------------------------------------------------------ subscriptions (resident opt-in)
@router.post("/subscriptions", status_code=202)
def subscribe(body: SubscriptionCreate, db: DbSession, _rl=Depends(_public_limit)):
    """Opt in to alerts for a coarse area. Stores the area rounded to ~11 km (never an exact location) and the
    consent text. Email/SMS subscriptions stay Pending until the recipient confirms with a token sent to them."""
    contact = body.contact
    if body.channel == "sms":
        contact = normalise_phone(contact)
        if not contact:
            raise HTTPException(422, "Enter the phone number in international format, e.g. +919876543210.")
    elif not valid_email(contact):
        raise HTTPException(422, "Enter a valid email address.")
    lat, lng = coarsen(body.latitude, body.longitude, 1)
    sub = db.scalar(select(Subscription).where(Subscription.channel == body.channel, Subscription.contact == contact))
    token = secrets.token_urlsafe(24)
    if sub is None:
        sub = Subscription(channel=body.channel, contact=contact, area_latitude=lat, area_longitude=lng, unsubscribe_token=secrets.token_urlsafe(24),
                           consent_text=CONSENT_TEXT, status="Pending", confirm_token=token)
        db.add(sub)
    elif sub.status == "Active":
        sub.area_label, sub.area_latitude, sub.area_longitude, sub.radius_km = body.area_label, lat, lng, body.radius_km
        commit(db)
        return {"status": "accepted", "message": "If this contact is valid, you will receive a confirmation message."}  # no enumeration
    else:  # Pending or Unsubscribed: a fresh, explicit consent is required
        sub.status, sub.confirm_token, sub.consent_text, sub.consent_at = "Pending", token, CONSENT_TEXT, datetime.now(timezone.utc)
        sub.unsubscribed_at = None
    sub.area_label, sub.area_latitude, sub.area_longitude, sub.radius_km = body.area_label, lat, lng, body.radius_km
    db.flush()
    audit(db, "resident", "subscription.requested", "subscription", sub.id, channel=body.channel, contact=mask_contact(body.channel, contact))
    commit(db)
    text = f"ReliefSync: confirm your alert subscription with this code: {token}. If you did not ask for this, ignore this message."
    result = get_provider(body.channel).send(body.channel, contact, "Confirm your ReliefSync alerts", text)
    resp = {"status": "accepted", "confirmation": result.status, "message": "If this contact is valid, you will receive a confirmation message."}
    if result.status == "failed":
        resp["message"] = "We could not send the confirmation message. Please try again later."
    if not settings.live_mode:  # development convenience only; never exposed in live mode
        resp["dev_confirm_token"] = token
        resp["dev_note"] = "Development mode: no message was sent. This token is returned only because notifications are simulated."
    return resp


@router.post("/subscriptions/confirm")
def confirm_subscription(body: TokenRequest, db: DbSession, _rl=Depends(_public_limit)):
    sub = db.scalar(select(Subscription).where(Subscription.confirm_token == body.token))
    if sub is None or sub.status != "Pending":
        raise HTTPException(404, "This confirmation code is not valid.")
    sub.status, sub.confirm_token, sub.confirmed_at = "Active", None, datetime.now(timezone.utc)
    audit(db, "resident", "subscription.confirmed", "subscription", sub.id)
    commit(db)
    return {"status": "active", "area_label": sub.area_label, "radius_km": sub.radius_km}


@router.post("/subscriptions/unsubscribe")
def unsubscribe(body: TokenRequest, db: DbSession, _rl=Depends(_public_limit)):
    sub = db.scalar(select(Subscription).where(Subscription.unsubscribe_token == body.token))
    if sub is None:
        raise HTTPException(404, "This unsubscribe link is not valid.")
    if sub.status != "Unsubscribed":
        sub.status, sub.unsubscribed_at, sub.confirm_token = "Unsubscribed", datetime.now(timezone.utc), None
        audit(db, "resident", "subscription.unsubscribed", "subscription", sub.id)
        commit(db)
    return {"status": "unsubscribed"}


@router.get("/subscriptions")
def list_subscriptions(db: DbSession, _op: OperatorDep, limit: Limit = 100, offset: Offset = 0):
    """Operators see masked contacts and coarse areas only."""
    counts = dict(db.execute(select(Subscription.status, func.count()).group_by(Subscription.status)).all())
    page = paginate(db, select(Subscription).order_by(Subscription.id.desc()), limit, offset)
    page["items"] = [{"id": s.id, "channel": s.channel, "contact_masked": mask_contact(s.channel, s.contact), "area_label": s.area_label,
                      "area_latitude": s.area_latitude, "area_longitude": s.area_longitude, "radius_km": s.radius_km, "status": s.status,
                      "consent_at": s.consent_at} for s in page["items"]]
    page["counts"] = counts
    return page
