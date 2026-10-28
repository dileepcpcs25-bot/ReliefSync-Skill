"""Pydantic v2 request/response models."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .constants import (
    STATUS_RULE,
    AllocationStatus,
    AssignmentStatus,
    Availability,
    Category,
    DisasterStatus,
    LocationSource,
    Severity,
)

T = TypeVar("T")


def _text(max_length: int, min_length: int = 1):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)]


Short = _text(60)
Medium = _text(120)
Phone = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9+()\-\s]{7,30}$")]
Count = Annotated[int, Field(ge=0, le=1_000_000_000)]
PositiveCount = Annotated[int, Field(gt=0, le=1_000_000_000)]


Latitude = Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
Longitude = Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class GeoIn(BaseModel):
    """Optional position on create/update. Latitude and longitude must be given together."""

    latitude: Latitude | None = None
    longitude: Longitude | None = None
    location_source: LocationSource | None = None
    location_approximate: bool | None = None

    @model_validator(mode="after")
    def _pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class GeoOut(ORMModel):
    latitude: float | None = None
    longitude: float | None = None
    location_source: str | None = None
    location_approximate: bool = False


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# ---- Disasters
class DisasterCreate(GeoIn):
    disaster_type: Short
    location: Medium
    severity: Severity
    people_affected: Count
    description: _text(2000, 0) = ""
    status: DisasterStatus = "Active"


class DisasterUpdate(GeoIn):
    disaster_type: Short | None = None
    location: Medium | None = None
    severity: Severity | None = None
    people_affected: Count | None = None
    description: _text(2000, 0) | None = None


class DisasterStatusUpdate(BaseModel):
    status: DisasterStatus


class DisasterOut(GeoOut):
    id: int
    disaster_type: str
    location: str
    severity: str
    people_affected: int
    description: str
    status: str
    priority_score: int
    priority_level: str
    origin: str = "user"
    external_event_id: int | None = None
    created_at: datetime
    updated_at: datetime


# ---- Volunteers
class VolunteerCreate(GeoIn):
    name: Medium
    phone: Phone
    skills: _text(200, 0) = ""
    location: Medium
    availability: Literal["Available", "Unavailable"] = "Available"
    sms_opt_in: bool = False


class VolunteerUpdate(GeoIn):
    name: Medium | None = None
    phone: Phone | None = None
    skills: _text(200, 0) | None = None
    location: Medium | None = None
    sms_opt_in: bool | None = None


class VolunteerAvailabilityUpdate(BaseModel):
    availability: Literal["Available", "Unavailable"]


class VolunteerOut(GeoOut):
    """`phone` is masked and coordinates are omitted for callers without operator credentials."""

    id: int
    name: str
    phone: str
    skills: str
    location: str
    availability: Availability
    sms_opt_in: bool = False
    created_at: datetime


# ---- Assignments
class AssignmentCreate(BaseModel):
    volunteer_id: int
    disaster_id: int
    role: Short


class AssignmentStatusUpdate(BaseModel):
    status: Literal["Completed", "Cancelled"]


class AssignmentOut(ORMModel):
    id: int
    volunteer_id: int
    disaster_id: int
    volunteer_name: str
    disaster_label: str
    role: str
    status: AssignmentStatus
    created_at: datetime
    updated_at: datetime


# ---- Inventory
class InventoryCreate(GeoIn):
    name: Medium
    category: Category
    quantity: Count
    unit: _text(30)
    storage_location: Medium
    low_stock_threshold: Count = 0


class InventoryUpdate(GeoIn):
    """Quantity is intentionally absent: change stock via the /adjust endpoint."""

    name: Medium | None = None
    category: Category | None = None
    unit: _text(30) | None = None
    storage_location: Medium | None = None
    low_stock_threshold: Count | None = None


class InventoryAdjust(BaseModel):
    delta: Annotated[int, Field(ge=-1_000_000_000, le=1_000_000_000)]
    reason: _text(200, 0) = ""

    @model_validator(mode="after")
    def _non_zero(self):
        if self.delta == 0:
            raise ValueError("delta must not be zero")
        return self


class InventoryOut(GeoOut):
    id: int
    name: str
    category: str
    quantity: int
    unit: str
    storage_location: str
    low_stock_threshold: int
    is_low_stock: bool
    created_at: datetime
    updated_at: datetime


# ---- Shelters
class ShelterCreate(GeoIn):
    name: Medium
    location: Medium
    total_capacity: PositiveCount
    current_occupancy: Count = 0
    contact: _text(120, 0) = ""

    @model_validator(mode="after")
    def _within_capacity(self):
        if self.current_occupancy > self.total_capacity:
            raise ValueError("current_occupancy cannot exceed total_capacity")
        return self


class ShelterUpdate(GeoIn):
    name: Medium | None = None
    location: Medium | None = None
    total_capacity: PositiveCount | None = None
    contact: _text(120, 0) | None = None


class ShelterOccupancyUpdate(BaseModel):
    current_occupancy: Count


class ShelterOut(GeoOut):
    id: int
    name: str
    location: str
    total_capacity: int
    current_occupancy: int
    available_capacity: int
    occupancy_percent: float
    contact: str
    created_at: datetime
    updated_at: datetime


# ---- Allocations
class AllocationCreate(BaseModel):
    disaster_id: int
    item_id: int
    quantity: PositiveCount
    destination: _text(160)
    notes: _text(1000, 0) = ""
    destination_latitude: Latitude | None = None
    destination_longitude: Longitude | None = None
    destination_location_source: LocationSource | None = None

    @model_validator(mode="after")
    def _pair(self):
        if (self.destination_latitude is None) != (self.destination_longitude is None):
            raise ValueError("destination_latitude and destination_longitude must be provided together")
        return self


class AllocationUpdate(BaseModel):
    """Quantity cannot be edited after confirmation (cancel and re-create instead)."""

    destination: _text(160) | None = None
    notes: _text(1000, 0) | None = None
    destination_latitude: Latitude | None = None
    destination_longitude: Longitude | None = None
    destination_location_source: LocationSource | None = None

    @model_validator(mode="after")
    def _pair(self):
        if (self.destination_latitude is None) != (self.destination_longitude is None):
            raise ValueError("destination_latitude and destination_longitude must be provided together")
        return self


class AllocationStatusUpdate(BaseModel):
    status: Literal["In Transit", "Delivered", "Cancelled"]


class AllocationOut(ORMModel):
    id: int
    disaster_id: int
    item_id: int
    disaster_label: str
    item_name: str
    item_unit: str
    quantity: int
    destination: str
    status: AllocationStatus
    notes: str
    destination_latitude: float | None = None
    destination_longitude: float | None = None
    created_at: datetime
    updated_at: datetime


# ---- Intelligence


class PriorityFactor(BaseModel):
    name: str
    input: str
    points: float
    basis: str  # how trustworthy the input is (operational record / reported figure ...)


class PriorityEntry(BaseModel):
    rank: int
    score: int
    level: str
    explanation: str
    method: str = "score = round((severity points + population points) x status multiplier)"
    factors: list[PriorityFactor] = []
    label: str = "Estimate (rule-based)"
    disaster: DisasterOut


class PriorityResponse(BaseModel):
    status_rule: str = STATUS_RULE
    items: list[PriorityEntry]


class PriorityDetail(BaseModel):
    status_rule: str = STATUS_RULE
    ranked: bool  # False for resolved incidents (excluded from rankings)
    entry: PriorityEntry


class RecommendationOut(ORMModel):
    disaster_id: int
    disaster_label: str
    priority_level: str
    priority_score: int
    item_id: int
    item_name: str
    category: str
    unit: str
    suggested_quantity: int
    available_quantity: int
    remaining_need: int
    destination: str
    reasoning: str


class RecommendationsResponse(BaseModel):
    status_rule: str = STATUS_RULE
    items: list[RecommendationOut]


# ---- Dashboard
class DashboardOut(BaseModel):
    disasters: dict[str, int]
    volunteers: dict[str, int]
    assignments: dict[str, int]
    inventory: dict[str, int]
    inventory_by_category: list[dict]
    shelters: dict[str, float]
    allocations: dict[str, int]
    recent_disasters: list[DisasterOut]
    top_priorities: list[PriorityEntry]
    low_stock_items: list[InventoryOut]
    external_observations: dict[str, int]
    recent_external_events: list[dict]
    regional_overview: list[dict]
    observation_coverage: dict[str, datetime | int | None]
    mongo_archive: dict
