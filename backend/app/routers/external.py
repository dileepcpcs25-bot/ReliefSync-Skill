import json
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from ..constants import BASIS_EXTERNAL, BASIS_ESTIMATE, Severity
from ..dependencies import DbSession, Limit, Offset, OperatorDep, RateLimiter, audit, commit, conflict, get_or_404, paginate
from ..models import Disaster, ExternalEvent
from ..schemas_ext import PromoteRequest, RefreshRequest, ReviewRequest
from ..services import external_ingest, weather
from ..services.mongo_archive import mongo_status
from ..services.external_sources import ATTRIBUTION, SOURCES
from ..services.httpclient import ExternalApiError

router = APIRouter(prefix="/external", tags=["External observations"])
_weather_limit = RateLimiter("weather", 30)


def event_out(e: ExternalEvent) -> dict:
    try:
        attrs = json.loads(e.attributes or "{}")
    except ValueError:
        attrs = {}
    return {
        "id": e.id, "source": e.source, "external_id": e.external_id, "event_type": e.event_type, "title": e.title,
        "latitude": e.latitude, "longitude": e.longitude, "depth_km": e.depth_km, "magnitude": e.magnitude,
        "source_alert_level": e.source_alert_level, "severity_estimate": e.severity_estimate, "country": e.country,
        "observed_at": e.observed_at, "source_updated_at": e.source_updated_at, "retrieved_at": e.retrieved_at,
        "url": e.url, "attributes": attrs, "review_status": e.review_status, "reviewed_by": e.reviewed_by,
        "duplicate_of_id": e.duplicate_of_id, "attribution": ATTRIBUTION.get(e.source, ""),
        "label": BASIS_EXTERNAL, "severity_label": BASIS_ESTIMATE,
        "location_approximate": bool(attrs.get("location_approximate")),
    }


@router.get("/status")
def status(db: DbSession):
    """Per-source freshness, last error and whether the source is configured."""
    return {"sources": external_ingest.source_status(db), "mongodb": mongo_status(),
            "notice": "External observations are automated, unverified data from third parties. They are not operational incidents."}


@router.get("/events")
def list_events(
    db: DbSession, limit: Limit = 100, offset: Offset = 0,
    source: str | None = None, event_type: str | None = None, severity: Severity | None = None,
    since: date | None = None, until: date | None = None, review_status: str | None = None,
    west: float | None = Query(None, ge=-180, le=180), south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180), north: float | None = Query(None, ge=-90, le=90),
    include_duplicates: bool = False, include_dismissed: bool = False,
):
    stmt = select(ExternalEvent).order_by(ExternalEvent.observed_at.desc().nullslast(), ExternalEvent.id.desc())
    if source:
        stmt = stmt.where(ExternalEvent.source == source)
    if event_type:
        stmt = stmt.where(ExternalEvent.event_type == event_type)
    if severity:
        stmt = stmt.where(ExternalEvent.severity_estimate == severity)
    if since:
        stmt = stmt.where(ExternalEvent.observed_at >= datetime.combine(since, time.min, tzinfo=timezone.utc))
    if until:
        stmt = stmt.where(ExternalEvent.observed_at <= datetime.combine(until, time.max, tzinfo=timezone.utc))
    if review_status:
        stmt = stmt.where(ExternalEvent.review_status == review_status)
    elif not include_dismissed:
        stmt = stmt.where(ExternalEvent.review_status != "Dismissed")
    if not include_duplicates:
        stmt = stmt.where(ExternalEvent.duplicate_of_id.is_(None))
    if None not in (south, north):
        stmt = stmt.where(ExternalEvent.latitude >= south, ExternalEvent.latitude <= north)
    if None not in (west, east):
        stmt = (stmt.where(ExternalEvent.longitude >= west, ExternalEvent.longitude <= east) if west <= east
                else stmt.where((ExternalEvent.longitude >= west) | (ExternalEvent.longitude <= east)))  # crosses the antimeridian
    page = paginate(db, stmt, limit, offset)
    page["items"] = [event_out(e) for e in page["items"]]
    page["notice"] = "External observations: unverified, third-party data."
    return page


@router.post("/refresh")
def refresh(body: RefreshRequest, db: DbSession, op: OperatorDep):
    """Manual refresh. Respects each source's cache interval (and a short minimum between requests)."""
    results = external_ingest.refresh_all(db, body.sources, force=body.force)
    audit(db, op.name, "external.refresh", "external_source", None, results=[{k: r[k] for k in ("source", "status", "new", "updated")} for r in results])
    commit(db)
    return {"results": results, "sources": external_ingest.source_status(db)}


@router.get("/events/{event_id}")
def get_event(event_id: int, db: DbSession):
    return event_out(get_or_404(db, ExternalEvent, event_id, "External event"))


@router.post("/events/{event_id}/review")
def review_event(event_id: int, body: ReviewRequest, db: DbSession, op: OperatorDep):
    e = get_or_404(db, ExternalEvent, event_id, "External event")
    if e.review_status == "Promoted":
        raise conflict("This observation was already promoted to an incident.")
    e.review_status, e.reviewed_by, e.reviewed_at = body.status, op.name, external_ingest._now()
    audit(db, op.name, "external.review", "external_event", e.id, status=body.status)
    commit(db)
    return event_out(e)


@router.post("/events/{event_id}/promote", status_code=201)
def promote_event(event_id: int, body: PromoteRequest, db: DbSession, op: OperatorDep):
    """An operator turns an observation into a NEW Monitoring incident. Nothing is ever promoted automatically,
    and later API updates never modify the incident that was created."""
    e = get_or_404(db, ExternalEvent, event_id, "External event")
    if e.review_status == "Promoted":
        raise conflict("This observation was already promoted.")
    d = Disaster(
        disaster_type=e.event_type.title()[:60], location=(e.country or e.title)[:120],
        severity=body.severity or e.severity_estimate, people_affected=body.people_affected, status="Monitoring",
        description=(f"Created by {op.name} from an UNVERIFIED {e.source.upper()} observation ({e.title}). "
                     f"Source: {e.url or e.source}. {body.notes}").strip()[:2000],
        latitude=e.latitude, longitude=e.longitude, location_source="external", location_approximate=True,
        origin="external_promoted", external_event_id=e.id,
    )
    db.add(d)
    db.flush()
    e.review_status, e.reviewed_by, e.reviewed_at = "Promoted", op.name, external_ingest._now()
    audit(db, op.name, "external.promote", "external_event", e.id, disaster_id=d.id)
    commit(db)
    return {"disaster_id": d.id, "message": "Incident created with status Monitoring. Review and verify it before acting on it."}


@router.get("/weather")
def get_weather(db: DbSession, lat: float = Query(ge=-90, le=90), lng: float = Query(ge=-180, le=180), _rl=Depends(_weather_limit)):
    try:
        return weather.get_weather(db, lat, lng)
    except ExternalApiError as exc:
        raise HTTPException(502, f"Weather service unavailable: {exc.message}") from exc
