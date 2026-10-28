"""NASA EONET v3 free natural-event metadata adapter."""
from __future__ import annotations

from ..config import settings
from . import httpclient
from .external_sources import NormalizedEvent, ParseResult, _iso_to_dt, _num
from .geo import valid_coordinates
from .httpclient import ExternalApiError


def parse_eonet(payload: object) -> ParseResult:
    """Parse GeoJSON events; polygon coordinates use a clearly approximate bounds centre."""
    if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
        raise ExternalApiError("malformed", "NASA EONET response has no GeoJSON features list")
    events, skipped = {}, 0
    for feature in payload["features"]:
        try:
            props = feature.get("properties") or {}
            geometry = feature.get("geometry") or {}
            ext_id = props.get("id") or feature.get("id")
            coords = geometry.get("coordinates")
            lat = lng = None
            approximate = False
            if geometry.get("type") == "Point" and isinstance(coords, list) and len(coords) >= 2:
                lng, lat = _num(coords[0]), _num(coords[1])
            elif isinstance(coords, list) and coords:
                points = []
                stack = list(coords)
                while stack:
                    value = stack.pop()
                    if isinstance(value, list) and len(value) >= 2 and not isinstance(value[0], list):
                        x, y = _num(value[0]), _num(value[1])
                        if x is not None and y is not None:
                            points.append((x, y))
                    elif isinstance(value, list):
                        stack.extend(value)
                if points:
                    lng = (min(x for x, _ in points) + max(x for x, _ in points)) / 2
                    lat = (min(y for _, y in points) + max(y for _, y in points)) / 2
                    approximate = True
            if not ext_id or lat is None or lng is None or not valid_coordinates(lat, lng):
                skipped += 1
                continue
            categories = props.get("categories") if isinstance(props.get("categories"), list) else []
            category = categories[0] if categories and isinstance(categories[0], dict) else {}
            category_title = str(category.get("title") or "natural event").lower()[:40]
            geometry_rows = props.get("geometry") if isinstance(props.get("geometry"), list) else []
            observed = _iso_to_dt(props.get("date"))
            if observed is None and geometry_rows and isinstance(geometry_rows[-1], dict):
                observed = _iso_to_dt(geometry_rows[-1].get("date"))
            sources = props.get("sources") if isinstance(props.get("sources"), list) else []
            source_url = sources[0].get("url") if sources and isinstance(sources[0], dict) else props.get("link")
            event = NormalizedEvent(
                source="eonet", external_id=str(ext_id), event_type=category_title,
                title=str(props.get("title") or "NASA EONET natural event")[:300],
                latitude=lat, longitude=lng, magnitude=_num(props.get("magnitudeValue")), severity_estimate="Low", observed_at=observed,
                source_updated_at=_iso_to_dt(props.get("closed")),
                url=source_url if isinstance(source_url, str) else None,
                attributes={"category_id": category.get("id"), "category": category_title,
                            "closed": props.get("closed"), "description": props.get("description"),
                            "magnitude_unit": props.get("magnitudeUnit"),
                            "location_approximate": approximate,
                            "data_note": "NASA-curated event metadata; not a severity or impact assessment"},
            )
            previous = events.get(str(ext_id))
            if previous is None or (observed is not None and (previous.observed_at is None or observed > previous.observed_at)):
                events[str(ext_id)] = event
        except (AttributeError, IndexError, TypeError):
            skipped += 1
    return ParseResult(list(events.values()), skipped)


def fetch_eonet() -> ParseResult:
    return parse_eonet(httpclient.get_json(settings.eonet_url, params={"status": "all", "days": 365, "limit": 500}))

