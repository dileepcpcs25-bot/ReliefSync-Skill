"""Single source of truth for allowed values, shared by models, schemas and services."""
from typing import Literal, get_args

Severity = Literal["Low", "Medium", "High", "Critical"]
DisasterStatus = Literal["Active", "Monitoring", "Resolved"]
Availability = Literal["Available", "Assigned", "Unavailable"]
AssignmentStatus = Literal["Active", "Completed", "Cancelled"]
AllocationStatus = Literal["Confirmed", "In Transit", "Delivered", "Cancelled"]
Category = Literal["Food", "Water", "Medical", "Shelter", "Clothing", "Hygiene", "Other"]

LocationSource = Literal["manual", "map", "geocoded", "external"]
LOCATION_SOURCES = get_args(LocationSource)

# How a piece of information should be labelled in the UI/API (see README: data labelling).
BASIS_OPERATIONAL = "Operational record (entered in ReliefSync, not independently verified)"
BASIS_EXTERNAL = "External observation (unverified by an operator)"
BASIS_ESTIMATE = "Estimate (rule-based)"

STATUS_RULE = "Resolved incidents are excluded."

OPEN_ALLOCATION_STATUSES = ("Confirmed", "In Transit")  # stock is deducted and reversible
ALLOCATION_TRANSITIONS = {
    "Confirmed": {"In Transit", "Delivered", "Cancelled"},
    "In Transit": {"Delivered", "Cancelled"},
    "Delivered": set(),
    "Cancelled": set(),
}


def sql_in(column: str, literal_type) -> str:
    """Build a CHECK constraint expression such as: status IN ('A','B')."""
    return f"{column} IN ({', '.join(repr(v) for v in get_args(literal_type))})"


# ---- notifications
CampaignAudience = Literal["volunteers", "shelters", "residents"]
NotificationChannel = Literal["in_app", "sms", "email"]
