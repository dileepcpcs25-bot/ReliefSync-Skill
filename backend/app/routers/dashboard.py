from fastapi import APIRouter
from sqlalchemy import func, select

from ..dependencies import DbSession
from ..models import Assignment, Disaster, ExternalEvent, InventoryItem, ResourceAllocation, Shelter, Volunteer
from ..schemas import DashboardOut
from .intelligence import build_priority_entries
from ..services.mongo_archive import mongo_status

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Broad operator-friendly geographic views matching the external-observations filters.
# They overlap at several boundaries, so regional rows must not be summed as a world total.
REGIONS = [
    ("south-asia", "India & South Asia", 60, 5, 100, 38),
    ("east-asia", "East & Southeast Asia", 95, -11, 150, 55),
    ("europe-africa", "Europe, Middle East & Africa", -25, -36, 60, 72),
    ("americas", "The Americas", -170, -56, -30, 72),
    ("oceania", "Oceania", 110, -50, 180, -1),
]


def _count(db, column, **where) -> int:
    stmt = select(func.count()).select_from(column.class_)
    for attr, value in where.items():
        stmt = stmt.where(getattr(column.class_, attr) == value)
    return db.scalar(stmt) or 0


@router.get("", response_model=DashboardOut)
def dashboard(db: DbSession):
    """Every figure is aggregated from current database rows; an empty DB yields zeros/empty lists."""
    disasters = db.scalars(select(Disaster).order_by(Disaster.created_at.desc(), Disaster.id.desc())).all()
    priorities = build_priority_entries(db)
    inv_total = db.scalar(select(func.coalesce(func.sum(InventoryItem.quantity), 0))) or 0
    low_stock = db.scalars(
        select(InventoryItem).where(InventoryItem.quantity <= InventoryItem.low_stock_threshold).order_by(InventoryItem.quantity).limit(8)
    ).all()
    low_stock_count = db.scalar(select(func.count()).select_from(InventoryItem).where(InventoryItem.quantity <= InventoryItem.low_stock_threshold)) or 0
    by_category = [
        {"category": c, "items": n, "units": int(u)}
        for c, n, u in db.execute(
            select(InventoryItem.category, func.count(), func.coalesce(func.sum(InventoryItem.quantity), 0)).group_by(InventoryItem.category)
        )
    ]
    capacity, occupancy = db.execute(
        select(func.coalesce(func.sum(Shelter.total_capacity), 0), func.coalesce(func.sum(Shelter.current_occupancy), 0))
    ).one()
    open_alloc = db.scalar(select(func.count()).select_from(ResourceAllocation).where(ResourceAllocation.status.in_(("Confirmed", "In Transit")))) or 0
    external_total = db.scalar(select(func.count()).select_from(ExternalEvent)) or 0
    source_counts = {source: int(count) for source, count in db.execute(select(ExternalEvent.source, func.count()).group_by(ExternalEvent.source))}
    recent_external = db.scalars(select(ExternalEvent).where(ExternalEvent.duplicate_of_id.is_(None)).order_by(ExternalEvent.observed_at.desc().nullslast(), ExternalEvent.id.desc()).limit(5)).all()
    coverage = db.execute(select(func.min(ExternalEvent.observed_at), func.max(ExternalEvent.observed_at))).one()
    unique_external_total = db.scalar(select(func.count()).select_from(ExternalEvent).where(ExternalEvent.duplicate_of_id.is_(None))) or 0
    regional_overview = []
    for region_id, label, west, south, east, north in REGIONS:
        coords = (ExternalEvent.latitude >= south, ExternalEvent.latitude <= north,
                  ExternalEvent.longitude >= west, ExternalEvent.longitude <= east)
        events = db.scalars(select(ExternalEvent).where(
            ExternalEvent.duplicate_of_id.is_(None), ExternalEvent.review_status != "Dismissed", *coords
        )).all()
        regional_overview.append({
            "id": region_id, "label": label, "observations": len(events),
            "active_incidents": db.scalar(select(func.count()).select_from(Disaster).where(
                Disaster.status == "Active", Disaster.latitude.is_not(None), Disaster.latitude >= south,
                Disaster.latitude <= north, Disaster.longitude >= west, Disaster.longitude <= east,
            )) or 0,
            "volunteers": db.scalar(select(func.count()).select_from(Volunteer).where(
                Volunteer.latitude.is_not(None), Volunteer.latitude >= south, Volunteer.latitude <= north,
                Volunteer.longitude >= west, Volunteer.longitude <= east,
            )) or 0,
            "shelters": db.scalar(select(func.count()).select_from(Shelter).where(
                Shelter.latitude.is_not(None), Shelter.latitude >= south, Shelter.latitude <= north,
                Shelter.longitude >= west, Shelter.longitude <= east,
            )) or 0,
            "latest_observation": max((e.observed_at for e in events if e.observed_at), default=None),
        })

    return DashboardOut(
        disasters={
            "total": len(disasters),
            "active": sum(d.status == "Active" for d in disasters),
            "monitoring": sum(d.status == "Monitoring" for d in disasters),
            "resolved": sum(d.status == "Resolved" for d in disasters),
            "critical_priority": sum(p.level == "Critical" for p in priorities),
            "high_priority": sum(p.level == "High" for p in priorities),
        },
        volunteers={
            "total": _count(db, Volunteer.id),
            "available": _count(db, Volunteer.id, availability="Available"),
            "assigned": _count(db, Volunteer.id, availability="Assigned"),
        },
        assignments={"active": _count(db, Assignment.id, status="Active"), "total": _count(db, Assignment.id)},
        inventory={"items": _count(db, InventoryItem.id), "total_units": int(inv_total), "low_stock": low_stock_count},
        inventory_by_category=by_category,
        shelters={
            "total": _count(db, Shelter.id),
            "total_capacity": int(capacity),
            "occupancy": int(occupancy),
            "available_capacity": int(capacity - occupancy),
            "occupancy_percent": round(100 * occupancy / capacity, 1) if capacity else 0,
        },
        allocations={"active": open_alloc, "delivered": _count(db, ResourceAllocation.id, status="Delivered"), "total": _count(db, ResourceAllocation.id)},
        recent_disasters=disasters[:5],
        top_priorities=priorities[:5],
        low_stock_items=low_stock,
        external_observations={"total": int(external_total), **source_counts},
        recent_external_events=[{"id": e.id, "source": e.source, "title": e.title, "event_type": e.event_type, "observed_at": e.observed_at, "retrieved_at": e.retrieved_at, "severity_estimate": e.severity_estimate, "country": e.country, "url": e.url} for e in recent_external],
        regional_overview=regional_overview,
        observation_coverage={"first_observed_at": coverage[0], "last_observed_at": coverage[1],
                              "unique_observations": int(unique_external_total)},
        mongo_archive=mongo_status(),
    )
