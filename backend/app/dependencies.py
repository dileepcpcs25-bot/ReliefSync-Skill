from typing import Annotated

from fastapi import Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db

DbSession = Annotated[Session, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0)]


def get_or_404(db: Session, model, obj_id: int, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(404, f"{label} {obj_id} not found")
    return obj


def conflict(message: str) -> HTTPException:
    return HTTPException(409, message)


def paginate(db: Session, stmt, limit: int, offset: int) -> dict:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = db.scalars(stmt.limit(limit).offset(offset)).unique().all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def apply_updates(obj, data) -> None:
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(obj, key, value)
    # A position given without a stated source is recorded as manually entered.
    if getattr(data, "latitude", None) is not None and getattr(data, "location_source", None) is None:
        obj.location_source = "manual"
    if getattr(data, "destination_latitude", None) is not None and getattr(data, "destination_location_source", None) is None:
        obj.destination_location_source = "manual"


def create_kwargs(body) -> dict:
    """Constructor kwargs for a create schema: None values are dropped so column defaults apply, and
    a position without a stated source is recorded as 'manual'."""
    data = body.model_dump(exclude_none=True)
    if data.get("latitude") is not None and "location_source" not in data:
        data["location_source"] = "manual"
    if data.get("destination_latitude") is not None and "destination_location_source" not in data:
        data["destination_location_source"] = "manual"
    return data


def commit(db: Session, message: str = "Operation conflicts with existing data") -> None:
    """Commit, translating database constraint failures into HTTP 409."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict(message) from exc


# =====================================================================================
# Operator authorisation, rate limiting, audit trail
# =====================================================================================
import hmac  # noqa: E402
import json  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from collections import defaultdict, deque  # noqa: E402
from dataclasses import dataclass  # noqa: E402

from fastapi import Header, Request  # noqa: E402

from .config import settings  # noqa: E402


@dataclass(frozen=True)
class Operator:
    name: str
    open_access: bool
    role: str = "operator"
    username: str = ""


def _operator_from_headers(x_operator_key: str | None, x_operator_name: str | None, authorization: str | None = None) -> Operator | None:
    if authorization and authorization.lower().startswith("bearer "):
        from .services.account_security import read_token
        claims = read_token(authorization[7:].strip())
        if claims:
            return Operator(name=str(claims.get("name", "Operator"))[:80], open_access=False, role=str(claims.get("role", "operator")), username=str(claims.get("sub", "")))
    name = (x_operator_name or "operator").strip()[:80] or "operator"
    if settings.operator_api_key:
        if x_operator_key and hmac.compare_digest(x_operator_key.encode(), settings.operator_api_key.encode()):
            return Operator(name=name, open_access=False)
        return None
    if settings.app_env == "production":
        return None  # production never runs open: a key MUST be configured
    return Operator(name=name, open_access=True)


def optional_operator(
    x_operator_key: Annotated[str | None, Header()] = None,
    x_operator_name: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Operator | None:
    """The operator if valid bearer token or legacy operator key is present."""
    return _operator_from_headers(x_operator_key, x_operator_name, authorization)


def require_operator(
    x_operator_key: Annotated[str | None, Header()] = None,
    x_operator_name: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Operator:
    op = _operator_from_headers(x_operator_key, x_operator_name, authorization)
    if op is None:
        raise HTTPException(401, "Sign in with your ReliefSync account to perform this action.")
    return op


OperatorDep = Annotated[Operator, Depends(require_operator)]
OptionalOperatorDep = Annotated[Operator | None, Depends(optional_operator)]


class RateLimiter:
    """Sliding-window limiter keyed by client address. In-memory: per process, resets on restart.
    It slows accidental floods; it is not a substitute for a reverse proxy / WAF in production."""

    registry: list["RateLimiter"] = []

    def __init__(self, scope: str, per_minute: int | None = None):
        RateLimiter.registry.append(self)
        self.scope = scope
        self.per_minute = per_minute
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def __call__(self, request: Request) -> None:
        limit = self.per_minute or settings.rate_limit_public_per_minute
        if limit <= 0:
            return
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= limit:
                raise HTTPException(429, f"Too many requests ({self.scope}). Please wait a minute and try again.")
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def audit(db: Session, actor: str, action: str, entity_type: str, entity_id: int | None = None, **detail) -> None:
    """Append an audit record in the caller's transaction (committed together with the change it describes)."""
    from .models import AuditLog

    db.add(AuditLog(actor=actor, action=action, entity_type=entity_type, entity_id=entity_id, detail=json.dumps(detail, default=str)))
