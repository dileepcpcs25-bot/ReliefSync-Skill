"""Tiny DB-backed cache for geocoding, routing and weather responses."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ApiCache


def _now() -> datetime:
    return datetime.now(timezone.utc)


def cache_get(db: Session, key: str, *, allow_stale: bool = False) -> tuple[object, datetime] | None:
    row = db.scalar(select(ApiCache).where(ApiCache.cache_key == key))
    if row is None or (not allow_stale and row.expires_at <= _now()):
        return None
    try:
        return json.loads(row.payload), row.fetched_at
    except ValueError:
        return None


def cache_put(db: Session, key: str, source: str, payload: object, ttl_seconds: int) -> datetime:
    now = _now()
    row = db.scalar(select(ApiCache).where(ApiCache.cache_key == key))
    if row is None:
        row = ApiCache(cache_key=key, source=source, payload="", fetched_at=now, expires_at=now)
        db.add(row)
    row.payload = json.dumps(payload)
    row.fetched_at = now
    row.expires_at = now + timedelta(seconds=ttl_seconds)
    db.commit()
    return now
