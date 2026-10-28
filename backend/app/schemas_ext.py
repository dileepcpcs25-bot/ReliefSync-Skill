"""Request/response models for the geographic, external-data and notification endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from .constants import CampaignAudience, LocationSource, NotificationChannel
from .schemas import Latitude, Longitude


class OperatorLogin(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
    key: Annotated[str, StringConstraints(max_length=200)] = ""

Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class RefreshRequest(BaseModel):
    sources: list[Literal["usgs", "gdacs", "firms", "eonet"]] | None = None
    force: bool = False


class ReviewRequest(BaseModel):
    status: Literal["Unreviewed", "Reviewed", "Dismissed"]


class PromoteRequest(BaseModel):
    severity: Literal["Low", "Medium", "High", "Critical"] | None = None  # defaults to the (estimated) severity band
    people_affected: int = Field(0, ge=0, le=1_000_000_000)
    notes: Text = ""


class GeocodeApplyRequest(BaseModel):
    entity: Literal["disasters", "shelters", "volunteers", "inventory"]
    limit: int = Field(5, ge=1, le=10)


class AssignApproval(BaseModel):
    volunteer_id: int
    role: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    radius_km: float = Field(50.0, gt=0, le=500)
    confirm: bool = False


class CampaignCreate(BaseModel):
    audience: CampaignAudience
    template_key: str
    disaster_id: int
    radius_km: float = Field(25.0, gt=0, le=500)
    channels: list[NotificationChannel] = Field(default_factory=lambda: ["in_app"])
    required_skills: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    instructions: Text = ""
    verified_info: Text = ""


class CampaignUpdate(BaseModel):
    template_key: str | None = None
    radius_km: float | None = Field(None, gt=0, le=500)
    channels: list[NotificationChannel] | None = None
    required_skills: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    instructions: Text | None = None
    verified_info: Text | None = None


class DispatchRequest(BaseModel):
    confirm: bool = False
    idempotency_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=80)]


class RetryRequest(BaseModel):
    confirm: bool = False


class SubscriptionCreate(BaseModel):
    channel: Literal["email", "sms"]
    contact: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=160)]
    area_label: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ""
    latitude: Latitude
    longitude: Longitude
    radius_km: float = Field(25.0, gt=0, le=200)
    consent: bool = False

    @field_validator("consent")
    @classmethod
    def _must_consent(cls, v):
        if not v:
            raise ValueError("Consent is required to receive alerts.")
        return v


class TokenRequest(BaseModel):
    token: Annotated[str, StringConstraints(strip_whitespace=True, min_length=16, max_length=64)]



class PasswordLogin(BaseModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=32)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]

class AccountRegister(BaseModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")]
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
    password: Annotated[str, StringConstraints(min_length=12, max_length=128)]


class PasswordChange(BaseModel):
    current_password: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    new_password: Annotated[str, StringConstraints(min_length=12, max_length=128)]
