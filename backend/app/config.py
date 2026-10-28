"""Runtime configuration read from environment variables (optionally a local .env).

Secrets (API keys, provider credentials) are only ever read here, on the backend.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")  # does not override variables already set


def _default_database_url() -> str:
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(exist_ok=True)
    return f"sqlite:///{(data_dir / 'reliefsync.db').as_posix()}"


def _origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:5191,http://127.0.0.1:5191")
    return [o.strip() for o in raw.split(",") if o.strip()]


def _str(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    # ---- core
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL") or _default_database_url())
    cors_origins: list[str] = field(default_factory=_origins)
    app_env: str = field(default_factory=lambda: _str("APP_ENV", "development").lower())
    public_app_url: str = field(default_factory=lambda: _str("PUBLIC_APP_URL", "http://localhost:5191").rstrip("/"))

    # ---- operator authorisation (see README: Authorisation)
    operator_api_key: str = field(default_factory=lambda: _str("OPERATOR_API_KEY"))
    demo_seed_data: bool = field(default_factory=lambda: _str("DEMO_SEED_DATA", "false").lower() in {"1", "true", "yes"})
    auth_secret: str = field(default_factory=lambda: _str("AUTH_SECRET", "local-only-reliefsync-demo-change-before-sharing"))
    allow_user_registration: bool = field(default_factory=lambda: _str("ALLOW_USER_REGISTRATION", "true").lower() in {"1", "true", "yes"})

    # ---- storage and external data sources
    mongodb_uri: str = field(default_factory=lambda: _str("MONGODB_URI", "mongodb://127.0.0.1:27017"))
    mongodb_database: str = field(default_factory=lambda: _str("MONGODB_DATABASE", "reliefsync"))

    # ---- external data sources (endpoints are configurable; defaults are the documented public ones)
    http_user_agent: str = field(default_factory=lambda: _str("HTTP_USER_AGENT", "ReliefSync/1.0 (disaster-relief demo; set HTTP_USER_AGENT with a contact)"))
    http_timeout_seconds: float = field(default_factory=lambda: _float("HTTP_TIMEOUT_SECONDS", 12.0))
    usgs_feed_url: str = field(default_factory=lambda: _str("USGS_FEED_URL", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"))
    gdacs_search_url: str = field(default_factory=lambda: _str("GDACS_SEARCH_URL", "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"))
    gdacs_event_types: str = field(default_factory=lambda: _str("GDACS_EVENT_TYPES", "EQ;TC;FL;VO;DR;WF"))
    gdacs_days_back: int = field(default_factory=lambda: _int("GDACS_DAYS_BACK", 14))
    eonet_url: str = field(default_factory=lambda: _str("NASA_EONET_URL", "https://eonet.gsfc.nasa.gov/api/v3/events/geojson"))
    open_meteo_url: str = field(default_factory=lambda: _str("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast"))
    firms_base_url: str = field(default_factory=lambda: _str("FIRMS_BASE_URL", "https://firms.modaps.eosdis.nasa.gov"))
    firms_map_key: str = field(default_factory=lambda: _str("FIRMS_MAP_KEY"))
    firms_area: str = field(default_factory=lambda: _str("FIRMS_AREA"))  # "west,south,east,north"
    firms_source: str = field(default_factory=lambda: _str("FIRMS_SOURCE", "VIIRS_SNPP_NRT"))
    firms_days: int = field(default_factory=lambda: _int("FIRMS_DAYS", 2))
    firms_max_rows: int = field(default_factory=lambda: _int("FIRMS_MAX_ROWS", 500))
    # minimum seconds between successful fetches per source (cache / politeness)
    refresh_interval_usgs: int = field(default_factory=lambda: _int("REFRESH_INTERVAL_USGS", 300))
    refresh_interval_gdacs: int = field(default_factory=lambda: _int("REFRESH_INTERVAL_GDACS", 600))
    refresh_interval_firms: int = field(default_factory=lambda: _int("REFRESH_INTERVAL_FIRMS", 900))
    manual_refresh_floor_seconds: int = field(default_factory=lambda: _int("MANUAL_REFRESH_FLOOR_SECONDS", 30))
    weather_cache_seconds: int = field(default_factory=lambda: _int("WEATHER_CACHE_SECONDS", 900))

    # ---- geocoding / routing
    nominatim_url: str = field(default_factory=lambda: _str("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search"))
    nominatim_min_interval: float = field(default_factory=lambda: _float("NOMINATIM_MIN_INTERVAL", 1.1))
    geocode_cache_days: int = field(default_factory=lambda: _int("GEOCODE_CACHE_DAYS", 30))
    routing_enabled: bool = field(default_factory=lambda: _str("ROUTING_ENABLED", "true").lower() in {"1", "true", "yes"})
    osrm_url: str = field(default_factory=lambda: _str("OSRM_URL", "https://router.project-osrm.org"))
    route_cache_seconds: int = field(default_factory=lambda: _int("ROUTE_CACHE_SECONDS", 3600))

    # ---- geography defaults
    default_radius_km: float = field(default_factory=lambda: _float("DEFAULT_RADIUS_KM", 50.0))
    max_radius_km: float = field(default_factory=lambda: _float("MAX_RADIUS_KM", 500.0))

    # ---- notifications. "development" NEVER contacts real recipients.
    notifications_mode: str = field(default_factory=lambda: _str("NOTIFICATIONS_MODE", "development").lower())
    notification_cooldown_minutes: int = field(default_factory=lambda: _int("NOTIFICATION_COOLDOWN_MINUTES", 30))
    notification_max_attempts: int = field(default_factory=lambda: _int("NOTIFICATION_MAX_ATTEMPTS", 3))
    twilio_account_sid: str = field(default_factory=lambda: _str("TWILIO_ACCOUNT_SID"))
    twilio_auth_token: str = field(default_factory=lambda: _str("TWILIO_AUTH_TOKEN"))
    twilio_from_number: str = field(default_factory=lambda: _str("TWILIO_FROM_NUMBER"))
    twilio_messaging_service_sid: str = field(default_factory=lambda: _str("TWILIO_MESSAGING_SERVICE_SID"))
    twilio_base_url: str = field(default_factory=lambda: _str("TWILIO_BASE_URL", "https://api.twilio.com"))
    smtp_host: str = field(default_factory=lambda: _str("SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: _int("SMTP_PORT", 587))
    smtp_username: str = field(default_factory=lambda: _str("SMTP_USERNAME"))
    smtp_password: str = field(default_factory=lambda: _str("SMTP_PASSWORD"))
    smtp_from: str = field(default_factory=lambda: _str("SMTP_FROM"))
    smtp_starttls: bool = field(default_factory=lambda: _str("SMTP_STARTTLS", "true").lower() in {"1", "true", "yes"})
    sms_cost_per_message: str = field(default_factory=lambda: _str("SMS_COST_PER_MESSAGE"))  # e.g. "0.0083 USD" (informational)
    email_cost_per_message: str = field(default_factory=lambda: _str("EMAIL_COST_PER_MESSAGE"))

    # ---- simple in-memory rate limits for public endpoints (requests per minute per client)
    rate_limit_public_per_minute: int = field(default_factory=lambda: _int("RATE_LIMIT_PUBLIC_PER_MINUTE", 20))

    @property
    def twilio_configured(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token and (self.twilio_from_number or self.twilio_messaging_service_sid))

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def live_mode(self) -> bool:
        return self.notifications_mode == "live"

    @property
    def firms_configured(self) -> bool:
        return bool(self.firms_map_key and self.firms_area)


settings = Settings()

