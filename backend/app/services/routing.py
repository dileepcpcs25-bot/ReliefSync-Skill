"""Road distance / travel-time ESTIMATES from an OSRM-compatible routing service.

Defaults to the public OSRM demo server, which is meant for light use only: responses are cached and the
base URL is configurable (OSRM_URL) so a self-hosted instance can be used. Results are always labelled as
provider estimates; straight-line distance is never presented as travel distance."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import settings
from . import httpclient
from .api_cache import cache_get, cache_put
from .geo import valid_coordinates
from .httpclient import ExternalApiError

PROVIDER_LABEL = "Estimate from routing provider (OSRM, OpenStreetMap data) - actual conditions may differ"


def parse_osrm(payload: object, with_geometry: bool) -> dict:
    if not isinstance(payload, dict) or payload.get("code") != "Ok" or not payload.get("routes"):
        code = payload.get("code") if isinstance(payload, dict) else "invalid"
        raise ExternalApiError("malformed", f"No route available (provider code: {code})")
    route = payload["routes"][0]
    try:
        out = {"distance_km": round(float(route["distance"]) / 1000.0, 2), "duration_min": round(float(route["duration"]) / 60.0, 1)}
    except (KeyError, TypeError, ValueError) as exc:
        raise ExternalApiError("malformed", "Routing response missing distance/duration") from exc
    if with_geometry:
        geom = route.get("geometry")
        coords = geom.get("coordinates") if isinstance(geom, dict) else None
        out["geometry"] = [[c[1], c[0]] for c in coords if isinstance(c, list) and len(c) >= 2] if coords else []
    return out


def route(db: Session, from_lat: float, from_lng: float, to_lat: float, to_lng: float, *, with_geometry: bool = False) -> dict:
    if not settings.routing_enabled:
        raise ExternalApiError("not_configured", "Routing is disabled (ROUTING_ENABLED=false).")
    if not (valid_coordinates(from_lat, from_lng) and valid_coordinates(to_lat, to_lng)):
        raise ExternalApiError("malformed", "Invalid coordinates")
    key = f"route:{from_lat:.4f},{from_lng:.4f}>{to_lat:.4f},{to_lng:.4f}:{int(with_geometry)}"
    hit = cache_get(db, key)
    if hit:
        data, fetched = hit
        return {**data, "provider": "osrm", "label": PROVIDER_LABEL, "cached": True, "retrieved_at": fetched}
    url = f"{settings.osrm_url.rstrip('/')}/route/v1/driving/{from_lng:.6f},{from_lat:.6f};{to_lng:.6f},{to_lat:.6f}"
    params = {"overview": "simplified" if with_geometry else "false", "geometries": "geojson"}
    data = parse_osrm(httpclient.get_json(url, params=params), with_geometry)
    fetched = cache_put(db, key, "osrm", data, settings.route_cache_seconds)
    return {**data, "provider": "osrm", "label": PROVIDER_LABEL, "cached": False, "retrieved_at": fetched}
