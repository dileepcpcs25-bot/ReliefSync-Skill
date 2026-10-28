"""SQLAlchemy 2.0 typed models. Integrity rules live in the database as CHECK/UNIQUE/FK
constraints so they hold even if a client bypasses API validation."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .constants import (
    AllocationStatus,
    AssignmentStatus,
    Availability,
    Category,
    DisasterStatus,
    Severity,
    sql_in,
)
from .database import Base
from .services.priority import score_disaster


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Stores naive UTC in SQLite, always returns timezone-aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)



def _coord_checks(prefix: str = "", table: str = "") -> tuple:
    lat, lng = f"{prefix}latitude", f"{prefix}longitude"
    return (
        CheckConstraint(f"{lat} IS NULL OR ({lat} >= -90 AND {lat} <= 90)", name=f"ck_{table}_{prefix}lat_range"),
        CheckConstraint(f"{lng} IS NULL OR ({lng} >= -180 AND {lng} <= 180)", name=f"ck_{table}_{prefix}lng_range"),
        CheckConstraint(f"({lat} IS NULL) = ({lng} IS NULL)", name=f"ck_{table}_{prefix}coords_pair"),
    )


class GeoMixin:
    """Optional WGS84 position. NULL means 'unknown' - coordinates are never invented."""

    latitude: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_source: Mapped[str | None] = mapped_column(String(12), nullable=True)  # manual | map | geocoded | external
    location_approximate: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None


class Disaster(GeoMixin, TimestampMixin, Base):
    __tablename__ = "disasters"
    __table_args__ = (
        CheckConstraint("people_affected >= 0", name="ck_disaster_people_nonneg"),
        CheckConstraint(sql_in("severity", Severity), name="ck_disaster_severity"),
        CheckConstraint(sql_in("status", DisasterStatus), name="ck_disaster_status"),
        *_coord_checks(table="disaster"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    disaster_type: Mapped[str] = mapped_column(String(60), index=True)
    location: Mapped[str] = mapped_column(String(120), index=True)
    severity: Mapped[str] = mapped_column(String(10), index=True)
    people_affected: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="Active", index=True)
    origin: Mapped[str] = mapped_column(String(20), default="user", server_default=text("'user'"))  # user | external_promoted
    external_event_id: Mapped[int | None] = mapped_column(ForeignKey("external_events.id", ondelete="SET NULL"), nullable=True)

    @property
    def label(self) -> str:
        return f"{self.disaster_type} - {self.location}"

    @property
    def priority_score(self) -> int:
        return score_disaster(self.severity, self.people_affected, self.status).score

    @property
    def priority_level(self) -> str:
        return score_disaster(self.severity, self.people_affected, self.status).level


class Volunteer(GeoMixin, Base):
    __tablename__ = "volunteers"
    __table_args__ = (CheckConstraint(sql_in("availability", Availability), name="ck_volunteer_availability"), *_coord_checks(table="volunteer"))
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    phone: Mapped[str] = mapped_column(String(30))
    skills: Mapped[str] = mapped_column(String(200), default="")
    location: Mapped[str] = mapped_column(String(120), index=True)
    availability: Mapped[str] = mapped_column(String(12), default="Available", index=True)
    sms_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))  # explicit consent to SMS
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Assignment(TimestampMixin, Base):
    __tablename__ = "assignments"
    __table_args__ = (
        CheckConstraint(sql_in("status", AssignmentStatus), name="ck_assignment_status"),
        # A volunteer can hold at most one Active assignment (enforced by the database).
        Index("uq_one_active_assignment", "volunteer_id", unique=True, sqlite_where=text("status = 'Active'")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    volunteer_id: Mapped[int] = mapped_column(ForeignKey("volunteers.id", ondelete="RESTRICT"), index=True)
    disaster_id: Mapped[int] = mapped_column(ForeignKey("disasters.id", ondelete="RESTRICT"), index=True)
    role: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(12), default="Active", index=True)

    volunteer: Mapped[Volunteer] = relationship(lazy="joined")
    disaster: Mapped[Disaster] = relationship(lazy="joined")

    @property
    def volunteer_name(self) -> str:
        return self.volunteer.name

    @property
    def disaster_label(self) -> str:
        return self.disaster.label


class InventoryItem(GeoMixin, TimestampMixin, Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_inventory_quantity_nonneg"),
        CheckConstraint("low_stock_threshold >= 0", name="ck_inventory_threshold_nonneg"),
        CheckConstraint(sql_in("category", Category), name="ck_inventory_category"),
        UniqueConstraint("name", "storage_location", name="uq_inventory_name_location"),
        *_coord_checks(table="inventory"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    category: Mapped[str] = mapped_column(String(20), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    unit: Mapped[str] = mapped_column(String(30))
    storage_location: Mapped[str] = mapped_column(String(120), index=True)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=0)

    @property
    def is_low_stock(self) -> bool:
        return self.quantity <= self.low_stock_threshold


class Shelter(GeoMixin, TimestampMixin, Base):
    __tablename__ = "shelters"
    __table_args__ = (
        CheckConstraint("total_capacity > 0", name="ck_shelter_capacity_positive"),
        CheckConstraint("current_occupancy >= 0", name="ck_shelter_occupancy_nonneg"),
        CheckConstraint("current_occupancy <= total_capacity", name="ck_shelter_occupancy_within_capacity"),
        *_coord_checks(table="shelter"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    location: Mapped[str] = mapped_column(String(120), index=True)
    total_capacity: Mapped[int] = mapped_column(Integer)
    current_occupancy: Mapped[int] = mapped_column(Integer, default=0)
    contact: Mapped[str] = mapped_column(String(120), default="")

    @property
    def available_capacity(self) -> int:
        return self.total_capacity - self.current_occupancy

    @property
    def occupancy_percent(self) -> float:
        return round(100 * self.current_occupancy / self.total_capacity, 1)


class ResourceAllocation(TimestampMixin, Base):
    __tablename__ = "resource_allocations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_allocation_quantity_positive"),
        CheckConstraint(sql_in("status", AllocationStatus), name="ck_allocation_status"),
        *_coord_checks("destination_", table="allocation"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    disaster_id: Mapped[int] = mapped_column(ForeignKey("disasters.id", ondelete="RESTRICT"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    destination: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(12), default="Confirmed", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    destination_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    destination_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    destination_location_source: Mapped[str | None] = mapped_column(String(12), nullable=True)

    disaster: Mapped[Disaster] = relationship(lazy="joined")
    item: Mapped[InventoryItem] = relationship(lazy="joined")

    @property
    def disaster_label(self) -> str:
        return self.disaster.label

    @property
    def item_name(self) -> str:
        return self.item.name

    @property
    def item_unit(self) -> str:
        return self.item.unit


# =====================================================================================
# External observations, caches, notifications, audit
# =====================================================================================
class ExternalEvent(Base):
    """An observation fetched from an external source. NOT an operational incident until an operator promotes it."""

    __tablename__ = "external_events"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_external_source_id"),
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_external_lat_range"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_external_lng_range"),
        CheckConstraint("review_status IN ('Unreviewed','Reviewed','Dismissed','Promoted')", name="ck_external_review_status"),
        Index("ix_external_source_observed", "source", "observed_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20), index=True)  # usgs | gdacs | firms
    external_id: Mapped[str] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(40), index=True)  # earthquake, flood, wildfire...
    title: Mapped[str] = mapped_column(String(300))
    latitude: Mapped[float] = mapped_column(Float, index=True)
    longitude: Mapped[float] = mapped_column(Float)
    depth_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    magnitude: Mapped[float | None] = mapped_column(Float, nullable=True)  # source-native magnitude/severity value
    source_alert_level: Mapped[str | None] = mapped_column(String(20), nullable=True)  # as reported by the source
    severity_estimate: Mapped[str] = mapped_column(String(10), default="Low", index=True)  # derived, labelled "Estimate"
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)  # when it happened
    source_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)  # when we last fetched it
    first_retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attributes: Mapped[str] = mapped_column(Text, default="{}")  # JSON text: extra source-specific fields
    review_status: Mapped[str] = mapped_column(String(12), default="Unreviewed", index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("external_events.id", ondelete="SET NULL"), nullable=True, index=True)


class ExternalFetchLog(Base):
    """One row per fetch attempt: powers 'last updated', honest error display and cache/cooldown decisions."""

    __tablename__ = "external_fetch_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20))  # ok | error | not_configured | cached
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    events_new: Mapped[int] = mapped_column(Integer, default=0)
    events_updated: Mapped[int] = mapped_column(Integer, default=0)
    events_skipped: Mapped[int] = mapped_column(Integer, default=0)  # malformed / missing coordinates


class ApiCache(Base):
    """Small generic cache for geocoding, routing and weather responses (respecting provider usage policies)."""

    __tablename__ = "api_cache"
    id: Mapped[int] = mapped_column(primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(400), unique=True)
    source: Mapped[str] = mapped_column(String(30), index=True)
    payload: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)


class Subscription(Base):
    """Opt-in recipient of resident alerts. Stores a COARSE area (rounded to ~11 km), never an exact location."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("channel IN ('email','sms')", name="ck_subscription_channel"),
        CheckConstraint("status IN ('Pending','Active','Unsubscribed')", name="ck_subscription_status"),
        CheckConstraint("radius_km > 0 AND radius_km <= 500", name="ck_subscription_radius"),
        CheckConstraint("area_latitude >= -90 AND area_latitude <= 90", name="ck_subscription_lat"),
        CheckConstraint("area_longitude >= -180 AND area_longitude <= 180", name="ck_subscription_lng"),
        UniqueConstraint("channel", "contact", name="uq_subscription_channel_contact"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(8))
    contact: Mapped[str] = mapped_column(String(160))  # email address or E.164 phone number
    area_label: Mapped[str] = mapped_column(String(120), default="")
    area_latitude: Mapped[float] = mapped_column(Float)
    area_longitude: Mapped[float] = mapped_column(Float)
    radius_km: Mapped[float] = mapped_column(Float, default=25.0)
    status: Mapped[str] = mapped_column(String(12), default="Pending", index=True)
    consent_text: Mapped[str] = mapped_column(Text)
    consent_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    confirm_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unsubscribe_token: Mapped[str] = mapped_column(String(64), unique=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    unsubscribed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class NotificationCampaign(TimestampMixin, Base):
    __tablename__ = "notification_campaigns"
    __table_args__ = (
        CheckConstraint("audience IN ('volunteers','shelters','residents')", name="ck_campaign_audience"),
        CheckConstraint(
            "status IN ('Draft','Approved','Dispatching','Dispatched','Partially Failed','Failed','Cancelled')",
            name="ck_campaign_status",
        ),
        CheckConstraint("radius_km > 0 AND radius_km <= 500", name="ck_campaign_radius"),
        UniqueConstraint("dispatch_idempotency_key", name="uq_campaign_idempotency"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    audience: Mapped[str] = mapped_column(String(12), index=True)
    template_key: Mapped[str] = mapped_column(String(40))
    disaster_id: Mapped[int] = mapped_column(ForeignKey("disasters.id", ondelete="RESTRICT"), index=True)
    radius_km: Mapped[float] = mapped_column(Float)
    channels: Mapped[str] = mapped_column(String(60), default="in_app")  # comma separated: in_app,sms,email
    required_skills: Mapped[str] = mapped_column(String(200), default="")
    instructions: Mapped[str] = mapped_column(Text, default="")  # operator text, e.g. reporting point
    verified_info: Mapped[str] = mapped_column(Text, default="")  # operator-supplied VERIFIED public information
    status: Mapped[str] = mapped_column(String(16), default="Draft", index=True)
    created_by: Mapped[str] = mapped_column(String(80), default="operator")
    approved_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    approved_message_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    dispatched_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    dispatch_idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    mode_at_dispatch: Mapped[str | None] = mapped_column(String(12), nullable=True)  # development | live

    disaster: Mapped[Disaster] = relationship(lazy="joined")


class NotificationDelivery(Base):
    """One row per (campaign, recipient, channel). The UNIQUE constraint is the last line of defence against duplicates."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("campaign_id", "recipient_type", "recipient_id", "channel", name="uq_delivery_once"),
        CheckConstraint(
            "status IN ('pending','recorded_in_app','simulated','accepted_by_provider','failed','skipped')",
            name="ck_delivery_status",
        ),
        Index("ix_delivery_recipient", "recipient_type", "recipient_id", "channel"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("notification_campaigns.id", ondelete="CASCADE"), index=True)
    recipient_type: Mapped[str] = mapped_column(String(12))  # volunteer | shelter | subscription | public
    recipient_id: Mapped[int] = mapped_column(Integer, default=0)  # 0 for the public feed
    channel: Mapped[str] = mapped_column(String(8))
    address_masked: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    provider: Mapped[str] = mapped_column(String(30), default="")
    provider_message_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")  # skip reason / provider error
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class InAppNotification(Base):
    """What a person sees inside ReliefSync. Creating one is NOT the same as sending an SMS or email."""

    __tablename__ = "in_app_notifications"
    __table_args__ = (CheckConstraint("recipient_type IN ('volunteer','shelter','public')", name="ck_inapp_recipient_type"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("notification_campaigns.id", ondelete="CASCADE"), index=True)
    delivery_id: Mapped[int | None] = mapped_column(ForeignKey("notification_deliveries.id", ondelete="SET NULL"), nullable=True)
    recipient_type: Mapped[str] = mapped_column(String(12), index=True)
    recipient_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    disaster_id: Mapped[int | None] = mapped_column(ForeignKey("disasters.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="{}")  # JSON text; never contains secrets or full contact details


class OperatorUser(Base):
    __tablename__ = "operator_users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(16), default="operator")
    password_hash: Mapped[str] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
