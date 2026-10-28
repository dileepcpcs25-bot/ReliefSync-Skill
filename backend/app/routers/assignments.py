from fastapi import APIRouter
from sqlalchemy import select

from ..dependencies import DbSession, Limit, Offset, commit, conflict, get_or_404, paginate
from ..models import Assignment, Disaster, Volunteer
from ..schemas import AssignmentCreate, AssignmentOut, AssignmentStatusUpdate, Page

router = APIRouter(prefix="/assignments", tags=["Assignments"])


def finish_assignment(assignment: Assignment, new_status: str) -> None:
    """Close an assignment and release the volunteer (shared with disaster resolution)."""
    assignment.status = new_status
    if assignment.volunteer.availability == "Assigned":
        assignment.volunteer.availability = "Available"


@router.get("", response_model=Page[AssignmentOut])
def list_assignments(
    db: DbSession,
    limit: Limit = 100,
    offset: Offset = 0,
    status: str | None = None,
    disaster_id: int | None = None,
    volunteer_id: int | None = None,
):
    stmt = select(Assignment).order_by(Assignment.created_at.desc(), Assignment.id.desc())
    if status:
        stmt = stmt.where(Assignment.status == status)
    if disaster_id:
        stmt = stmt.where(Assignment.disaster_id == disaster_id)
    if volunteer_id:
        stmt = stmt.where(Assignment.volunteer_id == volunteer_id)
    return paginate(db, stmt, limit, offset)


def assign_volunteer(db, volunteer_id: int, disaster_id: int, role: str) -> Assignment:
    """Create an Active assignment after RE-CHECKING the live state (shared by the plain endpoint and the
    operator-approved nearby-volunteer flow). Conflicts raise HTTP 409; nothing is written on failure."""
    volunteer = get_or_404(db, Volunteer, volunteer_id, "Volunteer")
    disaster = get_or_404(db, Disaster, disaster_id, "Disaster")
    if disaster.status == "Resolved":
        raise conflict("Cannot assign volunteers to a resolved disaster.")
    if volunteer.availability != "Available":
        raise conflict(f"Volunteer is {volunteer.availability} and cannot be assigned.")
    assignment = Assignment(volunteer_id=volunteer.id, disaster_id=disaster.id, role=role)
    volunteer.availability = "Assigned"
    db.add(assignment)
    commit(db, "Volunteer already has an active assignment.")  # partial unique index guards races
    return assignment


@router.post("", response_model=AssignmentOut, status_code=201)
def create_assignment(body: AssignmentCreate, db: DbSession):
    return assign_volunteer(db, body.volunteer_id, body.disaster_id, body.role)


@router.get("/{assignment_id}", response_model=AssignmentOut)
def get_assignment(assignment_id: int, db: DbSession):
    return get_or_404(db, Assignment, assignment_id, "Assignment")


@router.patch("/{assignment_id}/status", response_model=AssignmentOut)
def update_assignment_status(assignment_id: int, body: AssignmentStatusUpdate, db: DbSession):
    assignment = get_or_404(db, Assignment, assignment_id, "Assignment")
    if assignment.status != "Active":
        raise conflict(f"Assignment is already {assignment.status}.")
    finish_assignment(assignment, body.status)
    commit(db)
    return assignment
