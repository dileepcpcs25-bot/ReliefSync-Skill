"""Stores normalised external observations: upsert by (source, external_id), cross-source duplicate linking,
fetch logging and cache/cooldown decisions. External rows live in their own table and are never merged into
operator-entered disasters (so manual incident details can never be overwritten by an API)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ExternalEvent, ExternalFetchLog
from .external_sources import SOURCES, NormalizedEvent, dumps_attributes
from .geo import haversine_km
from .httpclient import ExternalApiError
from .mongo_archive import archive_observations


def _now() -> datetime:
    return datetime.now(timezone.utc)


def upsert_events(db: Session, events: list[NormalizedEvent]) -> tuple[int, int]:
    """Insert new events, refresh existing ones. Review state (Reviewed/Dismissed/Promoted) is preserved."""
    new = updated = 0
    now = _now()
    for ev in events:
        row = db.scalar(select(ExternalEvent).where(ExternalEvent.source == ev.source, ExternalEvent.external_id == ev.external_id))
        if row is None:
            row = ExternalEvent(source=ev.source, external_id=ev.external_id, first_retrieved_at=now)
            db.add(row)
            new += 1
        else:
            updated += 1
        row.event_type = ev.event_type
        row.title = ev.title
        row.latitude, row.longitude = ev.latitude, ev.longitude
        row.depth_km, row.magnitude = ev.depth_km, ev.magnitude
        row.source_alert_level = ev.source_alert_level
        row.severity_estimate = ev.severity_estimate
        row.country = ev.country
        row.observed_at, row.source_updated_at = ev.observed_at, ev.source_updated_at
        row.url = ev.url
        row.attributes = dumps_attributes(ev.attributes)
        row.retrieved_at = now
    db.flush()
    return new, updated


def link_cross_source_duplicates(db: Session, *, max_km: float = 50.0, max_minutes: float = 15.0, max_mag_diff: float = 0.8) -> int:
    """Mark GDACS earthquakes that are the same physical event as a USGS earthquake (USGS is the primary record).
    Rule: both earthquakes, origin times within `max_minutes`, epicentres within `max_km`, magnitudes within
    `max_mag_diff`. Linked rows are hidden from default listings but kept (nothing is deleted)."""
    usgs = db.scalars(select(ExternalEvent).where(ExternalEvent.source == "usgs", ExternalEvent.event_type == "earthquake")).all()
    gdacs = db.scalars(select(ExternalEvent).where(ExternalEvent.source == "gdacs", ExternalEvent.event_type == "earthquake")).all()
    linked = 0
    for g in gdacs:
        if g.observed_at is None:
            continue
        match = None
        for u in usgs:
            if u.observed_at is None:
                continue
            if abs((u.observed_at - g.observed_at).total_seconds()) > max_minutes * 60:
                continue
            if haversine_km(u.latitude, u.longitude, g.latitude, g.longitude) > max_km:
                continue
            if u.magnitude is not None and g.magnitude is not None and abs(u.magnitude - g.magnitude) > max_mag_diff:
                continue
            match = u
            break
        new_id = match.id if match else None
        if g.duplicate_of_id != new_id:
            g.duplicate_of_id = new_id
            linked += 1 if new_id else 0
    db.flush()
    return linked


def last_log(db: Session, source: str, status: str | None = None) -> ExternalFetchLog | None:
    stmt = select(ExternalFetchLog).where(ExternalFetchLog.source == source)
    if status:
        stmt = stmt.where(ExternalFetchLog.status == status)
    return db.scalar(stmt.order_by(ExternalFetchLog.started_at.desc(), ExternalFetchLog.id.desc()).limit(1))


def refresh_source(db: Session, source: str, *, force: bool = False) -> dict:
    """Fetch one source unless a recent attempt makes that unnecessary (cache). Never fabricates data:
    on any failure the stored observations are left untouched and the error is reported."""
    spec = SOURCES[source]
    now = _now()
    if not spec["configured"]():
        log = ExternalFetchLog(source=source, started_at=now, finished_at=now, status="not_configured",
                               message="Not configured (see backend/.env.example).")
        db.add(log)
        db.commit()
        return {"source": source, "status": "not_configured", "message": log.message, "new": 0, "updated": 0, "skipped": 0}

    floor = timedelta(seconds=_floor())
    interval = timedelta(seconds=spec["interval"]())
    attempt, ok = last_log(db, source), last_log(db, source, "ok")
    if attempt and attempt.status in ("ok", "error") and attempt.finished_at and now - attempt.finished_at < floor:
        return _cached(source, ok, "A request was made moments ago; not repeating it (minimum interval between requests).")
    if not force and ok and ok.finished_at and now - ok.finished_at < interval:
        return _cached(source, ok, "Cached: refreshed recently (source refresh interval).")

    log = ExternalFetchLog(source=source, started_at=now, status="error")
    db.add(log)
    try:
        result = spec["fetch"]()
        new, updated = upsert_events(db, result.events)
        mongo_result = archive_observations(result.events)
        link_cross_source_duplicates(db)
        log.status, log.events_new, log.events_updated, log.events_skipped = "ok", new, updated, result.skipped
        log.message = "Truncated: the source returned its maximum number of events." if result.truncated else ""
    except ExternalApiError as exc:
        db.rollback()
        log = ExternalFetchLog(source=source, started_at=now, status="error", http_status=exc.status, message=exc.message)
        if exc.kind == "rate_limited" and exc.retry_after:
            log.message += f" (retry after {exc.retry_after}s)"
        db.add(log)
    except Exception as exc:  # defensive: an unexpected parser bug must not take the API down or corrupt data
        db.rollback()
        log = ExternalFetchLog(source=source, started_at=now, status="error", message=f"Unexpected error: {type(exc).__name__}")
        db.add(log)
    log.finished_at = _now()
    db.commit()
    return {
        "source": source, "status": log.status, "message": log.message, "http_status": log.http_status,
        "new": log.events_new, "updated": log.events_updated, "skipped": log.events_skipped,
        "mongodb_archive": mongo_result if log.status == "ok" else None,
        "last_success_at": (ok.finished_at if log.status != "ok" and ok else log.finished_at if log.status == "ok" else None),
    }


def _cached(source: str, ok: ExternalFetchLog | None, message: str) -> dict:
    return {"source": source, "status": "cached", "message": message, "new": 0, "updated": 0, "skipped": 0,
            "last_success_at": ok.finished_at if ok else None}


def _floor() -> int:
    from ..config import settings

    return settings.manual_refresh_floor_seconds


def refresh_all(db: Session, sources: list[str] | None = None, *, force: bool = False) -> list[dict]:
    return [refresh_source(db, s, force=force) for s in (sources or list(SOURCES))]


def source_status(db: Session) -> list[dict]:
    out = []
    now = _now()
    for key, spec in SOURCES.items():
        ok, attempt = last_log(db, key, "ok"), last_log(db, key)
        configured = spec["configured"]()
        interval = spec["interval"]()
        out.append({
            "source": key, "label": spec["label"], "configured": configured,
            "last_success_at": ok.finished_at if ok else None,
            "last_attempt_at": attempt.finished_at if attempt else None,
            "last_status": attempt.status if attempt else None,
            "last_message": attempt.message if attempt else "",
            "stale": (not ok) or (now - ok.finished_at > timedelta(seconds=interval)),
            "refresh_interval_seconds": interval,
        })
    return out
