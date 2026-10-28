"""Geocoding, routing and the map-ready feature feed."""
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from ..constants import BASIS_ESTIMATE, BASIS_EXTERNAL, BASIS_OPERATIONAL, STATUS_RULE
from ..dependencies import DbSession, OperatorDep, OptionalOperatorDep, RateLimiter, audit, commit
from ..models import Disaster, ExternalEvent, InventoryItem, ResourceAllocation, Shelter, Volunteer
from ..schemas_ext import GeocodeApplyRequest
from ..services import geocoding, routing
from ..services.geo import coarsen
from ..services.httpclient import ExternalApiError
from .external import event_out

router = APIRouter(tags=["Geography"])
_geocode_limit = RateLimiter("geocode", 15)
_route_limit = RateLimiter("route", 30)

LAYERS = ("disasters", "external", "shelters", "inventory", "allocations", "volunteers")


@router.get("/geo/geocode")
def geocode(db: DbSession, q: str = Query(min_length=3, max_length=200), _rl=Depends(_geocode_limit)):
    """Address / place search (Nominatim). Results are cached; an ambiguous query is flagged, never auto-resolved."""
    try:
        return geocoding.geocode(db, q)
    except ExternalApiError as exc:
        raise HTTPException(422 if exc.kind == "malformed" and exc.status is None else 502, f"Geocoding unavailable: {exc.message}") from exc


@router.post("/geo/geocode-missing")
def geocode_missing(body: GeocodeApplyRequest, db: DbSession, op: OperatorDep):
    """Fill in coordinates for records that only have a place NAME. Never overwrites existing coordinates;
    ambiguous or empty results are reported back for a person to resolve on the map."""
    model = {"disasters": Disaster, "shelters": Shelter, "volunteers": Volunteer, "inventory": InventoryItem}[body.entity]
    name_col = "storage_location" if body.entity == "inventory" else "location"
    rows = db.scalars(select(model).where(model.latitude.is_(None)).order_by(model.id).limit(body.limit)).all()
    applied, ambiguous, not_found, errors = [], [], [], []
    for r in rows:
        place = getattr(r, name_col)
        try:
            res = geocoding.geocode(db, place)
        except ExternalApiError as exc:
            errors.append({"id": r.id, "place": place, "error": exc.message})
            if exc.kind in ("rate_limited", "network", "timeout"):
                break  # stop hammering a service that is failing
            continue
        if not res["candidates"]:
            not_found.append({"id": r.id, "place": place})
        elif res["ambiguous"]:
            ambiguous.append({"id": r.id, "place": place, "candidates": res["candidates"][:3]})
        else:
            c = res["candidates"][0]
            r.latitude, r.longitude, r.location_source, r.location_approximate = c["latitude"], c["longitude"], "geocoded", True
            applied.append({"id": r.id, "place": place, "matched": c["display_name"]})
    audit(db, op.name, "geocode.apply", body.entity, None, applied=len(applied), ambiguous=len(ambiguous))
    commit(db)
    return {"applied": applied, "ambiguous": ambiguous, "not_found": not_found, "errors": errors,
            "note": "Geocoded positions are approximate (place-level). Ambiguous results were NOT applied."}


@router.get("/geo/route")
def get_route(db: DbSession, from_lat: float = Query(ge=-90, le=90), from_lng: float = Query(ge=-180, le=180),
              to_lat: float = Query(ge=-90, le=90), to_lng: float = Query(ge=-180, le=180), geometry: bool = True,
              _rl=Depends(_route_limit)):
    try:
        return routing.route(db, from_lat, from_lng, to_lat, to_lng, with_geometry=geometry)
    except ExternalApiError as exc:
        raise HTTPException(502, f"Routing unavailable: {exc.message}") from exc


def _f(kind, id_, lat, lng, title, **kw):
    return {"kind": kind, "id": id_, "latitude": lat, "longitude": lng, "title": title, **kw}


