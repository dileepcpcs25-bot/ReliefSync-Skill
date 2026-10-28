from fastapi import APIRouter, Response
from sqlalchemy import select, update

from ..constants import Category
from ..dependencies import DbSession, Limit, Offset, apply_updates, commit, conflict, create_kwargs, get_or_404, paginate
from ..models import InventoryItem, ResourceAllocation
from ..schemas import InventoryAdjust, InventoryCreate, InventoryOut, InventoryUpdate, Page

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.get("", response_model=Page[InventoryOut])
def list_inventory(
    db: DbSession,
    limit: Limit = 100,
    offset: Offset = 0,
    q: str | None = None,
    category: Category | None = None,
    storage_location: str | None = None,
    low_stock: bool | None = None,
):
    stmt = select(InventoryItem).order_by(InventoryItem.name, InventoryItem.id)
    if q:
        stmt = stmt.where(InventoryItem.name.ilike(f"%{q.strip()}%"))
    if category:
        stmt = stmt.where(InventoryItem.category == category)
    if storage_location:
        stmt = stmt.where(InventoryItem.storage_location.ilike(f"%{storage_location.strip()}%"))
    if low_stock is True:
        stmt = stmt.where(InventoryItem.quantity <= InventoryItem.low_stock_threshold)
    elif low_stock is False:
        stmt = stmt.where(InventoryItem.quantity > InventoryItem.low_stock_threshold)
    return paginate(db, stmt, limit, offset)


@router.post("", response_model=InventoryOut, status_code=201)
def create_item(body: InventoryCreate, db: DbSession):
    item = InventoryItem(**create_kwargs(body))
    db.add(item)
    commit(db, "An item with this name already exists at that storage location.")
    return item


@router.get("/{item_id}", response_model=InventoryOut)
def get_item(item_id: int, db: DbSession):
    return get_or_404(db, InventoryItem, item_id, "Inventory item")


@router.patch("/{item_id}", response_model=InventoryOut)
def update_item(item_id: int, body: InventoryUpdate, db: DbSession):
    item = get_or_404(db, InventoryItem, item_id, "Inventory item")
    apply_updates(item, body)
    commit(db, "An item with this name already exists at that storage location.")
    return item


@router.patch("/{item_id}/adjust", response_model=InventoryOut)
def adjust_quantity(item_id: int, body: InventoryAdjust, db: DbSession):
    """Atomic adjustment: the WHERE clause makes it impossible to go below zero, even under races."""
    item = get_or_404(db, InventoryItem, item_id, "Inventory item")
    result = db.execute(
        update(InventoryItem)
        .where(InventoryItem.id == item_id, InventoryItem.quantity + body.delta >= 0)
        .values(quantity=InventoryItem.quantity + body.delta)
    )
    if result.rowcount != 1:
        db.rollback()
        raise conflict("Adjustment would make stock negative.")
    commit(db)
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, db: DbSession):
    item = get_or_404(db, InventoryItem, item_id, "Inventory item")
    if db.scalar(select(ResourceAllocation.id).where(ResourceAllocation.item_id == item_id).limit(1)):
        raise conflict("Item has allocation history and cannot be deleted. Set its quantity to 0 instead.")
    db.delete(item)
    commit(db)
    return Response(status_code=204)
