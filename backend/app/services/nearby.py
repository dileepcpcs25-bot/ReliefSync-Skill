"""Nearby volunteer / shelter discovery from stored coordinates.

Distances are straight-line (haversine) estimates. Ranking is transparent:
    volunteer rank score = 0.6 x skill suitability + 0.4 x proximity,   proximity = 1 - distance / radius
Volunteers who are unavailable, have no known position, are outside the radius, or already hold an Active
assignment are EXCLUDED (and counted with the reason so an operator can see why)."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Assignment, Disaster, Shelter, Volunteer
from .geo import bounding_box, haversine_km, osm_directions_url

# Skills that are useful for a given hazard (lower-case keywords matched against the volunteer's free-text skills).
SKILLS_BY_HAZARD = {
    "flood": ["boat", "swim", "rescue", "first aid", "driving", "logistics"],
    "earthquake": ["search", "rescue", "first aid", "medical", "engineer", "structural"],
    "cyclone": ["rescue", "first aid", "logistics", "driving", "shelter"],
    "tropical cyclone": ["rescue", "first aid", "logistics", "driving", "shelter"],
    "wildfire": ["fire", "first aid", "evacuation", "driving", "logistics"],
    "fire": ["fire", "first aid", "evacuation", "driving", "logistics"],
}
DEFAULT_SKILLS = ["first aid", "logistics", "driving", "rescue", "medical"]
ROLE_BY_SKILL = {
    "first aid": "First-aid support", "medical": "Medical support", "nurse": "Medical support", "doctor": "Medical support",
    "boat": "Water rescue support", "swim": "Water rescue support", "rescue": "Search and rescue support",
    "search": "Search and rescue support", "fire": "Fire-response support", "driving": "Transport and logistics",
    "logistics": "Transport and logistics", "engineer": "Structural assessment support", "shelter": "Shelter support",
    "evacuation": "Evacuation support",
}


def parse_skills(text: str) -> list[str]:
    return [s.strip().lower() for s in (text or "").replace(";", ",").split(",") if s.strip()]


def wanted_skills(disaster_type: str, explicit: str | list[str] | None) -> list[str]:
    if explicit:
        return parse_skills(explicit) if isinstance(explicit, str) else [s.lower() for s in explicit]
    kind = (disaster_type or "").lower()
    for key, skills in SKILLS_BY_HAZARD.items():
        if key in kind:
            return skills
    return DEFAULT_SKILLS


def skill_match(volunteer_skills: str, wanted: list[str]) -> list[str]:
    have = parse_skills(volunteer_skills)
    return [w for w in wanted if any(w in h or h in w for h in have)]


def suggested_role(matches: list[str]) -> str:
    for m in matches:
        if m in ROLE_BY_SKILL:
            return ROLE_BY_SKILL[m]
    return "General relief support"


@dataclass
class VolunteerCandidate:
    volunteer: Volunteer
    distance_km: float
    matched_skills: list[str]
    suitability: float
    score: float
    role: str
    reason: str


@dataclass
class VolunteerSearch:
    candidates: list[VolunteerCandidate] = field(default_factory=list)
    excluded: dict[str, int] = field(default_factory=dict)
    wanted: list[str] = field(default_factory=list)


def _bump(d: dict, key: str) -> None:
    d[key] = d.get(key, 0) + 1


def find_nearby_volunteers(db: Session, disaster: Disaster, radius_km: float, required_skills: str | list[str] | None = None,
                           require_skill_match: bool = False, limit: int = 50) -> VolunteerSearch:
    result = VolunteerSearch(wanted=wanted_skills(disaster.disaster_type, required_skills))
    if disaster.status == "Resolved" or not disaster.has_coordinates:
        return result
    busy = set(db.scalars(select(Assignment.volunteer_id).where(Assignment.status == "Active")))
    for v in db.scalars(select(Volunteer)).all():
        if v.availability != "Available":
            _bump(result.excluded, f"not available ({v.availability})")
            continue
        if v.id in busy:
            _bump(result.excluded, "already on an active assignment")
            continue
        if not v.has_coordinates:
            _bump(result.excluded, "position unknown")
            continue
        s, w, n, e = bounding_box(disaster.latitude, disaster.longitude, radius_km)  # cheap reject before haversine
        if not (s <= v.latitude <= n and w <= v.longitude <= e):
            _bump(result.excluded, "outside radius")
            continue
        dist = haversine_km(disaster.latitude, disaster.longitude, v.latitude, v.longitude)
        if dist > radius_km:
            _bump(result.excluded, "outside radius")
            continue
        matches = skill_match(v.skills, result.wanted)
        if require_skill_match and not matches:
            _bump(result.excluded, "no matching skills")
            continue
        suitability = len(matches) / len(result.wanted) if result.wanted else 0.0
        proximity = max(0.0, 1.0 - dist / radius_km)
        score = round(0.6 * suitability + 0.4 * proximity, 4)
        reason = (
            f"Available; about {dist:.1f} km away (straight line); "
            + (f"matching skills: {', '.join(matches)}" if matches else "no listed skill matches this incident type")
            + "; no active assignment."
        )
        result.candidates.append(VolunteerCandidate(v, round(dist, 1), matches, round(suitability, 2), score, suggested_role(matches), reason))
    result.candidates.sort(key=lambda c: (-c.score, c.distance_km, c.volunteer.id))
    result.candidates = result.candidates[:limit]
    return result


@dataclass
class ShelterCandidate:
    shelter: Shelter
    distance_km: float
    directions_url: str


def find_nearby_shelters(db: Session, disaster: Disaster, radius_km: float, *, include_full: bool = False,
                         min_available: int = 1, limit: int = 50) -> tuple[list[ShelterCandidate], dict[str, int]]:
    excluded: dict[str, int] = {}
    out: list[ShelterCandidate] = []
    if not disaster.has_coordinates:
        return out, excluded
    for sh in db.scalars(select(Shelter)).all():
        if not sh.has_coordinates:
            _bump(excluded, "position unknown")
            continue
        dist = haversine_km(disaster.latitude, disaster.longitude, sh.latitude, sh.longitude)
        if dist > radius_km:
            _bump(excluded, "outside radius")
            continue
        if not include_full and sh.available_capacity < max(1, min_available):
            _bump(excluded, "no available capacity")
            continue
        out.append(ShelterCandidate(sh, round(dist, 1), osm_directions_url(disaster.latitude, disaster.longitude, sh.latitude, sh.longitude)))
    out.sort(key=lambda c: (c.distance_km, -c.shelter.available_capacity, c.shelter.id))
    return out[:limit], excluded