@router.get("/map/features")
def map_features(
    db: DbSession, operator: OptionalOperatorDep,
    layers: str = ",".join(LAYERS[:5]), severity: str | None = None, source: str | None = None, event_type: str | None = None,
    since: date | None = None, until: date | None = None, status: str | None = Query(None, pattern="^(Active|Monitoring|Resolved)$"), include_resolved: bool = False,
    west: float | None = Query(None, ge=-180, le=180), south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180), north: float | None = Query(None, ge=-90, le=90),
):
    """Everything with a known position, ready to plot. Active layers exclude resolved incidents. Volunteer positions
    are only returned to authorised operators and are rounded to ~1 km."""
    if since and until and since > until:
        raise HTTPException(422, "since must be on or before until.")
    wanted = {x for x in layers.split(",") if x in LAYERS}

    def inside(lat, lng):
        if None not in (south, north) and not (south <= lat <= north):
            return False
        if None not in (west, east):
            return (west <= lng <= east) if west <= east else (lng >= west or lng <= east)
        return True

    features, missing = [], {}
    if "disasters" in wanted:
        stmt = select(Disaster)
        if status:
            stmt = stmt.where(Disaster.status == status)
        elif not include_resolved:
            stmt = stmt.where(Disaster.status != "Resolved")
        if since:
            stmt = stmt.where(Disaster.created_at >= datetime.combine(since, time.min, tzinfo=timezone.utc))
        if until:
            stmt = stmt.where(Disaster.created_at <= datetime.combine(until, time.max, tzinfo=timezone.utc))
        if severity:
            stmt = stmt.where(Disaster.severity == severity)
        for d in db.scalars(stmt):
            if not d.has_coordinates:
                missing["disasters"] = missing.get("disasters", 0) + 1
            elif inside(d.latitude, d.longitude):
                features.append(_f("disaster", d.id, d.latitude, d.longitude, d.label, status=d.status, severity=d.severity,
                                   source="ReliefSync", label=BASIS_OPERATIONAL, timestamp=d.updated_at, approximate=d.location_approximate,
                                   details={"people_affected": d.people_affected, "priority_score": d.priority_score, "priority_level": d.priority_level,
                                            "origin": d.origin, "location_source": d.location_source, "description": d.description}))
    if "external" in wanted:
        stmt = select(ExternalEvent).where(ExternalEvent.duplicate_of_id.is_(None), ExternalEvent.review_status.notin_(("Dismissed", "Promoted")))
        if severity:
            stmt = stmt.where(ExternalEvent.severity_estimate == severity)
        if source:
            stmt = stmt.where(ExternalEvent.source == source)
        if event_type:
            stmt = stmt.where(ExternalEvent.event_type == event_type)
        if since:
            stmt = stmt.where(ExternalEvent.observed_at >= datetime.combine(since, time.min, tzinfo=timezone.utc))
        if until:
            stmt = stmt.where(ExternalEvent.observed_at <= datetime.combine(until, time.max, tzinfo=timezone.utc))
        for e in db.scalars(stmt.order_by(ExternalEvent.observed_at.desc().nullslast()).limit(1000)):
            if inside(e.latitude, e.longitude):
                o = event_out(e)
                features.append(_f("external", e.id, e.latitude, e.longitude, e.title, status=e.review_status, severity=e.severity_estimate,
                                   source=e.source.upper(), label=BASIS_EXTERNAL, severity_label=BASIS_ESTIMATE, timestamp=e.observed_at,
                                   retrieved_at=e.retrieved_at, url=e.url, approximate=o["location_approximate"],
                                   details={"event_type": e.event_type, "magnitude": e.magnitude, "source_alert_level": e.source_alert_level, "country": e.country}))
    if "shelters" in wanted:
        for s in db.scalars(select(Shelter)):
            if not s.has_coordinates:
                missing["shelters"] = missing.get("shelters", 0) + 1
            elif inside(s.latitude, s.longitude):
                features.append(_f("shelter", s.id, s.latitude, s.longitude, s.name, status="Open" if s.available_capacity > 0 else "Full",
                                   source="ReliefSync", label=BASIS_OPERATIONAL, timestamp=s.updated_at, approximate=s.location_approximate,
                                   details={"location": s.location, "total_capacity": s.total_capacity, "current_occupancy": s.current_occupancy,
                                            "available_capacity": s.available_capacity, "contact": s.contact}))
    if "inventory" in wanted:
        for i in db.scalars(select(InventoryItem)):
            if not i.has_coordinates:
                missing["inventory"] = missing.get("inventory", 0) + 1
            elif inside(i.latitude, i.longitude):
                features.append(_f("inventory", i.id, i.latitude, i.longitude, f"{i.name} ({i.storage_location})", status="Low stock" if i.is_low_stock else "In stock",
                                   source="ReliefSync", label=BASIS_OPERATIONAL, timestamp=i.updated_at, approximate=i.location_approximate,
                                   details={"category": i.category, "quantity": i.quantity, "unit": i.unit, "storage_location": i.storage_location}))
    if "allocations" in wanted:
        stmt = select(ResourceAllocation).where(ResourceAllocation.status.in_(("Confirmed", "In Transit")))
        for a in db.scalars(stmt):
            if a.disaster.status == "Resolved":
                continue
            if a.destination_latitude is None:
                missing["allocations"] = missing.get("allocations", 0) + 1
            elif inside(a.destination_latitude, a.destination_longitude):
                features.append(_f("allocation", a.id, a.destination_latitude, a.destination_longitude, f"{a.item_name} to {a.destination}", status=a.status,
                                   source="ReliefSync", label=BASIS_OPERATIONAL, timestamp=a.updated_at, approximate=a.destination_location_source == "geocoded",
                                   details={"disaster": a.disaster_label, "quantity": a.quantity, "unit": a.item_unit}))
    volunteers_hidden = "volunteers" in wanted and operator is None
    if "volunteers" in wanted and operator is not None:
        for v in db.scalars(select(Volunteer).where(Volunteer.availability != "Unavailable")):
            if not v.has_coordinates:
                missing["volunteers"] = missing.get("volunteers", 0) + 1
                continue
            lat, lng = coarsen(v.latitude, v.longitude, 2)
            if inside(lat, lng):
                features.append(_f("volunteer", v.id, lat, lng, f"Volunteer #{v.id}", status=v.availability, source="ReliefSync", label=BASIS_OPERATIONAL,
                                   approximate=True, details={"skills": v.skills, "note": "Position rounded to about 1 km for privacy."}))
    return {"features": features, "count": len(features), "missing_coordinates": missing, "volunteers_hidden": volunteers_hidden,
            "generated_at": datetime.now(timezone.utc), "status_rule": STATUS_RULE}
