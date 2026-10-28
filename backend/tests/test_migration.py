"""Upgrading a database created by the previous version must keep every record and add the new columns."""
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app import migrations
from app.database import Base

OLD_SCHEMA = [
    """CREATE TABLE disasters (id INTEGER PRIMARY KEY, disaster_type VARCHAR(60) NOT NULL, location VARCHAR(120) NOT NULL, severity VARCHAR(10) NOT NULL,
       people_affected INTEGER NOT NULL, description TEXT NOT NULL, status VARCHAR(12) NOT NULL, created_at DATETIME, updated_at DATETIME)""",
    """CREATE TABLE volunteers (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, phone VARCHAR(30) NOT NULL, skills VARCHAR(200) NOT NULL,
       location VARCHAR(120) NOT NULL, availability VARCHAR(12) NOT NULL, created_at DATETIME)""",
    """CREATE TABLE inventory_items (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, category VARCHAR(20) NOT NULL, quantity INTEGER NOT NULL,
       unit VARCHAR(30) NOT NULL, storage_location VARCHAR(120) NOT NULL, low_stock_threshold INTEGER NOT NULL, created_at DATETIME, updated_at DATETIME)""",
    """CREATE TABLE shelters (id INTEGER PRIMARY KEY, name VARCHAR(120) NOT NULL, location VARCHAR(120) NOT NULL, total_capacity INTEGER NOT NULL,
       current_occupancy INTEGER NOT NULL, contact VARCHAR(120) NOT NULL, created_at DATETIME, updated_at DATETIME)""",
    """CREATE TABLE resource_allocations (id INTEGER PRIMARY KEY, disaster_id INTEGER NOT NULL, item_id INTEGER NOT NULL, quantity INTEGER NOT NULL,
       destination VARCHAR(160) NOT NULL, status VARCHAR(12) NOT NULL, notes TEXT NOT NULL, created_at DATETIME, updated_at DATETIME)""",
    "INSERT INTO disasters VALUES (1,'Flood','Chennai','High',5000,'old record','Active','2026-01-01','2026-01-01')",
    "INSERT INTO volunteers VALUES (1,'Asha','+91 98765 43210','First aid','Chennai','Available','2026-01-01')",
    "INSERT INTO inventory_items VALUES (1,'Water','Water',50,'L','Depot A',5,'2026-01-01','2026-01-01')",
    "INSERT INTO shelters VALUES (1,'Camp','Chennai',100,10,'044-123','2026-01-01','2026-01-01')",
    "INSERT INTO resource_allocations VALUES (1,1,1,5,'Ward 1','Confirmed','','2026-01-01','2026-01-01')",
]


def make_old_db(path: Path):
    with sqlite3.connect(path) as conn:
        for stmt in OLD_SCHEMA:
            conn.execute(stmt)


def test_upgrade_preserves_records_adds_columns_and_backs_up(tmp_path):
    db = tmp_path / "reliefsync_old.db"
    make_old_db(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    Base.metadata.create_all(engine)  # creates only the NEW tables
    pending = migrations.pending_changes(engine)
    assert any(t == "disasters" and c == "latitude" for t, c, _ in pending)

    result = migrations.upgrade(engine)
    assert result["backup"] and Path(result["backup"]).exists()
    cols = {c["name"] for c in inspect(engine).get_columns("disasters")}
    assert {"latitude", "longitude", "location_source", "location_approximate", "origin", "external_event_id"} <= cols
    assert "sms_opt_in" in {c["name"] for c in inspect(engine).get_columns("volunteers")}

    with engine.connect() as conn:  # nothing lost, nothing overwritten, defaults sensible
        row = conn.execute(text("SELECT disaster_type, location, people_affected, description, latitude, origin, location_approximate FROM disasters")).one()
        assert tuple(row) == ("Flood", "Chennai", 5000, "old record", None, "user", 0)
        assert conn.execute(text("SELECT name, phone, sms_opt_in FROM volunteers")).one() == ("Asha", "+91 98765 43210", 0)
        assert conn.execute(text("SELECT quantity FROM inventory_items")).scalar() == 50
        assert conn.execute(text("SELECT current_occupancy FROM shelters")).scalar() == 10
        assert conn.execute(text("SELECT destination, destination_latitude FROM resource_allocations")).one() == ("Ward 1", None)
    # the backup still holds the ORIGINAL schema (so a rollback is a file copy)
    with sqlite3.connect(result["backup"]) as b:
        assert "latitude" not in {r[1] for r in b.execute("PRAGMA table_info(disasters)")}
        assert b.execute("SELECT COUNT(*) FROM disasters").fetchone()[0] == 1


def test_upgrade_is_idempotent_and_dry_run_changes_nothing(tmp_path):
    db = tmp_path / "reliefsync_idem.db"
    make_old_db(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    Base.metadata.create_all(engine)
    assert migrations.upgrade(engine, dry_run=True)["applied"] == []
    assert not (tmp_path / "backups").exists()
    migrations.upgrade(engine)
    again = migrations.upgrade(engine)
    assert again["pending"] == [] and again["applied"] == [] and again["backup"] is None


def test_range_checks_apply_to_migrated_columns(tmp_path):
    db = tmp_path / "reliefsync_chk.db"
    make_old_db(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    Base.metadata.create_all(engine)
    migrations.upgrade(engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE disasters SET latitude = 13.0, longitude = 80.0 WHERE id = 1"))
    import pytest
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("UPDATE disasters SET latitude = 120 WHERE id = 1"))


def test_fresh_database_needs_no_migration(client):
    from app.database import engine

    assert migrations.pending_changes(engine) == []


def test_new_installation_never_touches_existing_rows(client, make):
    d = make.disaster(description="keep me")
    from app import migrations as m
    from app.database import engine

    m.upgrade(engine)
    assert client.get(f"/api/disasters/{d['id']}").json()["description"] == "keep me"
