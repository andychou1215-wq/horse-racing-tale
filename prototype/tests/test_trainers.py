"""cli/trainers.py 純函式的單元測試（跟 xlsx 無關，這個原型自己的假設值行為）。"""
from __future__ import annotations

import pytest

from cli.trainers import (
    MAX_HORSES_REDUCED_EFFICIENCY,
    Trainer,
    can_assign,
    capacity_multiplier,
    fatigue_relief_bonus,
    generate_trainer_market,
    training_multiplier,
)


def make_trainer(**overrides) -> Trainer:
    defaults = dict(name="測試教練", specialty="速度訓練", skill_level=3, hire_fee=2400.0, weekly_salary=600.0)
    defaults.update(overrides)
    return Trainer(**defaults)


def test_no_trainer_gives_baseline_multiplier():
    assert training_multiplier(None, "速度") == 1.0


def test_matching_specialty_increases_multiplier_with_level():
    low = training_multiplier(make_trainer(specialty="速度訓練", skill_level=1), "速度")
    high = training_multiplier(make_trainer(specialty="速度訓練", skill_level=5), "速度")
    assert 1.0 < low < high


def test_non_matching_specialty_gives_baseline_multiplier():
    t = make_trainer(specialty="速度訓練", skill_level=5)
    assert training_multiplier(t, "耐力") == 1.0


def test_fatigue_relief_bonus_only_for_status_management_specialty():
    assert fatigue_relief_bonus(None) == 0.0
    assert fatigue_relief_bonus(make_trainer(specialty="速度訓練", skill_level=5)) == 0.0
    assert fatigue_relief_bonus(make_trainer(specialty="狀態管理", skill_level=3)) == 3.0


def test_capacity_multiplier_full_efficiency_up_to_8():
    for count in (1, 4, 8):
        assert capacity_multiplier(count) == 1.0


def test_capacity_multiplier_reduced_between_9_and_12():
    for count in (9, 10, 12):
        assert capacity_multiplier(count) < 1.0


def test_capacity_multiplier_raises_above_12():
    with pytest.raises(ValueError):
        capacity_multiplier(13)


def test_can_assign_respects_cap():
    assert can_assign(MAX_HORSES_REDUCED_EFFICIENCY - 1) is True
    assert can_assign(MAX_HORSES_REDUCED_EFFICIENCY) is False


def test_generate_trainer_market_returns_requested_count_with_unique_names():
    market = generate_trainer_market(count=4)
    assert len(market) == 4
    assert len({t.name for t in market}) == 4


def test_generate_trainer_market_hire_fee_and_salary_scale_with_level():
    market = generate_trainer_market(count=10)
    for t in market:
        assert t.hire_fee == pytest.approx(800.0 * t.skill_level)
        assert t.weekly_salary == pytest.approx(200.0 * t.skill_level)
