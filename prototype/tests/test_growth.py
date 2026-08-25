"""成長曲線類型與階段轉換(cli/growth.py + cli/game.py apply_weekly_stat_decline等)的
單元測試。2026/8/24使用者決定補回GDD 3.6完整版(取代舊的FIXED_AGE_STAGE_MULTIPLIER)。
"""
from __future__ import annotations

import random

import pytest

from cli import growth as G
from cli.breeding import generate_foal
from cli.facilities import DEFAULT_LEVEL, decline_mitigation_for_level
from cli.game import apply_weekly_stat_decline, game_state_with_test_horses, train_horse
from cli.horse_market import (
    generate_broodmare_market_horse,
    generate_foal_market_horse,
    generate_market_horse,
    generate_stallion_market_horse,
)
from cli.horses import ALL_STATS, Horse


def make_horse(**overrides) -> Horse:
    defaults = dict(
        name="測試馬",
        stats={s: 60.0 for s in ALL_STATS},
        potential_cap=90.0,
        pace="先",
        age=2,
        growth_curve="一般",
    )
    defaults.update(overrides)
    return Horse(**defaults)


# --------------------------------------------------------------- growth_stage

def test_growth_stage_under_age_2_is_always_rising():
    for curve in G.GROWTH_CURVE_TYPES:
        assert G.growth_stage(curve, 0) == "上升期"
        assert G.growth_stage(curve, 1) == "上升期"


def test_growth_stage_precocious_full_timeline():
    assert G.growth_stage("早熟", 2) == "上升期"
    assert G.growth_stage("早熟", 3) == "巔峰期"
    assert G.growth_stage("早熟", 4) == "停滯期"
    assert G.growth_stage("早熟", 5) == "衰退期"
    assert G.growth_stage("早熟", 20) == "衰退期"  # 衰退期之後恆常維持衰退期，不會有第5階段


def test_growth_stage_normal_full_timeline():
    assert G.growth_stage("一般", 2) == "上升期"
    assert G.growth_stage("一般", 3) == "上升期"
    assert G.growth_stage("一般", 4) == "巔峰期"
    assert G.growth_stage("一般", 5) == "停滯期"
    assert G.growth_stage("一般", 6) == "衰退期"


def test_growth_stage_late_bloomer_peaks_later_than_normal():
    assert G.growth_stage("晚成", 4) == "上升期"
    assert G.growth_stage("晚成", 5) == "巔峰期"
    assert G.growth_stage("晚成", 6) == "停滯期"
    assert G.growth_stage("晚成", 7) == "衰退期"


def test_growth_stage_enduring_has_longest_peak_and_plateau():
    assert G.growth_stage("持久型", 3) == "上升期"
    assert G.growth_stage("持久型", 4) == "巔峰期"
    assert G.growth_stage("持久型", 5) == "巔峰期"
    assert G.growth_stage("持久型", 6) == "停滯期"
    assert G.growth_stage("持久型", 7) == "停滯期"
    assert G.growth_stage("持久型", 8) == "衰退期"


def test_age_stage_multiplier_matches_stage_table():
    assert G.age_stage_multiplier("一般", 2) == pytest.approx(1.15)
    assert G.age_stage_multiplier("一般", 4) == pytest.approx(1.00)
    assert G.age_stage_multiplier("一般", 5) == pytest.approx(0.6)
    assert G.age_stage_multiplier("一般", 6) == pytest.approx(0.3)


def test_horse_growth_stage_method_matches_module_function():
    horse = make_horse(growth_curve="晚成", age=6)
    assert horse.growth_stage() == G.growth_stage("晚成", 6)


# ------------------------------------------------------------- random_growth_curve

def test_random_growth_curve_only_returns_known_types():
    random.seed(0)
    for _ in range(50):
        assert G.random_growth_curve() in G.GROWTH_CURVE_TYPES


# --------------------------------------------------------- individual_decline_factor

def test_individual_decline_factor_higher_stats_decline_slower():
    low = G.individual_decline_factor(guts=0, health=0)
    high = G.individual_decline_factor(guts=100, health=100)
    assert low == pytest.approx(1.3)
    assert high == pytest.approx(0.7)
    assert high < low


def test_weekly_decline_rate_is_positive_and_bounded():
    random.seed(1)
    for _ in range(30):
        rate = G.weekly_decline_rate(guts=50, health=50, facility_mitigation=1.0)
        assert 0 < rate < 0.01  # 基礎值只有0.3%~0.5%，個體係數最多再放大到1.3倍


# --------------------------------------------------------- facilities.decline_mitigation

def test_decline_mitigation_default_level_is_no_mitigation():
    assert decline_mitigation_for_level(DEFAULT_LEVEL) == pytest.approx(1.0)


def test_decline_mitigation_increases_with_level_but_never_reaches_zero():
    m2 = decline_mitigation_for_level(2)
    m5 = decline_mitigation_for_level(5)
    assert m5 < m2
    assert m5 > 0


