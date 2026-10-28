from fastapi import APIRouter
from sqlalchemy import or_, select

from ..constants import Availability
from ..dependencies import (
    DbSession,
    Limit,
    Offset,
    OptionalOperatorDep,
    apply_updates,
    commit,
    conflict,
    create_kwargs,
    get_or_404,
    paginate,
)
from ..models import Volunteer
from ..schemas import Page, VolunteerAvailabilityUpdate, VolunteerCreate, VolunteerOut, VolunteerUpdate

router = APIRouter(prefix="/volunteers", tags=["Volunteers"])


def mask_phone(phone: str) -> str:
    digits = [c for c in phone if c.isdigit()]
    return ("*" * 6 + "".join(digits[-2:])) if len(digits) >= 2 else "******"


def volunteer_view(volunteer: Volunteer, operator) -> VolunteerOut:
    """Privacy: callers without operator credentials never receive the phone number or any coordinates."""
    out = VolunteerOut.model_validate(volunteer)
    if operator is None:
        return out.model_copy(
            update={"phone": mask_phone(volunteer.phone), "latitude": None, "longitude": None, "location_source": None, "location_approximate": False}
        )
    return out


@router.get("", response_model=Page[VolunteerOut])
def list_volunteers(
    db: DbSession,
    operator: OptionalOperatorDep,
    limit: Limit = 100,
    offset: Offset = 0,
    q: str | None = None,
    availability: Availability | None = None,
    location: str | None = None,
):
    stmt = select(Volunteer).order_by(Volunteer.name, Volunteer.id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Volunteer.name.ilike(like), Volunteer.skills.ilike(like), Volunteer.location.ilike(like)))
    if availability:
        stmt = stmt.where(Volunteer.availability == availability)
    if location:
        stmt = stmt.where(Volunteer.location.ilike(f"%{location.strip()}%"))
    page = paginate(db, stmt, limit, offset)
    page["items"] = [volunteer_view(v, operator) for v in page["items"]]
    return page


@router.post("", response_model=VolunteerOut, status_code=201)
def create_volunteer(body: VolunteerCreate, db: DbSession, operator: OptionalOperatorDep):
    volunteer = Volunteer(**create_kwargs(body))
    db.add(volunteer)
    commit(db)
    return volunteer_view(volunteer, operator)


@router.get("/{volunteer_id}", response_model=VolunteerOut)
def get_volunteer(volunteer_id: int, db: DbSession, operator: OptionalOperatorDep):
    return volunteer_view(get_or_404(db, Volunteer, volunteer_id, "Volunteer"), operator)


@router.patch("/{volunteer_id}", response_model=VolunteerOut)
def update_volunteer(volunteer_id: int, body: VolunteerUpdate, db: DbSession, operator: OptionalOperatorDep):
    volunteer = get_or_404(db, Volunteer, volunteer_id, "Volunteer")
    apply_updates(volunteer, body)
    commit(db)
    return volunteer_view(volunteer, operator)


@router.patch("/{volunteer_id}/availability", response_model=VolunteerOut)
def update_availability(volunteer_id: int, body: VolunteerAvailabilityUpdate, db: DbSession, operator: OptionalOperatorDep):
    volunteer = get_or_404(db, Volunteer, volunteer_id, "Volunteer")
    if volunteer.availability == "Assigned":
        raise conflict("Volunteer has an active assignment. Complete or cancel it first.")
    volunteer.availability = body.availability
    commit(db)
    return volunteer_view(volunteer, operator)
