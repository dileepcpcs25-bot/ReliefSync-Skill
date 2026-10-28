"""Pure business-logic tests (no database, no web framework)."""
from types import SimpleNamespace as NS

import pytest

from app.services.allocation import DisasterInfo, ItemInfo, recommend
from app.services.priority import level_for_score, population_points, rank_disasters, score_disaster


def test_population_tier_boundaries():
    assert [population_points(n) for n in (0, 1, 99, 100, 999, 1000, 9999, 10000, 99999, 100000)] == [0, 5, 5, 12, 12, 22, 22, 30, 30, 35]


def test_negative_population_rejected():
    with pytest.raises(ValueError):
        population_points(-1)


def test_level_boundaries():
    assert [level_for_score(s) for s in (0, 29, 30, 49, 50, 69, 70, 90)] == ["Low", "Low", "Medium", "Medium", "High", "High", "Critical", "Critical"]


def test_score_active_critical_large_population():
    r = score_disaster("Critical", 100_000, "Active")
    assert (r.score, r.level) == (90, "Critical")
    assert "Critical = 55" in r.explanation


def test_monitoring_multiplier_and_resolved_zero():
    assert score_disaster("Critical", 100_000, "Monitoring").score == 54
    assert score_disaster("Critical", 100_000, "Resolved").score == 0


def test_input_normalisation_and_validation():
    assert score_disaster("  high ", 0, "active").score == 40
    for bad in (("Extreme", 1, "Active"), ("High", 1, "Paused")):
        with pytest.raises(ValueError):
            score_disaster(*bad)


def test_ranking_order_ties_and_resolved_excluded():
    ds = [
        NS(id=1, severity="Low", people_affected=10, status="Active"),
        NS(id=2, severity="Critical", people_affected=50_000, status="Active"),
        NS(id=3, severity="High", people_affected=500, status="Resolved"),
        NS(id=4, severity="Medium", people_affected=5, status="Active"),
        NS(id=5, severity="Medium", people_affected=5, status="Active"),
    ]
    ranked = rank_disasters(ds)
    assert [r.disaster_id for r in ranked] == [2, 4, 5, 1]  # resolved (3) absent; tie 4/5 by id
    assert [r.rank for r in ranked] == [1, 2, 3, 4]


def _d(id, people, level="High", score=60, status="Active"):
    return DisasterInfo(id, f"D{id}", f"Loc{id}", status, people, score, level)


def test_recommend_empty_inputs():
    assert recommend([], []) == []
    assert recommend([_d(1, 100)], []) == []
    assert recommend([], [ItemInfo(1, "Rice", "Food", 50, "kg")]) == []


def test_recommend_never_exceeds_stock_across_disasters():
    items = [ItemInfo(1, "Water", "Water", 100, "L")]
    recs = recommend([_d(1, 1000, "Critical", 80), _d(2, 1000, "High", 60)], items)
    assert sum(r.suggested_quantity for r in recs) <= 100
    assert recs[0].disaster_id == 1  # higher priority claims stock first
    assert recs[0].suggested_quantity == 60  # 60% share of 100


def test_recommend_skips_resolved_and_other_category_and_zero_stock():
    items = [ItemInfo(1, "Misc", "Other", 50, "u"), ItemInfo(2, "Rice", "Food", 0, "kg")]
    assert recommend([_d(1, 100), _d(2, 100, status="Resolved")], items) == []


def test_recommend_subtracts_existing_allocations():
    items = [ItemInfo(1, "Rice", "Food", 1000, "kg")]
    # target = 100 people * 2 = 200; 200 already allocated -> nothing left to recommend
    assert recommend([_d(1, 100)], items, {(1, "Food"): 200}) == []
    recs = recommend([_d(1, 100)], items, {(1, "Food"): 150})
    assert recs[0].remaining_need == 50 and recs[0].suggested_quantity == 50


def test_recommend_is_deterministic_and_includes_reasoning():
    items = [ItemInfo(1, "Rice", "Food", 500, "kg"), ItemInfo(2, "Water", "Water", 500, "L")]
    a = recommend([_d(1, 300)], items)
    assert a == recommend([_d(1, 300)], items)
    assert all(r.reasoning and r.suggested_quantity >= 1 for r in a)
