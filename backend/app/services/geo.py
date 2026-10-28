"""Pure geographic helpers (no database or web imports).

Distances use the haversine great-circle formula on a sphere of radius 6371.0088 km (the IUGG mean
Earth radius). It is accurate to roughly 0.5 % - fine for "which resources are near" ranking, but it is a
STRAIGHT-LINE distance, never a travel distance.
"""
from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088


def valid_coordinates(lat, lng) -> bool:
    """True only for finite numbers inside the WGS84 ranges. Bools and strings are rejected."""
    for v in (lat, lng):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    if not (valid_coordinates(lat1, lng1) and valid_coordinates(lat2, lng2)):
        raise ValueError("Invalid coordinates")
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def bounding_box(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    """(south, west, north, east) box that fully contains the circle; used as a cheap SQL pre-filter.
    Near the poles or the antimeridian the longitude span is widened to the full range (safe, never too small)."""
    dlat = math.degrees(radius_km / EARTH_RADIUS_KM)
    south, north = max(-90.0, lat - dlat), min(90.0, lat + dlat)
    if north >= 90.0 or south <= -90.0:
        return south, -180.0, north, 180.0
    dlng = math.degrees(radius_km / (EARTH_RADIUS_KM * math.cos(math.radians(lat))))
    if dlng >= 180.0 or lng - dlng < -180.0 or lng + dlng > 180.0:
        return south, -180.0, north, 180.0
    return south, lng - dlng, north, lng + dlng


def within_radius(lat1, lng1, lat2, lng2, radius_km: float) -> bool:
    if not (valid_coordinates(lat1, lng1) and valid_coordinates(lat2, lng2)):
        return False
    return haversine_km(lat1, lng1, lat2, lng2) <= radius_km


def coarsen(lat: float, lng: float, decimals: int = 1) -> tuple[float, float]:
    """Round coordinates (1 decimal ~ 11 km, 2 decimals ~ 1.1 km) so exact positions are not stored/exposed."""
    return round(lat, decimals), round(lng, decimals)


def osm_directions_url(from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> str:
    """Link to openstreetmap.org's directions UI (a link only - no data is fetched)."""
    return (
        "https://www.openstreetmap.org/directions?engine=fossgis_osrm_car"
        f"&route={from_lat:.5f}%2C{from_lng:.5f}%3B{to_lat:.5f}%2C{to_lng:.5f}"
    )
