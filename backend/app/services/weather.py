"""Current weather and today's forecast totals from Open-Meteo (free for non-commercial use, no API key;
attribution CC BY 4.0). An observation/forecast from a weather model - not a local official warning."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import settings
from . import httpclient
from .api_cache import cache_get, cache_put
from .geo import valid_coordinates
from .httpclient import ExternalApiError

ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"
WMO = {0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Rime fog", 51: "Light drizzle",
       53: "Drizzle", 55: "Dense drizzle", 61: "Slight rain", 63: "Rain", 65: "Heavy rain", 71: "Slight snow", 73: "Snow",
       75: "Heavy snow", 80: "Rain showers", 81: "Heavy rain showers", 82: "Violent rain showers", 95: "Thunderstorm",
       96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail"}


def parse_open_meteo(payload: object) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("current"), dict):
        raise ExternalApiError("malformed", "Weather response has no 'current' block")
    cur, units = payload["current"], payload.get("current_units") or {}
    daily = payload.get("daily") if isinstance(payload.get("daily"), dict) else {}

    def first(key):
        v = daily.get(key)
        return v[0] if isinstance(v, list) and v else None

    code = cur.get("weather_code")
    return {
        "observed_at": cur.get("time"),
        "temperature_c": cur.get("temperature_2m"),
        "wind_speed_kmh": cur.get("wind_speed_10m"),
        "wind_gusts_kmh": cur.get("wind_gusts_10m"),
        "precipitation_mm": cur.get("precipitation"),
        "weather_code": code,
        "summary": WMO.get(code, "Unknown") if isinstance(code, int) else None,
        "today_precipitation_sum_mm": first("precipitation_sum"),
        "today_wind_gusts_max_kmh": first("wind_gusts_10m_max"),
        "units": {k: v for k, v in units.items() if k != "time"},
    }


def get_weather(db: Session, lat: float, lng: float) -> dict:
    if not valid_coordinates(lat, lng):
        raise ExternalApiError("malformed", "Invalid coordinates")
    key = f"weather:{lat:.2f},{lng:.2f}"  # ~1 km grid: nearby requests share one cached answer
    hit = cache_get(db, key)
    if hit:
        data, fetched = hit
        cached = True
    else:
        payload = httpclient.get_json(settings.open_meteo_url, params={
            "latitude": round(lat, 4), "longitude": round(lng, 4), "timezone": "GMT",
            "current": "temperature_2m,precipitation,weather_code,wind_speed_10m,wind_gusts_10m",
            "daily": "precipitation_sum,wind_gusts_10m_max", "forecast_days": 1,
        })
        data = parse_open_meteo(payload)
        fetched = cache_put(db, key, "open-meteo", data, settings.weather_cache_seconds)
        cached = False
    return {**data, "source": "open-meteo", "attribution": ATTRIBUTION, "cached": cached, "retrieved_at": fetched,
            "label": "External observation / model forecast (unverified)"}