# --------------------------------------------------- train_horse uses dynamic multiplier

def test_train_horse_uses_growth_curve_multiplier_not_fixed_constant():
    random.seed(2)
    state = game_state_with_test_horses()
    horse = state.horses[0]
    horse.growth_curve = "早熟"
    horse.age = 5  # 早熟型5歲已進入衰退期，倍率應該是0.3而不是舊的固定1.15
    before = horse.stats["速度"]
    train_horse(state, horse, "速度")
    gain_decline_stage = horse.stats["速度"] - before

    horse2 = state.horses[1]
    horse2.growth_curve = "早熟"
    horse2.age = 2  # 早熟型2歲是上升期，倍率1.15
    before2 = horse2.stats["速度"]
    train_horse(state, horse2, "速度")
    gain_rising_stage = horse2.stats["速度"] - before2

    assert gain_decline_stage < gain_rising_stage


# ------------------------------------------------------- apply_weekly_stat_decline

def test_apply_weekly_stat_decline_only_affects_horses_in_decline_stage():
    state = game_state_with_test_horses()
    rising_horse = state.horses[0]
    rising_horse.growth_curve = "一般"
    rising_horse.age = 2  # 上升期

    declining_horse = state.horses[1]
    declining_horse.growth_curve = "一般"
    declining_horse.age = 6  # 衰退期
    before_stats = dict(declining_horse.stats)
    before_rising_stats = dict(rising_horse.stats)

    random.seed(3)
    apply_weekly_stat_decline(state)

    # 上升期的馬完全不受影響
    assert rising_horse.stats == before_rising_stats
    # 衰退期的馬：智力/精神不衰退，其餘至少有一項下降(隨機浮動，用<=避免flaky)
    assert declining_horse.stats["智力"] == before_stats["智力"]
    assert declining_horse.stats["精神"] == before_stats["精神"]
    changed = [s for s in ALL_STATS if s not in G.DECLINE_EXEMPT_STATS
               and declining_horse.stats[s] < before_stats[s]]
    assert len(changed) > 0


def test_apply_weekly_stat_decline_returns_log_line_for_declining_horses():
    state = game_state_with_test_horses()
    horse = state.horses[0]
    horse.growth_curve = "早熟"
    horse.age = 10  # 早熟型早已進入衰退期

    random.seed(4)
    lines = apply_weekly_stat_decline(state)
    assert any(horse.name in line for line in lines)


def test_apply_weekly_stat_decline_never_drops_stat_below_one():
    state = game_state_with_test_horses()
    horse = state.horses[0]
    horse.growth_curve = "早熟"
    horse.age = 10
    for stat in ALL_STATS:
        horse.stats[stat] = 1.0

    random.seed(5)
    for _ in range(20):
        apply_weekly_stat_decline(state)
    assert all(v >= 1.0 for v in horse.stats.values())


def test_apply_weekly_stat_decline_applies_to_retired_horses_too():
    """退役種馬/繁殖母馬持續老化衰退是刻意設計(見cli/game.py docstring)。"""
    state = game_state_with_test_horses()
    horse = state.horses[0]
    horse.growth_curve = "早熟"
    horse.age = 10
    horse.retired = True
    before = dict(horse.stats)

    random.seed(6)
    apply_weekly_stat_decline(state)
    assert any(horse.stats[s] < before[s] for s in ALL_STATS if s not in G.DECLINE_EXEMPT_STATS)


# ------------------------------------------------------- growth_curve wired into generation

def test_starter_horses_have_growth_curve_assigned():
    state = game_state_with_test_horses()
    for horse in state.horses:
        assert horse.growth_curve in G.GROWTH_CURVE_TYPES


def test_market_horses_have_random_growth_curve():
    random.seed(7)
    horse = generate_market_horse(set())
    assert horse.growth_curve in G.GROWTH_CURVE_TYPES


def test_foal_market_horses_have_random_growth_curve():
    random.seed(8)
    horse = generate_foal_market_horse(set())
    assert horse.growth_curve in G.GROWTH_CURVE_TYPES


def test_stallion_and_broodmare_market_horses_have_random_growth_curve():
    random.seed(9)
    stallion = generate_stallion_market_horse(set())
    mare = generate_broodmare_market_horse(set())
    assert stallion.growth_curve in G.GROWTH_CURVE_TYPES
    assert mare.growth_curve in G.GROWTH_CURVE_TYPES


def test_bred_foal_has_random_growth_curve_independent_of_parents():
    random.seed(10)
    mare = make_horse(name="母馬", growth_curve="早熟")
    sire_stats = {s: 60.0 for s in ALL_STATS}
    foal, _note = generate_foal(
        mare=mare,
        sire_stats=sire_stats,
        sire_potential_cap=85.0,
        sire_name="種馬",
        inbred=False,
        existing_names=set(),
    )
    assert foal.growth_curve in G.GROWTH_CURVE_TYPES
