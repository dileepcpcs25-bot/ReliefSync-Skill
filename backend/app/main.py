from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .config import settings
from .dependencies import _operator_from_headers
from . import migrations
from .database import Base, engine
from .routers import (
    allocations,
    auth,
    assignments,
    dashboard,
    disasters,
    external,
    geo,
    history,
    intelligence,
    inventory,
    nearby,
    notifications,
    shelters,
    volunteers,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)  # creates only missing tables; never drops or alters existing data
    migrations.upgrade(engine)  # additive columns for older databases; backs the file up first
    if settings.demo_seed_data:
        from .services.demo_seed import seed_demo_data
        seed_demo_data()
    yield


app = FastAPI(
    title="ReliefSync API",
    version="1.1.0",
    description="Disaster relief coordination with transparent, rule-based decision support. "
    "Demonstration system - not a certified emergency-response tool.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def protect_operator_writes(request: Request, call_next):
    public_write_paths = {"/api/auth/login", "/api/auth/login/password", "/api/auth/register", "/api/subscriptions", "/api/subscriptions/confirm", "/api/subscriptions/unsubscribe"}
    if request.url.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path not in public_write_paths:
        operator = _operator_from_headers(request.headers.get("x-operator-key"), request.headers.get("x-operator-name"), request.headers.get("authorization"))
        if operator is None:
            return JSONResponse(status_code=401, content={"detail": "Sign in with your ReliefSync account before making changes."})
    return await call_next(request)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_request: Request, _exc: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "The change violates a data integrity rule."})


@app.get("/health", tags=["Health"])
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "service": "reliefsync-api"}


for module in (dashboard, intelligence, disasters, volunteers, assignments, inventory, shelters, allocations, auth, external, geo, history, nearby, notifications):
    app.include_router(module.router, prefix="/api")

