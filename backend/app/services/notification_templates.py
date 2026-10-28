"""Reusable, factual message templates.

Rules enforced here (and covered by tests):
* Information is labelled: operator-entered figures are called "reported" / "not independently verified".
* Public-facing templates never contain casualty or people-affected numbers.
* No evacuation orders, emergency phone numbers or official warnings are ever invented. If an operator has not
  supplied VERIFIED public information, the message tells recipients to follow official local emergency-management
  sources instead.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import settings

NEUTRAL_PUBLIC_LINE = "Please follow instructions from your official local emergency-management authority."
NEUTRAL_RESPONDER_LINE = "Await instructions from your ReliefSync coordinator before travelling. Do not self-deploy."
SMS_MAX = 300


@dataclass(frozen=True)
class Template:
    key: str
    label: str
    audiences: tuple[str, ...]
    purpose: str
    subject: str  # str.format fields: kind, location
    public: bool = False
    allows_resolved: bool = False  # only the all-clear may refer to a resolved incident


TEMPLATES: dict[str, Template] = {t.key: t for t in (
    Template("volunteer_request", "Volunteer assistance request", ("volunteers",), "Ask nearby, available volunteers to offer help.", "Volunteers needed: {kind} near {location}"),
    Template("shelter_preparedness", "Shelter preparedness notice", ("shelters",), "Tell nearby shelter coordinators about an incident and ask them to confirm their status.", "Shelter notice: {kind} near {location}"),
    Template("resource_coordination", "Resource coordination alert", ("volunteers", "shelters"), "Coordinate supplies and logistics for an incident.", "Resource coordination: {kind} near {location}"),
    Template("public_safety_info", "Verified public safety information", ("residents",), "Share VERIFIED safety information with opted-in residents.", "Safety information: {kind} near {location}", public=True),
    Template("incident_update", "Incident update", ("volunteers", "shelters", "residents"), "Share a factual update on an ongoing incident.", "Update: {kind} near {location}"),
    Template("all_clear", "All-clear notice", ("volunteers", "shelters", "residents"), "Tell recipients an incident has been marked resolved in ReliefSync.", "All clear: {kind} near {location}", allows_resolved=True),
)}


def incident_link(disaster_id: int) -> str:
    return f"{settings.public_app_url}/#/map?disaster={disaster_id}"


def render_base(template_key: str, audience: str, disaster, *, required_skills: str = "", instructions: str = "", verified_info: str = "") -> tuple[str, str]:
    """Recipient-independent message (this is what an approver signs off on)."""
    t = TEMPLATES[template_key]
    kind, location = disaster.disaster_type, disaster.location
    subject = t.subject.format(kind=kind, location=location)
    lines: list[str] = []
    approx = " (position approximate)" if getattr(disaster, "location_approximate", False) else ""
    if template_key == "all_clear":
        lines.append(f"ReliefSync has marked the {kind} incident near {location} as resolved. This is an operational status in ReliefSync.")
        lines.append(verified_info.strip() if verified_info.strip() else NEUTRAL_PUBLIC_LINE)
    elif t.public or audience == "residents":
        lines.append(f"Incident reported: {kind} near {location}{approx}. Status in ReliefSync: {disaster.status}.")
        lines.append("Information source: ReliefSync operators. Details may change.")
        lines.append(verified_info.strip() if verified_info.strip() else NEUTRAL_PUBLIC_LINE)
        lines.append("Verified instructions are only included when entered by an authorised operator.")
    else:
        lines.append(f"Reported incident (entered by a ReliefSync user, not independently verified): {kind} near {location}{approx}.")
        lines.append(f"Severity rating: {disaster.severity} (user-entered). Reported people affected: {disaster.people_affected:,} (unverified estimate). Status: {disaster.status}.")
        if audience == "volunteers" and required_skills.strip():
            lines.append(f"Helpful skills: {required_skills.strip()}.")
        if template_key == "shelter_preparedness":
            lines.append("Please confirm your shelter's current status and capacity in ReliefSync. Being notified does not change your recorded availability.")
        lines.append(instructions.strip() if instructions.strip() else NEUTRAL_RESPONDER_LINE)
    lines.append(f"Incident page: {incident_link(disaster.id)}")
    return subject, "\n".join(lines)


def personalise(body: str, *, distance_km: float | None = None, capacity_line: str | None = None) -> str:
    extra = []
    if distance_km is not None:
        extra.append(f"Approximate distance from the incident: {distance_km:.1f} km (straight line, estimate).")
    if capacity_line:
        extra.append(capacity_line)
    return body if not extra else body + "\n" + "\n".join(extra)


def sms_text(subject: str, body: str) -> str:
    """Short SMS form. The incident link and the opt-out link are always kept; the middle is trimmed."""
    keep = ("Incident page", "To stop these alerts")
    tail = " ".join(l for l in body.splitlines() if l.startswith(keep))
    middle = " ".join(l for l in body.splitlines() if l and not l.startswith(keep))
    text = f"ReliefSync: {subject}. {middle}"
    room = max(60, SMS_MAX - len(tail) - 1)
    if len(text) > room:
        text = text[: room - 1].rstrip() + "…"
    return f"{text} {tail}".strip()
