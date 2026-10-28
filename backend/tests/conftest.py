"""Test fixtures. The app is pointed at a throw-away SQLite file BEFORE it is imported,
so tests can never touch a real database."""
import os
import tempfile
from pathlib import Path

_TMP_DIR = tempfile.mkdtemp(prefix="reliefsync_test_")
TEST_DB = Path(_TMP_DIR) / "reliefsync_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
# Tests must start from a genuinely empty database, even when a developer .env enables demo seeding.
os.environ["DEMO_SEED_DATA"] = "false"
os.environ["APP_ENV"] = "development"
os.environ["MONGODB_URI"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

assert "reliefsync_test" in str(engine.url), "Refusing to run tests against a non-test database"


import httpx  # noqa: E402

from app.config import settings  # noqa: E402
from app.dependencies import RateLimiter  # noqa: E402
from app.services import geocoding, httpclient  # noqa: E402


class MockNet:
    """Fake internet. Routes are matched by substring of the full URL. Any request that matches nothing FAILS the
    test, so automated tests can never reach a real API, SMS provider or mail server."""

    def __init__(self):
        self.routes, self.calls = [], []

    def add(self, pattern, *, status=200, json=None, text=None, exc=None, times=None):
        self.routes.append({"pattern": pattern, "status": status, "json": json, "text": text, "exc": exc, "times": times})

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(request)
        for r in self.routes:
            if r["pattern"] in url and (r["times"] is None or r["times"] > 0):
                if r["times"] is not None:
                    r["times"] -= 1
                if r["exc"]:
                    raise r["exc"]
                if r["json"] is not None:
                    return httpx.Response(r["status"], json=r["json"])
                return httpx.Response(r["status"], text=r["text"] or "")
        raise AssertionError(f"Test attempted an un-mocked network request: {request.method} {url}")

    def urls(self):
        return [str(c.url) for c in self.calls]


@pytest.fixture(autouse=True)
def net(monkeypatch):
    mock = MockNet()
    monkeypatch.setattr(httpclient, "client_factory", lambda: httpx.Client(transport=httpx.MockTransport(mock.handler), headers={"User-Agent": "test"}))
    monkeypatch.setattr(httpclient.time, "sleep", lambda _s: None)
    monkeypatch.setattr(geocoding.time, "sleep", lambda _s: None)
    monkeypatch.setattr(settings, "nominatim_min_interval", 0.0)
    monkeypatch.setattr(settings, "manual_refresh_floor_seconds", 0)
    monkeypatch.setattr(settings, "notifications_mode", "development")
    monkeypatch.setattr(settings, "operator_api_key", "")
    monkeypatch.setattr(settings, "mongodb_uri", "")
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "rate_limit_public_per_minute", 1000)
    for limiter in RateLimiter.registry:
        limiter.reset()
    return mock


@pytest.fixture()
def cfg(monkeypatch):
    """cfg(name=value, ...) overrides settings for one test."""

    def apply(**kw):
        for k, v in kw.items():
            monkeypatch.setattr(settings, k, v)

    return apply


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)  # safe: guarded above, only ever the temp test DB
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def make(client):
    """Factory helpers returning created resource JSON."""

    def disaster(**kw):
        body = {"disaster_type": "Flood", "location": "Chennai", "severity": "High", "people_affected": 1000, **kw}
        r = client.post("/api/disasters", json=body)
        assert r.status_code == 201, r.text
        return r.json()

    def volunteer(**kw):
        body = {"name": "Asha", "phone": "+91 98765 43210", "skills": "First aid", "location": "Chennai", **kw}
        r = client.post("/api/volunteers", json=body)
        assert r.status_code == 201, r.text
        return r.json()

    def item(**kw):
        body = {"name": "Water bottles", "category": "Water", "quantity": 100, "unit": "L", "storage_location": "Depot A", "low_stock_threshold": 10, **kw}
        r = client.post("/api/inventory", json=body)
        assert r.status_code == 201, r.text
        return r.json()

    def shelter(**kw):
        body = {"name": "Relief Camp", "location": "Chennai", "total_capacity": 100, "current_occupancy": 20, **kw}
        r = client.post("/api/shelters", json=body)
        assert r.status_code == 201, r.text
        return r.json()

    return type("Make", (), {"disaster": staticmethod(disaster), "volunteer": staticmethod(volunteer), "item": staticmethod(item), "shelter": staticmethod(shelter)})
