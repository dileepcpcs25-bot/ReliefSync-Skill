"""Optional MongoDB archive for fetched third-party observations.

Operational records remain in the relational database; MongoDB stores a queryable archive
of global source observations using the local MongoDB default or MONGODB_URI override.
"""
from datetime import datetime, timezone

from ..config import settings


def mongo_status() -> dict:
    if not settings.mongodb_uri:
        return {"configured": False, "connected": False}
    from pymongo import MongoClient

    client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=1500)
    try:
        client.admin.command("ping")
        collection = client[settings.mongodb_database]["external_observations"]
        return {"configured": True, "connected": True, "database": settings.mongodb_database,
                "observation_count": collection.count_documents({})}
    except Exception as exc:
        return {"configured": True, "connected": False, "error": type(exc).__name__}
    finally:
        client.close()


def archive_observations(events) -> dict:
    if not settings.mongodb_uri:
        return {"configured": False, "status": "disabled", "archived": 0}
    from pymongo import MongoClient, UpdateOne

    client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=2500)
    try:
        collection = client[settings.mongodb_database]["external_observations"]
        collection.create_index([("source", 1), ("external_id", 1)], unique=True)
        collection.create_index([("location", "2dsphere")])
        now = datetime.now(timezone.utc)
        operations = [
            UpdateOne(
                {"source": event.source, "external_id": event.external_id},
                {"$set": {
                    "event_type": event.event_type, "title": event.title,
                    "location": {"type": "Point", "coordinates": [event.longitude, event.latitude]},
                    "severity_estimate": event.severity_estimate, "magnitude": event.magnitude,
                    "country": event.country, "observed_at": event.observed_at,
                    "source_updated_at": event.source_updated_at, "url": event.url,
                    "attributes": event.attributes, "archived_at": now,
                }, "$setOnInsert": {"first_archived_at": now}},
                upsert=True,
            ) for event in events
        ]
        if operations:
            collection.bulk_write(operations, ordered=False)
        return {"configured": True, "status": "ok", "archived": len(operations), "database": settings.mongodb_database}
    except Exception as exc:
        return {"configured": True, "status": "error", "archived": 0, "message": type(exc).__name__}
    finally:
        client.close()
