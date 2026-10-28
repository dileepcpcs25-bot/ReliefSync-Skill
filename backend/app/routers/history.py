"""Historical-event lookup and operator-only resource matching. Resource status is current, not historical."""
import json
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from ..dependencies import DbSession, OperatorDep
from ..models import Disaster, ExternalEvent, Shelter, Volunteer, Assignment
from ..services.geo import haversine_km

router = APIRouter(prefix="/history", tags=["Historical events and resources"])


def _in_box(lat: float, lng: float, west, south, east, north) -> bool:
    if south is not None and not south <= lat <= north:
        return False
    if west is not None and not (west <= lng <= east if west <= east else (lng >= west or lng <= east)):
        return False
    return True


@router.get("/events")
def historical_events(db: DbSession, _op: OperatorDep, since: date | None = None, until: date | None = None,
                      region: str | None = None, limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0),
                      west: float | None = Query(None, ge=-180, le=180), south: float | None = Query(None, ge=-90, le=90),
                      east: float | None = Query(None, ge=-180, le=180), north: float | None = Query(None, ge=-90, le=90)):
    """Return previously recorded operational incidents and fetched third-party events. No history is fabricated."""
    if (south is None) != (north is None) or (west is None) != (east is None):
        raise HTTPException(422, "Provide both bounds for each coordinate axis.")
    if since and until and since > until:
        raise HTTPException(422, "since must be on or before until.")
    start = datetime.combine(since, time.min, tzinfo=timezone.utc) if since else None
    end = datetime.combine(until, time.max, tzinfo=timezone.utc) if until else None
    incidents = db.scalars(select(Disaster).order_by(Disaster.created_at.desc(), Disaster.id.desc())).all()
    external = db.scalars(select(ExternalEvent).order_by(ExternalEvent.observed_at.desc().nullslast(), ExternalEvent.id.desc())).all()
    rows = []
    for d in incidents:
        at = d.created_at
        if (start and at < start) or (end and at > end):
            continue
        if (west is not None or south is not None) and not d.has_coordinates:
            continue
        if d.has_coordinates and not _in_box(d.latitude, d.longitude, west, south, east, north):
            continue
        rows.append({"key": f"local:{d.id}", "record_id": d.id, "event_source": "local", "source": "ReliefSync operational record",
                     "title": d.label, "event_type": d.disaster_type, "location": d.location, "status": d.status,
                     "severity": d.severity, "latitude": d.latitude, "longitude": d.longitude, "approximate": d.location_approximate,
                     "event_at": at, "date_basis": "record created in ReliefSync", "attribution": "Entered in ReliefSync; not independently verified."})
    for e in external:
        at = e.observed_at
        if at is None or (start and at < start) or (end and at > end):
            continue
        if not _in_box(e.latitude, e.longitude, west, south, east, north):
            continue
        rows.append({"key": f"external:{e.id}", "record_id": e.id, "event_source": "external", "source": e.source.upper(),
                     "title": e.title, "event_type": e.event_type, "location": e.country or "", "status": e.review_status,
                     "severity": e.severity_estimate, "latitude": e.latitude, "longitude": e.longitude,
                     "approximate": bool(json.loads(e.attributes or "{}").get("location_approximate", False)),
                     "event_at": at, "date_basis": "source-reported event time", "attribution": f"Third-party observation; unverified. {e.url or ''}"})
    rows.sort(key=lambda x: (x["event_at"], x["key"]), reverse=True)
    total = len(rows)
    return {"items": rows[offset:offset + limit], "total": total, "limit": limit, "offset": offset,
            "notice": "Event history is based on incident records and external observations already stored by ReliefSync. Volunteer and shelter statuses shown for a selected event are current records, not historical snapshots."}


@router.get("/events/{event_key}/resources")
def resources_for_event(event_key: str, db: DbSession, _op: OperatorDep,
                        radius_km: float = Query(100, gt=0, le=2000), include_unavailable: bool = True):
    """Show all located volunteers and shelters within radius; volunteer contact details and exact positions are withheld."""
    try:
        kind, raw_id = event_key.split(":", 1)
        event_id = int(raw_id)
    except (ValueError, TypeError):
        raise HTTPException(422, "Event key must be local:<id> or external:<id>.")
    if kind == "local":
        event = db.get(Disaster, event_id)
        if event is None:
            raise HTTPException(404, "Historical incident not found.")
        lat, lng, title, event_at, approximate = event.latitude, event.longitude, event.label, event.created_at, event.location_approximate
    elif kind == "external":
        event = db.get(ExternalEvent, event_id)
        if event is None:
            raise HTTPException(404, "Historical external observation not found.")
        lat, lng, title, event_at, approximate = event.latitude, event.longitude, event.title, event.observed_at, bool(json.loads(event.attributes or "{}").get("location_approximate", False))
    else:
        raise HTTPException(422, "Event key must be local:<id> or external:<id>.")
    if lat is None or lng is None:
        raise HTTPException(409, "This event has no verified point coordinates, so nearby resources cannot be matched.")

    busy_ids = set(db.scalars(select(Assignment.volunteer_id).where(Assignment.status == "Active")))
    volunteers, shelters = [], []
    all_volunteers = db.scalars(select(Volunteer).order_by(Volunteer.id)).all()
    all_shelters = db.scalars(select(Shelter).order_by(Shelter.id)).all()
    missing_volunteers = missing_shelters = 0
    for v in all_volunteers:
        if v.latitude is None or v.longitude is None:
            missing_volunteers += 1
            continue
        dist = haversine_km(lat, lng, v.latitude, v.longitude)
        if dist <= radius_km and (include_unavailable or v.availability == "Available"):
            volunteers.append({"id": v.id, "name": v.name, "skills": v.skills, "location": v.location,
                               "availability": v.availability, "assigned": v.id in busy_ids, "distance_km": round(dist, 1),
                               "current_record": True})
    for s in all_shelters:
        if s.latitude is None or s.longitude is None:
            missing_shelters += 1
            continue
        dist = haversine_km(lat, lng, s.latitude, s.longitude)
        if dist <= radius_km:
            shelters.append({"id": s.id, "name": s.name, "location": s.location, "distance_km": round(dist, 1),
                             "total_capacity": s.total_capacity, "current_occupancy": s.current_occupancy,
                             "available_capacity": s.available_capacity, "current_record": True})
    volunteers.sort(key=lambda x: (x["distance_km"], x["id"]))
    shelters.sort(key=lambda x: (x["distance_km"], x["id"]))
    return {"event": {"key": event_key, "title": title, "event_at": event_at, "approximate_location": approximate}, "radius_km": radius_km,
            "volunteers": volunteers, "shelters": shelters,
            "unlocated": {"volunteers": missing_volunteers, "shelters": missing_shelters},
            "distance_note": "Straight-line distance estimate from recorded coordinates, not travel distance. Unlocated records are not matched. Event coordinates may be approximate as reported by the source.",
            "resource_time_note": "Volunteer availability, active assignments, and shelter occupancy are current database values; ReliefSync has no past-state snapshots for these resources."}


