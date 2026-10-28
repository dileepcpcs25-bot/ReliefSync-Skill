from fastapi import APIRouter
from sqlalchemy import select, update

from ..constants import ALLOCATION_TRANSITIONS, OPEN_ALLOCATION_STATUSES, AllocationStatus
from ..dependencies import DbSession, Limit, Offset, apply_updates, commit, conflict, create_kwargs, get_or_404, paginate
from ..models import Disaster, InventoryItem, ResourceAllocation
from ..schemas import AllocationCreate, AllocationOut, AllocationStatusUpdate, AllocationUpdate, Page

router = APIRouter(prefix="/allocations", tags=["Allocations"])


@router.get("", response_model=Page[AllocationOut])
def list_allocations(
    db: DbSession,
    limit: Limit = 100,
    offset: Offset = 0,
    status: AllocationStatus | None = None,
    disaster_id: int | None = None,
    item_id: int | None = None,
):
    stmt = select(ResourceAllocation).order_by(ResourceAllocation.created_at.desc(), ResourceAllocation.id.desc())
    if status:
        stmt = stmt.where(ResourceAllocation.status == status)
    if disaster_id:
        stmt = stmt.where(ResourceAllocation.disaster_id == disaster_id)
    if item_id:
        stmt = stmt.where(ResourceAllocation.item_id == item_id)
    return paginate(db, stmt, limit, offset)


@router.post("", response_model=AllocationOut, status_code=201)
def create_allocation(body: AllocationCreate, db: DbSession):
    """Confirm an allocation: deduct stock and record it in ONE transaction.

    The deduction is a conditional UPDATE (quantity >= requested), so two concurrent
    requests can never overdraw stock; the loser receives 409 and nothing is written.
    """
    disaster = get_or_404(db, Disaster, body.disaster_id, "Disaster")
    item = get_or_404(db, InventoryItem, body.item_id, "Inventory item")
    if disaster.status == "Resolved":
        raise conflict("Cannot allocate resources to a resolved disaster.")
    try:
        deducted = db.execute(
            update(InventoryItem)
            .where(InventoryItem.id == item.id, InventoryItem.quantity >= body.quantity)
            .values(quantity=InventoryItem.quantity - body.quantity)
        )
        if deducted.rowcount != 1:
            db.rollback()
            raise conflict(f"Insufficient stock of {item.name}: requested {body.quantity}, available {item.quantity}.")
        allocation = ResourceAllocation(**create_kwargs(body), status="Confirmed")
        db.add(allocation)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(allocation)
    return allocation


@router.get("/{allocation_id}", response_model=AllocationOut)
def get_allocation(allocation_id: int, db: DbSession):
    return get_or_404(db, ResourceAllocation, allocation_id, "Allocation")


@router.patch("/{allocation_id}", response_model=AllocationOut)
def update_allocation(allocation_id: int, body: AllocationUpdate, db: DbSession):
    allocation = get_or_404(db, ResourceAllocation, allocation_id, "Allocation")
    if allocation.status in ("Delivered", "Cancelled"):
        raise conflict(f"A {allocation.status} allocation can no longer be edited.")
    apply_updates(allocation, body)
    commit(db)
    return allocation


@router.patch("/{allocation_id}/status", response_model=AllocationOut)
def update_allocation_status(allocation_id: int, body: AllocationStatusUpdate, db: DbSession):
    allocation = get_or_404(db, ResourceAllocation, allocation_id, "Allocation")
    if body.status not in ALLOCATION_TRANSITIONS[allocation.status]:
        raise conflict(f"Cannot change allocation from {allocation.status} to {body.status}.")

    if body.status != "Cancelled":
        allocation.status = body.status
        commit(db)
        return allocation

    # Cancellation: flip status only if still open (compare-and-set), then restore stock once.
    try:
        flipped = db.execute(
            update(ResourceAllocation)
            .where(ResourceAllocation.id == allocation_id, ResourceAllocation.status.in_(OPEN_ALLOCATION_STATUSES))
            .values(status="Cancelled")
        )
        if flipped.rowcount != 1:
            db.rollback()
            raise conflict("Allocation was already cancelled or delivered.")
        db.execute(
            update(InventoryItem)
            .where(InventoryItem.id == allocation.item_id)
            .values(quantity=InventoryItem.quantity + allocation.quantity)
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(allocation)
    return allocation
