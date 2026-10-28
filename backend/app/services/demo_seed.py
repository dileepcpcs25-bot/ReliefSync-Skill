"""Seed clearly synthetic local exercise data so a new dashboard is populated."""
from datetime import datetime, timezone
import csv
import hashlib
from pathlib import Path

from sqlalchemy import select

from ..database import SessionLocal
from ..models import Assignment, Disaster, ExternalEvent, InventoryItem, OperatorUser, ResourceAllocation, Shelter, Volunteer
from .account_security import hash_password


def seed_demo_data():
    db = SessionLocal()
    try:
        if not db.scalar(select(OperatorUser.id).where(OperatorUser.username == "admin")):
            db.add(OperatorUser(username="admin", display_name="ReliefSync Admin", role="admin", password_hash=hash_password("ReliefSync-admin-2026!")))
            db.commit()

        # Import the dated worldwide source snapshot once; these are observations, not verified incidents.
        snapshot = (Path(__file__).resolve().parents[2] / ".." / "sample-data" / "world_disaster_observations.csv").resolve()
        if snapshot.exists() and not db.scalar(select(ExternalEvent.id).limit(1)):
            with snapshot.open(newline="", encoding="utf-8-sig") as source:
                for row in csv.DictReader(source):
                    try:
                        observed = datetime.strptime(row["observed_at"], "%d-%m-%Y %H:%M:%S").replace(tzinfo=timezone.utc)
                        lat, lng = float(row["latitude"]), float(row["longitude"])
                        title = row["title"].strip()[:300]
                        identity = hashlib.sha256(f"{row['source']}|{title}|{lat}|{lng}|{observed.isoformat()}".encode()).hexdigest()[:32]
                        db.add(ExternalEvent(source=row["source"], external_id=f"snapshot-{identity}", event_type=row["event_type"][:40], title=title, latitude=lat, longitude=lng, severity_estimate=row["severity_estimate"] if row["severity_estimate"] in {"Low", "Medium", "High", "Critical"} else "Low", country=row.get("country") or None, observed_at=observed, retrieved_at=datetime.now(timezone.utc), first_retrieved_at=datetime.now(timezone.utc), url=row.get("url") or None, source_alert_level=row.get("source_alert_level") or None, attributes='{"dataset":"included world snapshot; source attribution retained"}'))
                    except (KeyError, ValueError):
                        continue
            db.flush()

        disaster = db.scalar(select(Disaster).where(Disaster.location == "DEMO Exercise - Chennai"))
        if disaster is None:
            disaster = Disaster(disaster_type="Flood exercise", location="DEMO Exercise - Chennai", severity="High", people_affected=1200, description="Synthetic training scenario for demonstrating volunteer assignment, shelter capacity and map heat intensity. Not a live event.", status="Active", latitude=13.0827, longitude=80.2707, location_source="manual")
            db.add(disaster)
            db.flush()

        volunteer_specs = [
            ("Demo Volunteer Asha", "+910000000101", "first aid, logistics", "Chennai", 13.06, 80.25),
            ("Demo Volunteer Ravi", "+910000000102", "shelter support", "Chennai", 13.10, 80.28),
            ("Demo Volunteer Meera", "+910000000103", "medical, first aid", "Chennai", 13.04, 80.23),
            ("Demo Volunteer Arun", "+910000000104", "transport, logistics", "Chennai", 13.12, 80.29),
            ("Demo Volunteer Leela", "+910000000105", "communications", "Chennai", 13.08, 80.31),
        ]
        volunteers = []
        for name, phone, skills, location, lat, lng in volunteer_specs:
            volunteer = db.scalar(select(Volunteer).where(Volunteer.name == name))
            if volunteer is None:
                volunteer = Volunteer(name=name, phone=phone, skills=skills, location=location, availability="Available", latitude=lat, longitude=lng, location_source="manual")
                db.add(volunteer)
                db.flush()
            volunteers.append(volunteer)

        shelter_specs = [
            ("DEMO Chennai Relief Hall", 300, 84, 13.075, 80.265),
            ("DEMO Marina Community Centre", 180, 42, 13.055, 80.282),
            ("DEMO North Chennai School", 220, 96, 13.112, 80.292),
        ]
        for name, capacity, occupancy, lat, lng in shelter_specs:
            if not db.scalar(select(Shelter.id).where(Shelter.name == name)):
                db.add(Shelter(name=name, location="Chennai", total_capacity=capacity, current_occupancy=occupancy, contact="Training record", latitude=lat, longitude=lng, location_source="manual"))

        item_specs = [
            ("DEMO Drinking water", "Water", 800, "cases", "Chennai Training Hub", 150),
            ("DEMO Ready meals", "Food", 220, "packs", "Chennai Training Hub", 100),
            ("DEMO First-aid kits", "Medical", 18, "kits", "Chennai Training Hub", 30),
            ("DEMO Relief blankets", "Shelter", 170, "pieces", "Chennai Training Hub", 50),
            ("DEMO Hygiene kits", "Hygiene", 95, "kits", "Chennai Training Hub", 25),
        ]
        items = {}
        for name, category, quantity, unit, location, threshold in item_specs:
            item = db.scalar(select(InventoryItem).where(InventoryItem.name == name, InventoryItem.storage_location == location))
            if item is None:
                item = InventoryItem(name=name, category=category, quantity=quantity, unit=unit, storage_location=location, low_stock_threshold=threshold, latitude=13.0827, longitude=80.2707, location_source="manual")
                db.add(item)
                db.flush()
            items[name] = item

        # Give the example dashboard real rows for assignment and allocation totals.
        for volunteer, role in zip(volunteers[:2], ("Water distribution", "Shelter logistics")):
            demo_assignment = db.scalar(select(Assignment.id).where(Assignment.volunteer_id == volunteer.id, Assignment.disaster_id == disaster.id, Assignment.role == role))
            active = db.scalar(select(Assignment.id).where(Assignment.volunteer_id == volunteer.id, Assignment.status == "Active"))
            if demo_assignment is None and active is None:
                db.add(Assignment(volunteer_id=volunteer.id, disaster_id=disaster.id, role=role, status="Active"))
                volunteer.availability = "Assigned"

        allocation_specs = [
            ("DEMO Drinking water", 100, "In Transit", "DEMO Chennai Relief Hall"),
            ("DEMO Ready meals", 80, "Confirmed", "DEMO Marina Community Centre"),
            ("DEMO Relief blankets", 30, "Delivered", "DEMO North Chennai School"),
        ]
        demo_note = "Synthetic dashboard demonstration record; not a real dispatch."
        for item_name, quantity, status, destination in allocation_specs:
            item = items[item_name]
            exists = db.scalar(select(ResourceAllocation.id).where(ResourceAllocation.disaster_id == disaster.id, ResourceAllocation.item_id == item.id, ResourceAllocation.notes == demo_note))
            if exists is None:
                db.add(ResourceAllocation(disaster_id=disaster.id, item_id=item.id, quantity=quantity, destination=destination, status=status, notes=demo_note, destination_latitude=13.08, destination_longitude=80.27, destination_location_source="manual"))

        db.commit()
        # If MongoDB is available, mirror all currently stored source records into its archive.
        from .mongo_archive import archive_observations
        archive_observations(db.scalars(select(ExternalEvent)).all())
    finally:
        db.close()
