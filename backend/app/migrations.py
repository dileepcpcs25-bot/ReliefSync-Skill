"""Additive, non-destructive schema upgrade for databases created by earlier ReliefSync versions.

`Base.metadata.create_all` creates missing TABLES but never alters existing ones. This module adds the new
COLUMNS (and indexes) that the geographic / notification features need to tables that already exist.

Safety rules
* Only `ALTER TABLE ... ADD COLUMN` and `CREATE INDEX IF NOT EXISTS` are ever issued. No data is deleted,
  rewritten or replaced, and no sample data is inserted.
* Before the first change, a consistent copy of the SQLite file is written to `<data dir>/backups/`.
* Rollback: stop the app and copy the backup file over the database file. (The added columns are all nullable
  or have defaults, so older code keeps working against an upgraded database.)
* Range checks for coordinates are added as column-level CHECKs. The "latitude and longitude come together"
  rule cannot be added to an existing table by SQLite, so the API enforces it for those tables.

Run manually:  python -m app.migrations --check   (report only)   |   python -m app.migrations   (apply)
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine, make_url

LAT = "REAL CHECK ({c} IS NULL OR ({c} >= -90 AND {c} <= 90))"
LNG = "REAL CHECK ({c} IS NULL OR ({c} >= -180 AND {c} <= 180))"


def _geo(prefix: str = "") -> list[tuple[str, str]]:
    lat, lng = f"{prefix}latitude", f"{prefix}longitude"
    cols = [(lat, LAT.format(c=lat)), (lng, LNG.format(c=lng))]
    cols.append((f"{prefix}location_source", "VARCHAR(12)"))
    return cols


ADDITIONS: dict[str, list[tuple[str, str]]] = {
    "disasters": [
        *_geo(),
        ("location_approximate", "BOOLEAN NOT NULL DEFAULT 0"),
        ("origin", "VARCHAR(20) NOT NULL DEFAULT 'user'"),
        ("external_event_id", "INTEGER REFERENCES external_events(id) ON DELETE SET NULL"),
    ],
    "volunteers": [*_geo(), ("location_approximate", "BOOLEAN NOT NULL DEFAULT 0"), ("sms_opt_in", "BOOLEAN NOT NULL DEFAULT 0")],
    "shelters": [*_geo(), ("location_approximate", "BOOLEAN NOT NULL DEFAULT 0")],
    "inventory_items": [*_geo(), ("location_approximate", "BOOLEAN NOT NULL DEFAULT 0")],
    "resource_allocations": [
        ("destination_latitude", LAT.format(c="destination_latitude")),
        ("destination_longitude", LNG.format(c="destination_longitude")),
        ("destination_location_source", "VARCHAR(12)"),
    ],
}
INDEXES = [
    ("ix_disasters_latitude", "disasters", "latitude"),
    ("ix_volunteers_latitude", "volunteers", "latitude"),
    ("ix_shelters_latitude", "shelters", "latitude"),
    ("ix_inventory_items_latitude", "inventory_items", "latitude"),
]


def pending_changes(engine: Engine) -> list[tuple[str, str, str]]:
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    pending = []
    for table, columns in ADDITIONS.items():
        if table not in existing_tables:
            continue  # create_all will build it complete
        have = {c["name"] for c in insp.get_columns(table)}
        pending.extend((table, name, ddl) for name, ddl in columns if name not in have)
    return pending


def backup_sqlite(engine: Engine) -> Path | None:
    url = make_url(engine.url.render_as_string(hide_password=False))
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    src = Path(url.database)
    if not src.exists() or src.stat().st_size == 0:
        return None
    dest_dir = src.parent / "backups"
    dest_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = dest_dir / f"{src.stem}-pre-upgrade-{stamp}{src.suffix}"
    with sqlite3.connect(src) as source, sqlite3.connect(dest) as target:
        source.backup(target)  # consistent online copy, safe with WAL
    return dest


def upgrade(engine: Engine, *, dry_run: bool = False) -> dict:
    pending = pending_changes(engine)
    result = {"pending": [f"{t}.{c}" for t, c, _ in pending], "applied": [], "backup": None}
    if dry_run or not pending:
        return result
    backup = backup_sqlite(engine)
    result["backup"] = str(backup) if backup else None
    with engine.begin() as conn:
        for table, name, ddl in pending:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
            result["applied"].append(f"{table}.{name}")
        for index_name, table, column in INDEXES:
            if any(t == table and c == column for t, c, _ in pending):
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({column})"))
    return result


if __name__ == "__main__":  # pragma: no cover
    from .database import Base, engine as _engine

    if "--check" not in sys.argv:
        Base.metadata.create_all(_engine)
    print(upgrade(_engine, dry_run="--check" in sys.argv))
