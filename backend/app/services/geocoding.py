"""Forward geocoding through Nominatim (OpenStreetMap), following the public usage policy:
identifying User-Agent, max ~1 request/second (global lock), results cached, no bulk or autocomplete use.
Ambiguous answers are reported explicitly - the caller (a person) chooses; nothing is auto-assumed."""
from __future__ import annotations

import threading
import time
from datetime import datetime

from sqlalchemy.orm import Session

from ..config import settings
from . import httpclient
from .api_cache import cache_get, cache_put
from .geo import haversine_km, valid_coordinates
from .httpclient import ExternalApiError

ATTRIBUTION = "Geocoding: Nominatim / (c) OpenStreetMap contributors (ODbL)"
_lock = threading.Lock()
_last_call = 0.0


def _throttle() -> None:
    global _last_call
    with _lock:
        wait = settings.nominatim_min_interval - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def parse_nominatim(payload: object) -> list[dict]:
    if not isinstance(payload, list):
        raise ExternalApiError("malformed", "Geocoder response was not a list")
    out = []
    for item in payload:
        try:
            lat, lng = float(item["lat"]), float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not valid_coordinates(lat, lng):
            continue
        addr = item.get("address") if isinstance(item.get("address"), dict) else {}
        out.append({
            "latitude": lat, "longitude": lng,
            "display_name": str(item.get("display_name", ""))[:300],
            "type": item.get("type") or item.get("category"),
            "importance": float(item["importance"]) if isinstance(item.get("importance"), (int, float)) else 0.0,
            "country": addr.get("country"),
            "osm_ref": f"{item.get('osm_type', '')}/{item.get('osm_id', '')}",
        })
    return out


def is_ambiguous(candidates: list[dict]) -> bool:
    """Ambiguous when a second result is about as important as the first AND lies in a different place (>10 km)."""
    if len(candidates) < 2:
        return False
    a, b = candidates[0], candidates[1]
    comparable = b["importance"] >= 0.8 * a["importance"]
    far = haversine_km(a["latitude"], a["longitude"], b["latitude"], b["longitude"]) > 10.0
    return comparable and far


def geocode(db: Session, query: str, limit: int = 5) -> dict:
    q = " ".join(query.split())
    if len(q) < 3:
        raise ExternalApiError("malformed", "Enter at least 3 characters to search for a place.")
    key = f"geocode:{q.lower()}:{limit}"
    hit = cache_get(db, key)
    if hit:
        candidates, fetched = hit
        cached = True
    else:
        _throttle()
        payload = httpclient.get_json(
            settings.nominatim_url, params={"q": q, "format": "jsonv2", "limit": limit, "addressdetails": 1}
        )
        candidates = parse_nominatim(payload)
        ttl = settings.geocode_cache_days * 86400 if candidates else 86400  # remember "not found" for a day
        fetched = cache_put(db, key, "nominatim", candidates, ttl)
        cached = False
    return {
        "query": q, "source": "nominatim", "attribution": ATTRIBUTION, "cached": cached,
        "retrieved_at": fetched if isinstance(fetched, datetime) else None,
        "candidates": candidates, "ambiguous": is_ambiguous(candidates),
    }
