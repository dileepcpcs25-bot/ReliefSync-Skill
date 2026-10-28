"""Campaign workflow: draft -> preview -> approve -> dispatch (-> retry failed).

Safety properties (all covered by tests):
* Nothing is sent without an operator-approved campaign AND an explicit `confirm` on dispatch.
* The approved message is hashed; if the content changes after approval, dispatch is refused.
* Dispatch is idempotent (client key) and claims the campaign atomically; each (campaign, recipient, channel)
  can exist only once (UNIQUE), so a double click or retry can never send the same message twice.
* Recipients are re-evaluated at dispatch time (availability, assignment conflicts, consent, resolved status).
* Development mode (default) uses a simulator for sms/email: no real recipient is ever contacted.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..dependencies import audit
from ..models import (
    Disaster,
    InAppNotification,
    NotificationCampaign,
    NotificationDelivery,
    Shelter,
    Subscription,
    Volunteer,
)
from .geo import haversine_km
from .nearby import find_nearby_volunteers
from .notification_providers import get_provider, mask_contact, normalise_phone, valid_email
from .notification_templates import NEUTRAL_PUBLIC_LINE, TEMPLATES, personalise, render_base, sms_text

CHANNELS_BY_AUDIENCE = {"volunteers": {"in_app", "sms"}, "shelters": {"in_app"}, "residents": {"in_app", "sms", "email"}}
SUCCESS_STATUSES = ("recorded_in_app", "simulated", "accepted_by_provider")
PREVIEW_LIST_LIMIT = 200


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Recipient:
    rtype: str
    rid: int
    channel: str
    address: str  # real address; never returned by the API
    label: str
    distance_km: float | None = None


@dataclass
class Plan:
    recipients: list[Recipient] = field(default_factory=list)
    excluded: dict[str, int] = field(default_factory=dict)


def _bump(d: dict, key: str, n: int = 1) -> None:
    d[key] = d.get(key, 0) + n


def parse_channels(csv: str) -> list[str]:
    return [c for c in (csv or "").split(",") if c]


# ------------------------------------------------------------------ validation
def validate_fields(audience: str, template_key: str, channels: list[str], radius_km: float, disaster: Disaster) -> None:
    tpl = TEMPLATES.get(template_key)
    if tpl is None:
        raise HTTPException(422, f"Unknown template '{template_key}'.")
    if audience not in tpl.audiences:
        raise HTTPException(422, f"Template '{template_key}' cannot be used for the '{audience}' audience.")
    if not channels:
        raise HTTPException(422, "Choose at least one channel.")
    bad = [c for c in channels if c not in CHANNELS_BY_AUDIENCE[audience]]
    if bad:
        raise HTTPException(422, f"Channel(s) not available for {audience}: {', '.join(bad)}.")
    if not (0 < radius_km <= settings.max_radius_km):
        raise HTTPException(422, f"Radius must be between 0 and {settings.max_radius_km:g} km.")
    if disaster.status == "Resolved" and not tpl.allows_resolved:
        raise HTTPException(409, "Resolved incidents are excluded from active notification campaigns. Only an all-clear notice can refer to a resolved incident.")
    if disaster.status != "Resolved" and tpl.key == "all_clear":
        raise HTTPException(409, "An all-clear notice can only be sent after the incident is marked Resolved.")
    if not disaster.has_coordinates:
        raise HTTPException(409, "This incident has no coordinates, so a geographic audience cannot be determined. Set its location on the map first.")


# ------------------------------------------------------------------ recipients
def _recently_notified(db: Session, campaign: NotificationCampaign) -> set[tuple[str, int, str]]:
    cutoff = _now() - timedelta(minutes=settings.notification_cooldown_minutes)
    rows = db.execute(
        select(NotificationDelivery.recipient_type, NotificationDelivery.recipient_id, NotificationDelivery.channel)
        .join(NotificationCampaign, NotificationCampaign.id == NotificationDelivery.campaign_id)
        .where(
            NotificationCampaign.disaster_id == campaign.disaster_id,
            NotificationCampaign.id != campaign.id,
            NotificationDelivery.status.in_(SUCCESS_STATUSES),
            NotificationDelivery.created_at >= cutoff,
        )
    )
    return {(t, i, c) for t, i, c in rows}


def build_plan(db: Session, campaign: NotificationCampaign) -> Plan:
    d = campaign.disaster
    channels = parse_channels(campaign.channels)
    plan = Plan()
    tpl = TEMPLATES[campaign.template_key]
    cooldown = set() if tpl.allows_resolved else _recently_notified(db, campaign)

    def add(r: Recipient):
        if (r.rtype, r.rid, r.channel) in cooldown and r.rtype != "public":
            _bump(plan.excluded, f"notified within the last {settings.notification_cooldown_minutes} min (cooldown)")
        else:
            plan.recipients.append(r)

    if d.status == "Resolved" and not tpl.allows_resolved:
        _bump(plan.excluded, "incident is resolved")
        return plan

    if campaign.audience == "volunteers":
        search = find_nearby_volunteers(db, d, campaign.radius_km, campaign.required_skills or None,
                                        require_skill_match=bool(campaign.required_skills.strip()))
        for reason, n in search.excluded.items():
            _bump(plan.excluded, reason, n)
        for c in search.candidates:
            v = c.volunteer
            if "in_app" in channels:
                add(Recipient("volunteer", v.id, "in_app", "", f"Volunteer #{v.id} {v.name}", c.distance_km))
            if "sms" in channels:
                phone = normalise_phone(v.phone)
                if not v.sms_opt_in:
                    _bump(plan.excluded, "no SMS consent recorded")
                elif not phone:
                    _bump(plan.excluded, "phone number is not in international (+country code) format")
                else:
                    add(Recipient("volunteer", v.id, "sms", phone, f"Volunteer #{v.id} {v.name}", c.distance_km))

    elif campaign.audience == "shelters":
        for sh in db.scalars(select(Shelter)).all():
            if not sh.has_coordinates:
                _bump(plan.excluded, "position unknown")
                continue
            dist = haversine_km(d.latitude, d.longitude, sh.latitude, sh.longitude)
            if dist > campaign.radius_km:
                _bump(plan.excluded, "outside radius")
                continue
            add(Recipient("shelter", sh.id, "in_app", "", f"Shelter #{sh.id} {sh.name}", round(dist, 1)))

    else:  # residents: public in-app feed + opted-in, confirmed subscribers whose chosen area contains the incident
        if "in_app" in channels:
            plan.recipients.append(Recipient("public", 0, "in_app", "", "Public alert feed (all visitors of this app)"))
        wanted = [c for c in channels if c in ("sms", "email")]
        if wanted:
            for s in db.scalars(select(Subscription).where(Subscription.channel.in_(wanted))).all():
                if s.status != "Active":
                    _bump(plan.excluded, f"subscription {s.status.lower()}")
                    continue
                dist = haversine_km(d.latitude, d.longitude, s.area_latitude, s.area_longitude)
                if dist > min(s.radius_km, campaign.radius_km):
                    _bump(plan.excluded, "incident outside the subscriber's chosen area")
                    continue
                add(Recipient("subscription", s.id, s.channel, s.contact, f"Subscriber #{s.id} ({s.area_label or 'area'})", None))
    return plan


# ------------------------------------------------------------------ message
def base_message(campaign: NotificationCampaign) -> tuple[str, str]:
    return render_base(campaign.template_key, campaign.audience, campaign.disaster, required_skills=campaign.required_skills,
                       instructions=campaign.instructions, verified_info=campaign.verified_info)


def message_hash(subject: str, body: str, channels: str, audience: str, radius_km: float) -> str:
    return hashlib.sha256("\x1f".join([subject, body, channels, audience, f"{radius_km:g}"]).encode()).hexdigest()


def campaign_hash(campaign: NotificationCampaign) -> str:
    s, b = base_message(campaign)
    return message_hash(s, b, campaign.channels, campaign.audience, campaign.radius_km)


def _capacity_line(sh: Shelter) -> str:
    return (f"Your shelter's recorded availability: {sh.available_capacity} of {sh.total_capacity} places free "
            f"(as last recorded {sh.updated_at:%Y-%m-%d %H:%M} UTC). This notice does not change that record.")


def delivery_message(db: Session, campaign: NotificationCampaign, delivery: NotificationDelivery) -> tuple[str, str]:
    subject, body = base_message(campaign)
    d = campaign.disaster
    distance = capacity = None
    if delivery.recipient_type == "volunteer":
        v = db.get(Volunteer, delivery.recipient_id)
        if v and v.has_coordinates:
            distance = haversine_km(d.latitude, d.longitude, v.latitude, v.longitude)
    elif delivery.recipient_type == "shelter":
        sh = db.get(Shelter, delivery.recipient_id)
        if sh and sh.has_coordinates:
            distance = haversine_km(d.latitude, d.longitude, sh.latitude, sh.longitude)
            capacity = _capacity_line(sh)
    body = personalise(body, distance_km=distance, capacity_line=capacity)
    if delivery.recipient_type == "subscription":
        sub = db.get(Subscription, delivery.recipient_id)
        if sub:
            body += f"\nTo stop these alerts: {settings.public_app_url}/#/alerts?unsubscribe={sub.unsubscribe_token}"
    if delivery.channel == "sms":
        body = sms_text(subject, body)
    return subject, body


def _warnings(campaign: NotificationCampaign, plan: Plan, channels: list[str]) -> list[str]:
    w = []
    if not settings.live_mode:
        w.append("DEVELOPMENT MODE: SMS and email are simulated. No real person will be contacted.")
    for ch, ok, name in (("sms", settings.twilio_configured, "Twilio"), ("email", settings.smtp_configured, "SMTP")):
        if ch in channels and settings.live_mode and not ok:
            w.append(f"Live mode is on but {name} is not configured: {ch} deliveries will FAIL (and be reported as failed).")
    if campaign.audience == "residents":
        if not campaign.verified_info.strip():
            w.append(f"No verified public information was supplied, so the message only says: \"{NEUTRAL_PUBLIC_LINE}\"")
        w.append("Only opted-in, confirmed subscribers are contacted. ReliefSync cannot reach every phone in an area; use official public-warning systems for that.")
    if not campaign.disaster.has_coordinates:
        w.append("The incident has no coordinates.")
    elif campaign.disaster.location_approximate:
        w.append("The incident position is approximate; the audience area is approximate too.")
    if not plan.recipients:
        w.append("No eligible recipients: the campaign cannot be approved or dispatched.")
    return w


def _cost(channel: str, n: int) -> str:
    unit = settings.sms_cost_per_message if channel == "sms" else settings.email_cost_per_message if channel == "email" else ""
    if channel == "in_app":
        return "No cost (in-app record)"
    return f"{n} x {unit} (estimate; the provider's billing is authoritative)" if unit else "Cost information is not configured"


def preview(db: Session, campaign: NotificationCampaign) -> dict:
    plan = build_plan(db, campaign)
    channels = parse_channels(campaign.channels)
    subject, body = base_message(campaign)
    sample = None
    if plan.recipients:
        r0 = plan.recipients[0]
        probe = NotificationDelivery(campaign_id=campaign.id, recipient_type=r0.rtype, recipient_id=r0.rid, channel=r0.channel)
        sample = delivery_message(db, campaign, probe)[1]
    per_channel = {}
    for ch in channels:
        n = sum(1 for r in plan.recipients if r.channel == ch)
        real = ch in ("sms", "email") and settings.live_mode and (settings.twilio_configured if ch == "sms" else settings.smtp_configured)
        per_channel[ch] = {"eligible": n, "will_contact_real_people": bool(real), "cost": _cost(ch, n)}
    d = campaign.disaster
    return {
        "campaign_id": campaign.id, "status": campaign.status, "mode": settings.notifications_mode,
        "audience": campaign.audience, "template": TEMPLATES[campaign.template_key].label,
        "disaster": {"id": d.id, "label": d.label, "status": d.status, "latitude": d.latitude, "longitude": d.longitude, "approximate": d.location_approximate},
        "target_area": {"latitude": d.latitude, "longitude": d.longitude, "radius_km": campaign.radius_km},
        "subject": subject, "body": body, "sample_personalised_body": sample,
        "channels": per_channel, "recipient_count": len(plan.recipients),
        "recipients": [
            {"type": r.rtype, "id": r.rid, "label": r.label, "channel": r.channel,
             "address_masked": mask_contact(r.channel, r.address), "distance_km": r.distance_km}
            for r in plan.recipients[:PREVIEW_LIST_LIMIT]
        ],
        "recipients_truncated": len(plan.recipients) > PREVIEW_LIST_LIMIT,
        "excluded": plan.excluded, "warnings": _warnings(campaign, plan, channels),
        "message_hash": campaign_hash(campaign), "requires_approval": True,
    }


# ------------------------------------------------------------------ workflow
def approve(db: Session, campaign: NotificationCampaign, operator_name: str) -> None:
    if campaign.status != "Draft":
        raise HTTPException(409, f"Only a Draft can be approved (this campaign is {campaign.status}).")
    validate_fields(campaign.audience, campaign.template_key, parse_channels(campaign.channels), campaign.radius_km, campaign.disaster)
    plan = build_plan(db, campaign)
    if not plan.recipients:
        raise HTTPException(409, "There are no eligible recipients, so there is nothing to approve.")
    campaign.status = "Approved"
    campaign.approved_by = operator_name
    campaign.approved_at = _now()
    campaign.approved_message_hash = campaign_hash(campaign)
    audit(db, operator_name, "campaign.approved", "campaign", campaign.id, recipients=len(plan.recipients),
          channels=campaign.channels, audience=campaign.audience, radius_km=campaign.radius_km, message_hash=campaign.approved_message_hash)


def _deliver(db: Session, campaign: NotificationCampaign, delivery: NotificationDelivery) -> None:
    """Attempt one delivery and record the honest outcome. Commits per delivery so a crash can never lose the
    record of a message that was already handed to a provider."""
    delivery.attempts += 1
    delivery.last_attempt_at = _now()
    db.commit()  # attempt is on record BEFORE the provider is called
    subject, body = delivery_message(db, campaign, delivery)
    if delivery.channel == "in_app":
        note = InAppNotification(
            campaign_id=campaign.id, delivery_id=delivery.id, recipient_type=delivery.recipient_type, recipient_id=delivery.recipient_id,
            disaster_id=campaign.disaster_id, title=subject, body=body, link=f"/#/map?disaster={campaign.disaster_id}",
        )
        db.add(note)
        delivery.status, delivery.provider, delivery.detail = "recorded_in_app", "in-app", "Recorded inside ReliefSync. This is not an SMS or email."
    else:
        address = _resolve_address(db, delivery)
        if not address:
            delivery.status, delivery.provider, delivery.detail = "failed", "", "Recipient address is no longer available (subscription ended or record changed)."
        else:
            result = get_provider(delivery.channel).send(delivery.channel, address, subject, body)
            delivery.status, delivery.provider, delivery.provider_message_id, delivery.detail = result.status, result.provider, result.message_id, result.detail
    db.commit()


def _resolve_address(db: Session, delivery: NotificationDelivery) -> str | None:
    if delivery.recipient_type == "volunteer":
        v = db.get(Volunteer, delivery.recipient_id)
        return normalise_phone(v.phone) if v and v.sms_opt_in else None
    if delivery.recipient_type == "subscription":
        s = db.get(Subscription, delivery.recipient_id)
        if s and s.status == "Active" and (normalise_phone(s.contact) if s.channel == "sms" else s.contact if valid_email(s.contact) else None):
            return s.contact
    return None


def _final_status(db: Session, campaign: NotificationCampaign) -> str:
    rows = db.scalars(select(NotificationDelivery.status).where(NotificationDelivery.campaign_id == campaign.id)).all()
    failed = sum(1 for s in rows if s == "failed")
    ok = sum(1 for s in rows if s in SUCCESS_STATUSES)
    if failed and not ok:
        return "Failed"
    return "Partially Failed" if failed else "Dispatched"


def summary(db: Session, campaign: NotificationCampaign) -> dict:
    rows = db.scalars(select(NotificationDelivery.status).where(NotificationDelivery.campaign_id == campaign.id)).all()
    counts: dict[str, int] = {}
    for s in rows:
        counts[s] = counts.get(s, 0) + 1
    return {"campaign_id": campaign.id, "status": campaign.status, "mode": campaign.mode_at_dispatch, "deliveries": counts, "total": len(rows)}


def dispatch(db: Session, campaign: NotificationCampaign, operator_name: str, idempotency_key: str, confirm: bool) -> dict:
    # Replay of an already-processed request returns the recorded outcome and does nothing else.
    if campaign.dispatch_idempotency_key == idempotency_key and campaign.status in ("Dispatching", "Dispatched", "Partially Failed", "Failed"):
        return {**summary(db, campaign), "replayed": True}
    if not confirm:
        raise HTTPException(422, "Explicit confirmation is required before dispatch (confirm = true).")
    if campaign.status != "Approved":
        raise HTTPException(409, f"Only an Approved campaign can be dispatched (this campaign is {campaign.status}).")
    validate_fields(campaign.audience, campaign.template_key, parse_channels(campaign.channels), campaign.radius_km, campaign.disaster)
    if campaign_hash(campaign) != campaign.approved_message_hash:
        raise HTTPException(409, "The message or audience changed after approval. Re-approve before dispatching.")
    plan = build_plan(db, campaign)  # eligibility is re-checked NOW, not at approval time
    if not plan.recipients:
        raise HTTPException(409, "There are no eligible recipients right now.")

    claimed = db.execute(
        update(NotificationCampaign)
        .where(NotificationCampaign.id == campaign.id, NotificationCampaign.status == "Approved")
        .values(status="Dispatching", dispatch_idempotency_key=idempotency_key, dispatched_by=operator_name,
                dispatched_at=_now(), mode_at_dispatch=settings.notifications_mode)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "This campaign is already being dispatched.")
    audit(db, operator_name, "campaign.dispatch_started", "campaign", campaign.id, mode=settings.notifications_mode,
          recipients=len(plan.recipients), idempotency_key=idempotency_key)
    db.commit()
    db.refresh(campaign)

    deliveries = []
    for r in plan.recipients:
        dv = NotificationDelivery(campaign_id=campaign.id, recipient_type=r.rtype, recipient_id=r.rid, channel=r.channel,
                                  address_masked=mask_contact(r.channel, r.address), status="pending")
        db.add(dv)
        try:
            db.flush()
            deliveries.append(dv)
        except IntegrityError:  # UNIQUE(campaign, recipient, channel): never a second delivery
            db.rollback()
    db.commit()
    for dv in deliveries:
        _deliver(db, campaign, dv)

    campaign.status = _final_status(db, campaign)
    audit(db, operator_name, "campaign.dispatch_finished", "campaign", campaign.id, **summary(db, campaign))
    db.commit()
    return {**summary(db, campaign), "replayed": False}


def retry_failed(db: Session, campaign: NotificationCampaign, operator_name: str, confirm: bool) -> dict:
    if not confirm:
        raise HTTPException(422, "Explicit confirmation is required (confirm = true).")
    if campaign.status not in ("Partially Failed", "Failed"):
        raise HTTPException(409, "Only campaigns with failed deliveries can be retried.")
    if campaign.disaster.status == "Resolved" and not TEMPLATES[campaign.template_key].allows_resolved:
        raise HTTPException(409, "The incident is now resolved; its notifications are not retried.")
    todo = db.scalars(
        select(NotificationDelivery).where(
            NotificationDelivery.campaign_id == campaign.id, NotificationDelivery.status == "failed",
            NotificationDelivery.attempts < settings.notification_max_attempts)
    ).all()  # only 'failed' rows: anything accepted/recorded is never touched, so nothing is sent twice
    if not todo:
        raise HTTPException(409, f"No failed deliveries are eligible (maximum {settings.notification_max_attempts} attempts each).")
    audit(db, operator_name, "campaign.retry_started", "campaign", campaign.id, deliveries=len(todo))
    db.commit()
    for dv in todo:
        _deliver(db, campaign, dv)
    campaign.status = _final_status(db, campaign)
    audit(db, operator_name, "campaign.retry_finished", "campaign", campaign.id, **summary(db, campaign))
    db.commit()
    return {**summary(db, campaign), "replayed": False}
