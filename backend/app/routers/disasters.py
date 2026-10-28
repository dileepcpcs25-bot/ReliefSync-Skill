from fastapi import APIRouter, Response
from sqlalchemy import or_, select

from ..constants import DisasterStatus, Severity
from ..dependencies import DbSession, Limit, Offset, apply_updates, commit, conflict, create_kwargs, get_or_404, paginate
from ..models import Assignment, Disaster, ResourceAllocation
from ..schemas import DisasterCreate, DisasterOut, DisasterStatusUpdate, DisasterUpdate, Page
from .assignments import finish_assignment

router = APIRouter(prefix="/disasters", tags=["Disasters"])


@router.get("", response_model=Page[DisasterOut])
def list_disasters(
    db: DbSession,
    limit: Limit = 100,
    offset: Offset = 0,
    q: str | None = None,
    severity: Severity | None = None,
    status: DisasterStatus | None = None,
    disaster_type: str | None = None,
    location: str | None = None,
):
    stmt = select(Disaster).order_by(Disaster.created_at.desc(), Disaster.id.desc())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Disaster.location.ilike(like), Disaster.disaster_type.ilike(like), Disaster.description.ilike(like)))
    if severity:
        stmt = stmt.where(Disaster.severity == severity)
    if status:
        stmt = stmt.where(Disaster.status == status)
    if disaster_type:
        stmt = stmt.where(Disaster.disaster_type.ilike(f"%{disaster_type.strip()}%"))
    if location:
        stmt = stmt.where(Disaster.location.ilike(f"%{location.strip()}%"))
    return paginate(db, stmt, limit, offset)


@router.post("", response_model=DisasterOut, status_code=201)
def create_disaster(body: DisasterCreate, db: DbSession):
    disaster = Disaster(**create_kwargs(body))
    db.add(disaster)
    commit(db)
    return disaster


@router.get("/{disaster_id}", response_model=DisasterOut)
def get_disaster(disaster_id: int, db: DbSession):
    return get_or_404(db, Disaster, disaster_id, "Disaster")


@router.patch("/{disaster_id}", response_model=DisasterOut)
def update_disaster(disaster_id: int, body: DisasterUpdate, db: DbSession):
    disaster = get_or_404(db, Disaster, disaster_id, "Disaster")
    apply_updates(disaster, body)
    commit(db)
    return disaster


@router.patch("/{disaster_id}/status", response_model=DisasterOut)
def update_disaster_status(disaster_id: int, body: DisasterStatusUpdate, db: DbSession):
    disaster = get_or_404(db, Disaster, disaster_id, "Disaster")
    disaster.status = body.status
    if body.status == "Resolved":  # release volunteers so availability stays consistent
        active = db.scalars(select(Assignment).where(Assignment.disaster_id == disaster_id, Assignment.status == "Active"))
        for assignment in active.unique():
            finish_assignment(assignment, "Completed")
    commit(db)
    return disaster


@router.delete("/{disaster_id}", status_code=204)
def delete_disaster(disaster_id: int, db: DbSession):
    disaster = get_or_404(db, Disaster, disaster_id, "Disaster")
    has_assignments = db.scalar(select(Assignment.id).where(Assignment.disaster_id == disaster_id).limit(1))
    has_allocations = db.scalar(select(ResourceAllocation.id).where(ResourceAllocation.disaster_id == disaster_id).limit(1))
    if has_assignments or has_allocations:
        raise conflict("Disaster has assignment or allocation history. Mark it Resolved instead of deleting it.")
    db.delete(disaster)
    commit(db)
    return Response(status_code=204)
