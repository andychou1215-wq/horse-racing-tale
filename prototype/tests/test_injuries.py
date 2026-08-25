"""cli/injuries.py 純函式的單元測試（跟 xlsx 無關，這個原型自己的假設值行為）。"""
from __future__ import annotations

import pytest

from cli.injuries import (
    INJURY_TYPES,
    MAX_HORSES_REDUCED_EFFICIENCY,
    SEVERITIES,
    can_assign,
    capacity_multiplier,
    injury_risk_tier,
    recovery_weeks_per_tick,
    roll_injury,
    vet_prevention_multiplier,
)
from cli.vets import Vet


def make_vet(**overrides) -> Vet:
    defaults = dict(name="測試獸醫", skill_level=3, hire_fee=3000.0, weekly_salary=750.0)
    defaults.update(overrides)
    return Vet(**defaults)


def test_injury_risk_tier_ranges_from_無_to_高():
    assert injury_risk_tier(health=100, fatigue=0) == "無"
    assert injury_risk_tier(health=0, fatigue=100) == "高"


def test_worse_health_or_fatigue_never_lowers_risk_tier():
    tiers_order = {"無": 0, "低": 1, "中": 2, "高": 3}
    base = injury_risk_tier(health=80, fatigue=40)
    worse_health = injury_risk_tier(health=40, fatigue=40)
    worse_fatigue = injury_risk_tier(health=80, fatigue=90)
    assert tiers_order[worse_health] >= tiers_order[base]
    assert tiers_order[worse_fatigue] >= tiers_order[base]


def test_vet_prevention_multiplier_no_vet_is_baseline():
    assert vet_prevention_multiplier(None) == 1.0


def test_vet_prevention_multiplier_reduces_with_level():
    low = vet_prevention_multiplier(make_vet(skill_level=1))
    high = vet_prevention_multiplier(make_vet(skill_level=5))
    assert 0.0 < high < low < 1.0


def test_roll_injury_never_triggers_when_chance_forced_to_zero(monkeypatch):
    import random

    monkeypatch.setattr(random, "random", lambda: 0.999)
    result = roll_injury(health=100, fatigue=0, is_racing_this_week=False, recent_light_injury=False)
    assert result is None


def test_roll_injury_always_triggers_when_chance_forced_to_certain(monkeypatch):
    import random

    monkeypatch.setattr(random, "random", lambda: 0.0)
    result = roll_injury(health=0, fatigue=100, is_racing_this_week=True, recent_light_injury=False)
    assert result is not None
    assert result.severity in SEVERITIES
    assert result.weeks_remaining > 0


def test_all_injury_types_have_valid_severity_keys():
    assert set(INJURY_TYPES.keys()) == set(SEVERITIES)
    for severity, types in INJURY_TYPES.items():
        assert len(types) > 0
        for t in types:
            assert "name" in t and "affected_stats" in t


def test_recovery_weeks_per_tick_no_vet_is_one_week():
    assert recovery_weeks_per_tick(None) == 1


def test_recovery_weeks_per_tick_increases_with_vet_level():
    low = recovery_weeks_per_tick(make_vet(skill_level=1))
    high = recovery_weeks_per_tick(make_vet(skill_level=5))
    assert high >= low >= 1


def test_capacity_multiplier_full_efficiency_up_to_5():
    for count in (1, 3, 5):
        assert capacity_multiplier(count) == 1.0


def test_capacity_multiplier_reduced_between_6_and_8():
    for count in (6, 7, 8):
        assert capacity_multiplier(count) < 1.0


def test_capacity_multiplier_raises_above_8():
    with pytest.raises(ValueError):
        capacity_multiplier(9)


def test_can_assign_respects_cap():
    assert can_assign(MAX_HORSES_REDUCED_EFFICIENCY - 1) is True
    assert can_assign(MAX_HORSES_REDUCED_EFFICIENCY) is False
