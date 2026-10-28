"""Rule-based resource recommendation engine. Pure functions: never touches the database.

Rules
1. Disasters are processed by priority score (highest first); Resolved ones are skipped.
2. Each category has a documented units-per-person target (PER_PERSON_UNITS).
   need = ceil(people_affected * units_per_person) - quantity already allocated
   to that disaster in that category (non-cancelled allocations).
3. A disaster may claim at most a priority-dependent share of an item's *remaining*
   stock in a single pass (PRIORITY_SHARE), so one incident cannot drain everything.
4. Stock is tracked across disasters within one run: the total recommended for an
   item never exceeds its current quantity.
5. Category "Other" has no target and is never recommended automatically.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping

PER_PERSON_UNITS = {
    "Water": 3.0,
    "Food": 2.0,
    "Medical": 0.2,
    "Shelter": 0.25,
    "Clothing": 1.0,
    "Hygiene": 0.5,
}
PRIORITY_SHARE = {"Critical": 0.6, "High": 0.4, "Medium": 0.25, "Low": 0.1}


@dataclass(frozen=True)
class DisasterInfo:
    id: int
    label: str
    location: str
    status: str
    people_affected: int
    priority_score: int
    priority_level: str


@dataclass(frozen=True)
class ItemInfo:
    id: int
    name: str
    category: str
    quantity: int
    unit: str


@dataclass(frozen=True)
class Recommendation:
    disaster_id: int
    disaster_label: str
    priority_level: str
    priority_score: int
    item_id: int
    item_name: str
    category: str
    unit: str
    suggested_quantity: int
    available_quantity: int
    remaining_need: int
    destination: str
    reasoning: str


def recommend(
    disasters: Iterable[DisasterInfo],
    items: Iterable[ItemInfo],
    already_allocated: Mapping[tuple[int, str], int] | None = None,
) -> list[Recommendation]:
    already_allocated = already_allocated or {}
    items = [i for i in items if i.quantity > 0 and i.category in PER_PERSON_UNITS]
    remaining = {i.id: i.quantity for i in items}
    results: list[Recommendation] = []

    eligible = [d for d in disasters if d.status != "Resolved" and d.people_affected > 0]
    for d in sorted(eligible, key=lambda x: (-x.priority_score, -x.people_affected, x.id)):
        share = PRIORITY_SHARE.get(d.priority_level, 0.1)
        for category, per_person in PER_PERSON_UNITS.items():
            target = math.ceil(d.people_affected * per_person)
            need = target - already_allocated.get((d.id, category), 0)
            if need <= 0:
                continue
            candidates = sorted((i for i in items if i.category == category), key=lambda i: (-remaining[i.id], i.id))
            for item in candidates:
                if need <= 0:
                    break
                stock = remaining[item.id]
                if stock <= 0:
                    continue
                qty = min(need, max(1, math.floor(stock * share)), stock)
                results.append(
                    Recommendation(
                        disaster_id=d.id,
                        disaster_label=d.label,
                        priority_level=d.priority_level,
                        priority_score=d.priority_score,
                        item_id=item.id,
                        item_name=item.name,
                        category=category,
                        unit=item.unit,
                        suggested_quantity=qty,
                        available_quantity=stock,
                        remaining_need=need,
                        destination=f"Relief point - {d.location}",
                        reasoning=(
                            f"{d.priority_level} priority (score {d.priority_score}); {d.people_affected:,} people x "
                            f"{per_person:g} {category.lower()} units each = {target:,} target; unmet need {need:,}. "
                            f"Capped at {int(share * 100)}% of the {stock:,} {item.unit} in stock."
                        ),
                    )
                )
                remaining[item.id] -= qty
                need -= qty
    return results
