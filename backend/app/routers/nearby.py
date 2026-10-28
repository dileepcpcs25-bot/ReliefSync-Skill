from fastapi import APIRouter, HTTPException, Query

from ..constants import BASIS_ESTIMATE, BASIS_OPERATIONAL, STATUS_RULE
from ..config import settings
from ..dependencies import DbSession, OperatorDep, audit, commit, conflict, get_or_404
from ..models import Disaster
from ..schemas import AssignmentOut
from ..schemas_ext import AssignApproval
from ..services import routing
from ..services.geo import haversine_km
from ..services.httpclient import ExternalApiError
from ..services.nearby import find_nearby_shelters, find_nearby_volunteers
from .assignments import assign_volunteer

router = APIRouter(prefix="/disasters/{disaster_id}", tags=["Nearby resources"])
RadiusQ = Query(default=None, gt=0)


def _radius(r: float | None) -> float:
    r = r or settings.default_radius_km
    if r > settings.max_radius_km:
        raise HTTPException(422, f"Radius cannot exceed {settings.max_radius_km:g} km.")
    return r


def _active_with_position(d: Disaster) -> None:
    if d.status == "Resolved":
        raise conflict("Resolved incidents are excluded from nearby-resource recommendations.")
    if not d.has_coordinates:
        raise conflict("This incident has no coordinates yet. Set its location on the map first.")


@router.get("/nearby-volunteers")
def nearby_volunteers(disaster_id: int, db: DbSession, _op: OperatorDep, radius_km: float | None = RadiusQ,
                      skills: str | None = None, require_skill_match: bool = False, limit: int = Query(50, ge=1, le=200)):
    """Authorised operators only. Returns ranked candidates WITHOUT phone numbers or coordinates."""
    d = get_or_404(db, Disaster, disaster_id, "Disaster")
    _active_with_position(d)
    radius = _radius(radius_km)
    res = find_nearby_volunteers(db, d, radius, skills, require_skill_match, limit)
    return {
        "disaster": {"id": d.id, "label": d.label, "status": d.status, "approximate_location": d.location_approximate},
        "radius_km": radius, "distance_note": "Straight-line distance (estimate), not travel distance.", "wanted_skills": res.wanted,
        "ranking": "score = 0.6 x skill suitability + 0.4 x proximity", "label": BASIS_ESTIMATE,
        "candidates": [
            {"volunteer_id": c.volunteer.id, "name": c.volunteer.name, "skills": c.volunteer.skills, "distance_km": c.distance_km,
             "matched_skills": c.matched_skills, "suitability": c.suitability, "score": c.score, "suggested_role": c.role, "reason": c.reason,
             "sms_opt_in": c.volunteer.sms_opt_in}
            for c in res.candidates
        ],
        "excluded": res.excluded, "status_rule": STATUS_RULE,
    }


@router.post("/nearby-volunteers/approve-assignment", response_model=AssignmentOut, status_code=201)
def approve_assignment(disaster_id: int, body: AssignApproval, db: DbSession, op: OperatorDep):
    """Operator approves one recommended volunteer. Everything is RE-CHECKED now: incident still active, volunteer
    still available with no active assignment, and still inside the radius."""
    if not body.confirm:
        raise HTTPException(422, "Explicit confirmation is required (confirm = true).")
    d = get_or_404(db, Disaster, disaster_id, "Disaster")
    _active_with_position(d)
    res = find_nearby_volunteers(db, d, _radius(body.radius_km), None, False, 1000)
    match = next((c for c in res.candidates if c.volunteer.id == body.volunteer_id), None)
    if match is None:
        raise conflict("This volunteer is no longer an eligible nearby candidate (unavailable, already assigned, or outside the radius).")
    assignment = assign_volunteer(db, body.volunteer_id, disaster_id, body.role)
    audit(db, op.name, "assignment.approved_nearby", "assignment", assignment.id, volunteer_id=body.volunteer_id, disaster_id=disaster_id, distance_km=match.distance_km)
    commit(db)
    return assignment


@router.get("/nearby-shelters")
def nearby_shelters(disaster_id: int, db: DbSession, radius_km: float | None = RadiusQ, include_full: bool = False,
                    with_routes: bool = False, limit: int = Query(20, ge=1, le=100)):
    d = get_or_404(db, Disaster, disaster_id, "Disaster")
    _active_with_position(d)
    radius = _radius(radius_km)
    found, excluded = find_nearby_shelters(db, d, radius, include_full=include_full, limit=limit)
    items = []
    for i, c in enumerate(found):
        sh = c.shelter
        item = {"shelter_id": sh.id, "name": sh.name, "location": sh.location, "latitude": sh.latitude, "longitude": sh.longitude,
                "approximate_location": sh.location_approximate, "straight_line_km": c.distance_km,
                "distance_label": "Straight-line distance (estimate), not travel distance",
                "total_capacity": sh.total_capacity, "current_occupancy": sh.current_occupancy, "available_capacity": sh.available_capacity,
                "contact": sh.contact, "last_updated": sh.updated_at, "directions_url": c.directions_url, "label": BASIS_OPERATIONAL,
                "route": None, "route_error": None}
        if with_routes and i < 5:  # public routing servers are for light use: only the nearest few
            try:
                item["route"] = routing.route(db, d.latitude, d.longitude, sh.latitude, sh.longitude, with_geometry=True)
            except ExternalApiError as exc:
                item["route_error"] = exc.message
        items.append(item)
    return {"disaster": {"id": d.id, "label": d.label, "latitude": d.latitude, "longitude": d.longitude}, "radius_km": radius,
            "items": items, "excluded": excluded,
            "note": "Capacity is the last value recorded by an operator; confirm with the shelter before directing anyone there.",
            "status_rule": STATUS_RULE}
