"""Deterministic, explainable disaster priority scoring.

score = round((severity_points + population_points) * status_multiplier)

This is a transparent rule-based heuristic for decision support. It is NOT a
validated predictor of casualties or real-world outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

SEVERITY_POINTS = {"Low": 10, "Medium": 25, "High": 40, "Critical": 55}
# (minimum people affected, points) checked from the largest tier down.
POPULATION_TIERS = ((100_000, 35), (10_000, 30), (1_000, 22), (100, 12), (1, 5), (0, 0))
STATUS_MULTIPLIER = {"Active": 1.0, "Monitoring": 0.6, "Resolved": 0.0}
LEVEL_THRESHOLDS = ((70, "Critical"), (50, "High"), (30, "Medium"), (0, "Low"))


@dataclass(frozen=True)
class PriorityFactor:
    name: str
    input: str
    points: float
    basis: str


@dataclass(frozen=True)
class PriorityResult:
    score: int
    level: str
    explanation: str
    factors: tuple[PriorityFactor, ...] = ()


@dataclass(frozen=True)
class RankedDisaster:
    disaster_id: int
    rank: int
    result: PriorityResult


def population_points(people_affected: int) -> int:
    if people_affected < 0:
        raise ValueError("people_affected must be non-negative")
    return next(points for minimum, points in POPULATION_TIERS if people_affected >= minimum)


def level_for_score(score: int) -> str:
    return next(level for threshold, level in LEVEL_THRESHOLDS if score >= threshold)


def score_disaster(severity: str, people_affected: int, status: str) -> PriorityResult:
    severity = str(severity).strip().title()
    status = str(status).strip().title()
    if severity not in SEVERITY_POINTS:
        raise ValueError(f"Unknown severity: {severity!r}")
    if status not in STATUS_MULTIPLIER:
        raise ValueError(f"Unknown status: {status!r}")
    people = int(people_affected)

    sev_pts, pop_pts, mult = SEVERITY_POINTS[severity], population_points(people), STATUS_MULTIPLIER[status]
    score = round((sev_pts + pop_pts) * mult)
    if status == "Resolved":
        explanation = "Resolved incidents are not prioritised (score 0)."
    else:
        explanation = (
            f"Severity {severity} = {sev_pts} pts; {people:,} people affected = {pop_pts} pts; "
            f"status {status} multiplier x{mult:g}."
        )
    factors = (
        PriorityFactor("Severity", severity, float(sev_pts), "Rating entered by a ReliefSync user (not independently verified)"),
        PriorityFactor("People affected", f"{people:,}", float(pop_pts), "Reported figure - an unverified estimate"),
        PriorityFactor("Status multiplier", status, float(mult), "Operational record (set by an operator)"),
    )
    return PriorityResult(score=score, level=level_for_score(score), explanation=explanation, factors=factors)


def rank_disasters(disasters: Iterable) -> list[RankedDisaster]:
    """Rank non-resolved disasters (objects with id, severity, people_affected, status).

    Order: score desc, then people affected desc, then id asc (stable and deterministic).
    Resolved disasters are excluded from the ranking.
    """
    scored = [
        (d, score_disaster(d.severity, d.people_affected, d.status))
        for d in disasters
        if str(d.status).strip().title() != "Resolved"
    ]
    scored.sort(key=lambda pair: (-pair[1].score, -pair[0].people_affected, pair[0].id))
    return [RankedDisaster(d.id, i, r) for i, (d, r) in enumerate(scored, start=1)]
