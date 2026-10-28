from collections import defaultdict
import httpx
import json
import os

from fastapi import APIRouter
from sqlalchemy import select

from ..dependencies import DbSession, get_or_404
from ..models import Disaster, InventoryItem, ResourceAllocation
from ..schemas import PriorityDetail, PriorityEntry, PriorityFactor, PriorityResponse, RecommendationOut, RecommendationsResponse
from ..services.allocation import DisasterInfo, ItemInfo, recommend
from ..services.priority import rank_disasters, score_disaster
from ..config import settings

router = APIRouter(prefix="/intelligence", tags=["Intelligence"])


def build_priority_entries(db, limit: int | None = None) -> list[PriorityEntry]:
    disasters = db.scalars(select(Disaster)).all()
    by_id = {d.id: d for d in disasters}
    ranked = rank_disasters(disasters)[:limit]
    return [
        PriorityEntry(
            rank=r.rank,
            score=r.result.score,
            level=r.result.level,
            explanation=r.result.explanation,
            factors=[PriorityFactor(**vars(f)) for f in r.result.factors],
            disaster=by_id[r.disaster_id],
        )
        for r in ranked
    ]


@router.get("/priority", response_model=PriorityResponse)
def disaster_priority(db: DbSession):
    """Ranked non-resolved disasters, recomputed from current database values."""
    return PriorityResponse(items=build_priority_entries(db))


@router.get("/priority/{disaster_id}", response_model=PriorityDetail)
def disaster_priority_detail(disaster_id: int, db: DbSession):
    """Score breakdown for one disaster (used by detail views). Resolved incidents are shown with score 0 and
    `ranked=false`: they stay in the database for history but are excluded from rankings."""
    d = get_or_404(db, Disaster, disaster_id, "Disaster")
    result = score_disaster(d.severity, d.people_affected, d.status)
    rank = next((r.rank for r in rank_disasters(db.scalars(select(Disaster)).all()) if r.disaster_id == d.id), 0)
    entry = PriorityEntry(
        rank=rank, score=result.score, level=result.level, explanation=result.explanation,
        factors=[PriorityFactor(**vars(f)) for f in result.factors], disaster=d,
    )
    return PriorityDetail(ranked=d.status != "Resolved", entry=entry)


@router.get("/recommendations", response_model=RecommendationsResponse)
def allocation_recommendations(db: DbSession):
    """Read-only suggestions. Nothing is deducted until an allocation is confirmed."""
    disasters = db.scalars(select(Disaster).where(Disaster.status != "Resolved")).all()
    items = db.scalars(select(InventoryItem).where(InventoryItem.quantity > 0)).all()
    allocated: dict[tuple[int, str], int] = defaultdict(int)
    rows = db.execute(
        select(ResourceAllocation.disaster_id, InventoryItem.category, ResourceAllocation.quantity)
        .join(InventoryItem, InventoryItem.id == ResourceAllocation.item_id)
        .where(ResourceAllocation.status != "Cancelled")
    )
    for disaster_id, category, quantity in rows:
        allocated[(disaster_id, category)] += quantity

    infos = []
    for d in disasters:
        p = score_disaster(d.severity, d.people_affected, d.status)
        infos.append(DisasterInfo(d.id, d.label, d.location, d.status, d.people_affected, p.score, p.level))
    item_infos = [ItemInfo(i.id, i.name, i.category, i.quantity, i.unit) for i in items]
    recs = recommend(infos, item_infos, allocated)
    return RecommendationsResponse(items=[RecommendationOut.model_validate(r) for r in recs])


@router.get("/explain/{disaster_id}")
def explain_priority_report(disaster_id: int, db: DbSession):
    """Explain recorded score factors; optionally ask a local Ollama model to summarize those facts."""
    disaster = get_or_404(db, Disaster, disaster_id, "Disaster")
    result = score_disaster(disaster.severity, disaster.people_affected, disaster.status)
    factors = [vars(f) for f in result.factors]
    baseline = f"{disaster.label} has a rule-based score of {result.score} ({result.level}). The recorded severity is {disaster.severity} and the recorded affected population is {disaster.people_affected:,}. {result.explanation} This summary uses only current database values; verify inputs with an incident lead."
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    try:
        response = httpx.post(f"{base_url}/api/chat", json={"model": model, "stream": False, "messages": [
            {"role": "system", "content": "Explain an operational decision-support score in plain language. Use only supplied facts, do not predict outcomes, invent resources, or issue commands. State what inputs could change the ranking."},
            {"role": "user", "content": json.dumps({"incident": disaster.label, "severity": disaster.severity, "affected_people": disaster.people_affected, "status": disaster.status, "score": result.score, "level": result.level, "rule_explanation": result.explanation, "factors": factors})}
        ]}, timeout=8.0)
        response.raise_for_status()
        explanation = response.json().get("message", {}).get("content", "").strip()
        if explanation:
            return {"disaster_id": disaster.id, "score": result.score, "level": result.level, "explanation": explanation, "provider": f"Local Ollama: {model}", "factors": factors}
    except (httpx.HTTPError, ValueError, KeyError):
        pass
    return {"disaster_id": disaster.id, "score": result.score, "level": result.level, "explanation": baseline, "provider": "Transparent rule explanation (local LLM unavailable)", "factors": factors}

