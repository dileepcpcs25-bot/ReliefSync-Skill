from fastapi import APIRouter, Response
from sqlalchemy import or_, select

from ..dependencies import DbSession, Limit, Offset, apply_updates, commit, conflict, create_kwargs, get_or_404, paginate
from ..models import Shelter
from ..schemas import Page, ShelterCreate, ShelterOccupancyUpdate, ShelterOut, ShelterUpdate

router = APIRouter(prefix="/shelters", tags=["Shelters"])


@router.get("", response_model=Page[ShelterOut])
def list_shelters(db: DbSession, limit: Limit = 100, offset: Offset = 0, q: str | None = None):
    stmt = select(Shelter).order_by(Shelter.name, Shelter.id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Shelter.name.ilike(like), Shelter.location.ilike(like)))
    return paginate(db, stmt, limit, offset)


@router.post("", response_model=ShelterOut, status_code=201)
def create_shelter(body: ShelterCreate, db: DbSession):
    shelter = Shelter(**create_kwargs(body))
    db.add(shelter)
    commit(db)
    return shelter


@router.get("/{shelter_id}", response_model=ShelterOut)
def get_shelter(shelter_id: int, db: DbSession):
    return get_or_404(db, Shelter, shelter_id, "Shelter")


@router.patch("/{shelter_id}", response_model=ShelterOut)
def update_shelter(shelter_id: int, body: ShelterUpdate, db: DbSession):
    shelter = get_or_404(db, Shelter, shelter_id, "Shelter")
    if body.total_capacity is not None and body.total_capacity < shelter.current_occupancy:
        raise conflict(f"Capacity cannot be below current occupancy ({shelter.current_occupancy}).")
    apply_updates(shelter, body)
    commit(db)
    return shelter


@router.patch("/{shelter_id}/occupancy", response_model=ShelterOut)
def update_occupancy(shelter_id: int, body: ShelterOccupancyUpdate, db: DbSession):
    shelter = get_or_404(db, Shelter, shelter_id, "Shelter")
    if body.current_occupancy > shelter.total_capacity:
        raise conflict(f"Occupancy cannot exceed capacity ({shelter.total_capacity}).")
    shelter.current_occupancy = body.current_occupancy
    commit(db)
    return shelter


@router.delete("/{shelter_id}", status_code=204)
def delete_shelter(shelter_id: int, db: DbSession):
    db.delete(get_or_404(db, Shelter, shelter_id, "Shelter"))
    commit(db)
    return Response(status_code=204)
