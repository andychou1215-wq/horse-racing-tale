"""設施系統(cli/facilities.py)的純函式測試，不碰GameState/webapp（那部分在
test_game.py/test_webapp.py 裡）。
"""
from __future__ import annotations

import pytest

from cli.facilities import (
    DEFAULT_LEVEL,
    FACILITY_STAT_MAP,
    FACILITY_TYPES,
    MAX_LEVEL,
    default_facility_levels,
    fatigue_relief_bonus_for_level,
    injury_recovery_bonus_for_level,
    stat_facility,
    training_multiplier_for_level,
    upgrade_cost,
)
from cli.horses import TRAINABLE_STATS


def test_default_facility_levels_are_all_lv2():
    levels = default_facility_levels()
    assert set(levels) == set(FACILITY_TYPES)
    assert all(level == DEFAULT_LEVEL for level in levels.values())


def test_lv2_training_multiplier_matches_old_fixed_assumption():
    """向下相容的核心斷言：Lv2(預設)算出來要剛好等於原本的FIXED_FACILITY_MULTIPLIER=1.1。"""
    assert training_multiplier_for_level(DEFAULT_LEVEL) == pytest.approx(1.1)


def test_training_multiplier_increases_with_level():
    values = [training_multiplier_for_level(lv) for lv in range(1, MAX_LEVEL + 1)]
    assert values == sorted(values)
    assert len(set(values)) == MAX_LEVEL


def test_fatigue_relief_bonus_is_zero_at_or_below_default_level():
    assert fatigue_relief_bonus_for_level(1) == 0
    assert fatigue_relief_bonus_for_level(DEFAULT_LEVEL) == 0
    assert fatigue_relief_bonus_for_level(DEFAULT_LEVEL + 1) > 0
    assert fatigue_relief_bonus_for_level(MAX_LEVEL) > fatigue_relief_bonus_for_level(DEFAULT_LEVEL + 1)


def test_injury_recovery_bonus_is_zero_at_or_below_default_level():
    assert injury_recovery_bonus_for_level(1) == 0
    assert injury_recovery_bonus_for_level(DEFAULT_LEVEL) == 0
    assert injury_recovery_bonus_for_level(MAX_LEVEL) > 0


def test_upgrade_cost_increases_with_level_and_rejects_max_level():
    costs = [upgrade_cost(lv) for lv in range(1, MAX_LEVEL)]
    assert costs == sorted(costs)
    assert len(set(costs)) == len(costs)
    with pytest.raises(ValueError):
        upgrade_cost(MAX_LEVEL)


def test_every_trainable_stat_maps_to_a_facility_or_is_intentionally_unmapped():
    """9項可訓練屬性理論上都該有對應設施；目前設計上全部都有對應（見模組docstring）。"""
    mapped_stats = {s for stats in FACILITY_STAT_MAP.values() for s in stats}
    for stat in TRAINABLE_STATS:
        assert stat_facility(stat) is not None, f"{stat} 沒有對應設施"
        assert stat in mapped_stats
