"""Parsers (pure functions) and fetchers for external disaster-observation sources.

Documented sources used (checked against each provider's current documentation):
* USGS Earthquake Hazards Program - GeoJSON summary feeds
    https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{magnitude}_{period}.geojson
    feature.id, properties{mag, place, time(ms), updated(ms), url, alert, tsunami, sig, status, type, title, magType},
    geometry.coordinates = [longitude, latitude, depth_km]. An unknown feed name answers HTTP 200 with a TEXT body.
* GDACS - https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=EQ;TC;...&fromdate=..&todate=..
    free to use with attribution ("Global Disaster Alert and Coordination System, GDACS"); max 100 events per
    request; GeoJSON features with properties{eventtype, eventid, episodeid, name, alertlevel, country, iso3,
    fromdate, todate, datemodified, iscurrent, severitydata{severity, severitytext, severityunit}, url{report, details}}.
* NASA FIRMS (needs a free MAP_KEY) - /api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{days 1-5}.
All sources are UNVERIFIED observations/automated alerts - see README.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..config import settings
from . import httpclient
from .geo import valid_coordinates
from .httpclient import ExternalApiError

SEVERITY_ORDER = ["Low", "Medium", "High", "Critical"]
GDACS_TYPES = {"EQ": "earthquake", "TC": "tropical cyclone", "FL": "flood", "VO": "volcano", "DR": "drought", "WF": "wildfire"}
GDACS_LEVEL_TO_SEVERITY = {"green": "Low", "orange": "High", "red": "Critical"}
USGS_PAGER_TO_SEVERITY = {"green": "Low", "yellow": "Medium", "orange": "High", "red": "Critical"}

ATTRIBUTION = {
    "usgs": "Earthquake data: U.S. Geological Survey (USGS), public domain.",
    "gdacs": "Global Disaster Alert and Coordination System, GDACS (https://www.gdacs.org). Automated alerts; may contain uncertainty.",
    "firms": "Fire data: NASA FIRMS / LANCE, NASA Earth Science Data and Information System (ESDIS).",
    "eonet": "Natural event metadata: NASA Earth Observatory Natural Event Tracker (EONET) API v3.",
}


@dataclass
class NormalizedEvent:
    source: str
    external_id: str
    event_type: str
    title: str
    latitude: float
    longitude: float
    severity_estimate: str
    observed_at: datetime | None = None
    source_updated_at: datetime | None = None
    depth_km: float | None = None
    magnitude: float | None = None
    source_alert_level: str | None = None
    country: str | None = None
    url: str | None = None
    attributes: dict = field(default_factory=dict)


@dataclass
class ParseResult:
    events: list[NormalizedEvent]
    skipped: int = 0  # features dropped because of missing/invalid coordinates or ids
    truncated: bool = False


# ------------------------------------------------------------------ helpers
def _num(v) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def _ms_to_dt(v) -> datetime | None:
    n = _num(v)
    if n is None:
        return None
    try:
        return datetime.fromtimestamp(n / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _iso_to_dt(v) -> datetime | None:
    if not isinstance(v, str) or not v.strip():
        return None
    text = v.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # GDACS timestamps are UTC without an offset


def _max_severity(*values: str | None) -> str:
    ranked = [SEVERITY_ORDER.index(v) for v in values if v in SEVERITY_ORDER]
    return SEVERITY_ORDER[max(ranked)] if ranked else "Low"


def usgs_magnitude_band(mag: float | None) -> str:
    """Estimated severity band from magnitude alone (a coarse rule, NOT an impact assessment)."""
    if mag is None:
        return "Low"
    if mag >= 7.0:
        return "Critical"
    if mag >= 6.0:
        return "High"
    if mag >= 5.0:
        return "Medium"
    return "Low"


# ------------------------------------------------------------------ USGS
def parse_usgs(payload: object) -> ParseResult:
    if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
        raise ExternalApiError("malformed", "USGS response has no 'features' list")
    events, skipped = [], 0
    for feat in payload["features"]:
        try:
            props = feat.get("properties") or {}
            coords = (feat.get("geometry") or {}).get("coordinates") or []
            ext_id = feat.get("id")
            lng, lat = _num(coords[0]), _num(coords[1])
            if not ext_id or lat is None or lng is None or not valid_coordinates(lat, lng):
                skipped += 1
                continue
            mag = _num(props.get("mag"))
            alert = props.get("alert") if isinstance(props.get("alert"), str) else None
            etype = props.get("type") if isinstance(props.get("type"), str) else "earthquake"
            title = props.get("title") or props.get("place") or "Seismic event"
            events.append(
                NormalizedEvent(
                    source="usgs",
                    external_id=str(ext_id),
                    event_type=etype,
                    title=str(title)[:300],
                    latitude=lat,
                    longitude=lng,
                    depth_km=_num(coords[2]) if len(coords) > 2 else None,
                    magnitude=mag,
                    source_alert_level=alert,
                    severity_estimate=_max_severity(usgs_magnitude_band(mag), USGS_PAGER_TO_SEVERITY.get((alert or "").lower())),
                    country=None,
                    observed_at=_ms_to_dt(props.get("time")),
                    source_updated_at=_ms_to_dt(props.get("updated")),
                    url=props.get("url") if isinstance(props.get("url"), str) else None,
                    attributes={
                        "place": props.get("place"), "mag_type": props.get("magType"), "status": props.get("status"),
                        "tsunami_flag": props.get("tsunami"), "significance": props.get("sig"), "felt_reports": props.get("felt"),
                    },
                )
            )
        except (AttributeError, IndexError, TypeError):
            skipped += 1
    return ParseResult(events, skipped)


def fetch_usgs() -> ParseResult:
    return parse_usgs(httpclient.get_json(settings.usgs_feed_url))


# ------------------------------------------------------------------ GDACS
def parse_gdacs(payload: object) -> ParseResult:
    if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
        raise ExternalApiError("malformed", "GDACS response has no 'features' list")
    events, skipped = [], 0
    for feat in payload["features"]:
        try:
            props = feat.get("properties") or {}
            geom = feat.get("geometry") or {}
            etype_code = str(props.get("eventtype") or "").upper()
            event_id = props.get("eventid")
            if not etype_code or event_id in (None, ""):
                skipped += 1
                continue
            lat = lng = None
            approximate = False
            if geom.get("type") == "Point" and isinstance(geom.get("coordinates"), list) and len(geom["coordinates"]) >= 2:
                lng, lat = _num(geom["coordinates"][0]), _num(geom["coordinates"][1])
            elif isinstance(feat.get("bbox"), list) and len(feat["bbox"]) == 4:  # polygon-type hazards: use the box centre
                w, s, e, n = (_num(x) for x in feat["bbox"])
                if None not in (w, s, e, n):
                    lng, lat, approximate = (w + e) / 2, (s + n) / 2, True
            if lat is None or lng is None or not valid_coordinates(lat, lng):
                skipped += 1
                continue
            level = str(props.get("alertlevel") or "").lower() or None
            sev = props.get("severitydata") if isinstance(props.get("severitydata"), dict) else {}
            url = props.get("url") if isinstance(props.get("url"), dict) else {}
            kind = GDACS_TYPES.get(etype_code, etype_code.lower())
            country = props.get("country") if isinstance(props.get("country"), str) else None
            title = props.get("name") or props.get("description") or f"{kind.title()} alert"
            events.append(
                NormalizedEvent(
                    source="gdacs",
                    external_id=f"{etype_code}-{event_id}",
                    event_type=kind,
                    title=str(title)[:300],
                    latitude=lat,
                    longitude=lng,
                    magnitude=_num(sev.get("severity")),
                    source_alert_level=level,
                    severity_estimate=GDACS_LEVEL_TO_SEVERITY.get(level or "", "Low"),
                    country=country,
                    observed_at=_iso_to_dt(props.get("fromdate")),
                    source_updated_at=_iso_to_dt(props.get("datemodified")),
                    url=url.get("report") if isinstance(url.get("report"), str) else None,
                    attributes={
                        "severity_text": sev.get("severitytext"), "severity_unit": sev.get("severityunit"),
                        "episode_id": props.get("episodeid"), "is_current": str(props.get("iscurrent")).lower() == "true",
                        "iso3": props.get("iso3"), "provider": props.get("source"), "location_approximate": approximate,
                        "alert_score": props.get("alertscore"),
                    },
                )
            )
        except (AttributeError, IndexError, TypeError):
            skipped += 1
    return ParseResult(events, skipped, truncated=len(payload["features"]) >= 100)


def fetch_gdacs() -> ParseResult:
    today = datetime.now(timezone.utc).date()
    params = {
        "eventlist": settings.gdacs_event_types,
        "fromdate": (today - timedelta(days=settings.gdacs_days_back)).isoformat(),
        "todate": today.isoformat(),
    }
    return parse_gdacs(httpclient.get_json(settings.gdacs_search_url, params=params))


# ------------------------------------------------------------------ NASA FIRMS
def parse_firms_csv(text: str, source_name: str, max_rows: int = 500) -> ParseResult:
    head = text.lstrip()[:200]
    if "latitude" not in head.lower():
        raise ExternalApiError("malformed", f"FIRMS did not return CSV data: {head[:120]!r}")
    rows, skipped = [], 0
    for row in csv.DictReader(io.StringIO(text)):
        lat, lng = _num(row.get("latitude")), _num(row.get("longitude"))
        date = (row.get("acq_date") or "").strip()
        if lat is None or lng is None or not valid_coordinates(lat, lng) or not date:
            skipped += 1
            continue
        conf = (row.get("confidence") or "").strip().lower()
        if conf in ("l", "low") or (conf.isdigit() and int(conf) < 50):
            continue  # low-confidence detections are dropped, not reported
        rows.append((row, lat, lng, date, conf))
    truncated = len(rows) > max_rows
    rows.sort(key=lambda r: -(_num(r[0].get("frp")) or 0))
    events = []
    for row, lat, lng, date, conf in rows[:max_rows]:
        hhmm = (row.get("acq_time") or "0000").strip().zfill(4)
        try:
            observed = datetime.fromisoformat(f"{date}T{hhmm[:2]}:{hhmm[2:]}:00+00:00")
        except ValueError:
            observed = None
        frp = _num(row.get("frp"))
        sat = (row.get("satellite") or row.get("instrument") or "").strip()
        events.append(
            NormalizedEvent(
                source="firms",
                external_id=f"{source_name}:{lat:.4f}:{lng:.4f}:{date}:{hhmm}:{sat}",
                event_type="wildfire",
                title=f"Satellite fire detection ({source_name})",
                latitude=lat,
                longitude=lng,
                magnitude=frp,
                source_alert_level=conf or None,
                severity_estimate="Medium" if (frp or 0) >= 50 else "Low",
                observed_at=observed,
                url="https://firms.modaps.eosdis.nasa.gov/map/",
                attributes={"frp_mw": frp, "confidence": conf, "satellite": sat, "day_night": row.get("daynight"), "note": "Thermal anomaly - not a confirmed wildfire"},
            )
        )
    return ParseResult(events, skipped, truncated)


def fetch_firms() -> ParseResult:
    if not settings.firms_configured:
        raise ExternalApiError("not_configured", "NASA FIRMS needs FIRMS_MAP_KEY and FIRMS_AREA (west,south,east,north) in backend/.env")
    days = max(1, min(5, settings.firms_days))
    url = f"{settings.firms_base_url.rstrip('/')}/api/area/csv/{settings.firms_map_key}/{settings.firms_source}/{settings.firms_area}/{days}"
    resp = httpclient.request("GET", url)  # the key is part of the documented URL path: never logged or returned
    return parse_firms_csv(resp.text, settings.firms_source, settings.firms_max_rows)


def fetch_eonet() -> ParseResult:
    # Lazy import keeps the EONET adapter importable independently; it reuses the shared event dataclasses.
    from .eonet import fetch_eonet as fetch
    return fetch()

SOURCES = {
    "usgs": {"label": "USGS Earthquake Hazards Program", "fetch": fetch_usgs, "interval": lambda: settings.refresh_interval_usgs, "configured": lambda: True},
    "gdacs": {"label": "GDACS global disaster alerts", "fetch": fetch_gdacs, "interval": lambda: settings.refresh_interval_gdacs, "configured": lambda: True},
    "firms": {"label": "NASA FIRMS satellite fire detections", "fetch": fetch_firms, "interval": lambda: settings.refresh_interval_firms, "configured": lambda: settings.firms_configured},
    "eonet": {"label": "NASA EONET natural events", "fetch": fetch_eonet, "interval": lambda: settings.refresh_interval_gdacs, "configured": lambda: True},
}


def dumps_attributes(attrs: dict) -> str:
    return json.dumps({k: v for k, v in attrs.items() if v is not None}, default=str)




