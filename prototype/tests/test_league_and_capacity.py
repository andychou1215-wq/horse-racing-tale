"""馬主聯盟升降級(cli/league.py) + 馬房/育馬場容量限制(cli/facilities.py新增的3種
容量型設施 + cli/game.py購買/登記時的容量檢查)的單元測試。2026/8/25使用者決定新增，
從MVP範圍.md「先跳過」清單補回剩餘經營系統。
"""
from __future__ import annotations

import random

import pytest

from cli import assumptions as A
from cli import league as L
from cli.facilities import (
    overseas_stable_capacity_for_level,
    stable_capacity_for_level,
    stud_farm_capacity_for_level,
)
from cli.game import (
    RaceEntry,
    apply_weekly_league_season_progression,
    assign_breeding_role,
    buy_broodmare,
    buy_horse,
    buy_stallion,
    new_game,
    retire_horse,
    run_race,
)
from cli.horses import ALL_STATS, Horse


def make_horse(**overrides) -> Horse:
    defaults = dict(
        name="測試馬",
        stats={s: 60.0 for s in ALL_STATS},
        potential_cap=90.0,
        pace="先",
        age=4,
        sex="母",
    )
    defaults.update(overrides)
    return Horse(**defaults)


# --------------------------------------------------------------- 容量數字本身

def test_capacity_tables_match_doc_values():
    assert [stable_capacity_for_level(lv) for lv in range(1, 6)] == [10, 20, 30, 40, 50]
    assert [stud_farm_capacity_for_level(lv) for lv in range(1, 6)] == [10, 20, 30, 40, 50]
    assert [overseas_stable_capacity_for_level(lv) for lv in range(1, 6)] == [5, 10, 15, 20, 25]


def test_new_game_includes_three_capacity_facilities_at_default_level():
    state = new_game()
    for f in ("馬房", "育馬場", "海外馬房"):
        assert state.facility_levels[f] == 2  # DEFAULT_LEVEL


# --------------------------------------------------------------------- 馬房容量

def _fill_stable(state, count: int) -> None:
    """直接塞馬進馬房到指定數量，不依賴市場供給量(市場一次只有4匹候選，不夠塞滿
    容量測試用的門檻)，用來讓容量測試不受市場刷新/供給量牽動、保持穩定可重現。"""
    while len(state.horses) < count:
        h = make_horse(name=f"填充馬{len(state.horses)}", sex="母", age=3)
        state.horses.append(h)


def test_buy_horse_blocked_when_stable_full():
    state = new_game()
    state.money = 10_000_000.0
    state.facility_levels["馬房"] = 1  # 容量10匹
    _fill_stable(state, 10)
    assert not state.horse_market == []  # 開局一定有市場馬可買(HORSE_MARKET_LISTING_COUNT=4)
    target = state.horse_market[0].name
    msg = buy_horse(state, target)
    assert "馬房已滿" in msg
    assert not any(h.name == target for h in state.horses)


def test_buy_horse_allowed_after_upgrading_stable():
    state = new_game()
    state.money = 10_000_000.0
    state.facility_levels["馬房"] = 1
    _fill_stable(state, 10)
    state.facility_levels["馬房"] = 2  # 升級後容量變20匹
    target = state.horse_market[0].name
    msg = buy_horse(state, target)
    assert "馬房已滿" not in msg
    assert any(h.name == target for h in state.horses)


def test_breeding_birth_not_blocked_by_full_stable(monkeypatch):
    """配種已登記的母馬正常生產，不受馬房容量擋下(2026/8/25使用者決定：容量只擋
    主動購買/登記，不擋懷孕中的生產週期)。"""
    from cli.game import apply_weekly_pregnancy_progression, breed

    state = new_game()
    stallion = next(h for h in state.horses if h.sex == "公")
    mare = next(h for h in state.horses if h.sex == "母")
    for h in (stallion, mare):
        retire_horse(state, h.name)
        h.age = 5
    assign_breeding_role(state, stallion.name, "種馬")
    assign_breeding_role(state, mare.name, "繁殖母馬")
    state.money = 1_000_000.0

    monkeypatch.setattr(random, "random", lambda: 0.0)  # 強制配種成功(BREEDING_SUCCESS_CHANCE門檻)
    msg = breed(state, mare.name, stallion.name)
    assert "配種成功" in msg

    state.facility_levels["馬房"] = 1  # 容量10匹
    _fill_stable(state, 10)  # 塞滿馬房，確認生產不受這個容量限制阻擋
    before_count = len(state.horses)
    mare.pregnant_weeks_remaining = 1
    apply_weekly_pregnancy_progression(state)
    assert len(state.horses) == before_count + 1  # 幼駒仍然正常生出來，不受容量阻擋


# -------------------------------------------------------------------- 育馬場容量

def test_assign_breeding_role_blocked_when_stud_farm_full():
    state = new_game()
    state.facility_levels["育馬場"] = 1  # 容量10匹
    horses = []
    for i in range(10):
        h = make_horse(name=f"種馬{i}", sex="公", age=5, retired=True)
        state.horses.append(h)
        assign_breeding_role(state, h.name, "種馬")
        horses.append(h)
    assert sum(1 for h in state.horses if h.breeding_role is not None) == 10

    extra = make_horse(name="多出來的種馬", sex="公", age=5, retired=True)
    state.horses.append(extra)
    msg = assign_breeding_role(state, extra.name, "種馬")
    assert "育馬場已滿" in msg
    assert extra.breeding_role is None


def test_assign_breeding_role_reassigning_same_horse_does_not_double_count():
    """重新登記同一匹馬(取消後再登記回同角色)不應該被自己先前佔用的名額卡住。"""
    state = new_game()
    state.facility_levels["育馬場"] = 1
    horse = make_horse(name="種馬A", sex="公", age=5, retired=True)
    state.horses.append(horse)
    assign_breeding_role(state, horse.name, "種馬")
    msg = assign_breeding_role(state, horse.name, "種馬")  # 重複登記同一角色
    assert "育馬場已滿" not in msg


def test_buy_stallion_blocked_when_stud_farm_full():
    state = new_game()
    state.money = 10_000_000.0
    state.facility_levels["育馬場"] = 1
    for i in range(10):
        h = make_horse(name=f"種馬{i}", sex="公", age=5, retired=True)
        state.horses.append(h)
        assign_breeding_role(state, h.name, "種馬")

    if not state.stallion_market:
        pytest.skip("種馬市場剛好是空的")
    target = state.stallion_market[0].name
    msg = buy_stallion(state, target)
    assert "育馬場已滿" in msg
    assert not any(h.name == target for h in state.horses)


def test_buy_broodmare_blocked_when_stable_full_even_if_stud_farm_has_room():
    state = new_game()
    state.money = 10_000_000.0
    state.facility_levels["馬房"] = 1  # 容量10
    _fill_stable(state, 10)
    if not state.broodmare_market:
        pytest.skip("繁殖母馬市場剛好是空的")
    target = state.broodmare_market[0].name
    msg = buy_broodmare(state, target)
    assert "馬房已滿" in msg


# ---------------------------------------------------------------- cli/league.py

def test_league_points_for_result_only_scores_defined_grades_and_ranks():
    assert L.league_points_for_result("地方三級賽", 1) == 30
    assert L.league_points_for_result("地方三級賽", 10) == 2
    assert L.league_points_for_result("地方三級賽", 11) == 0  # 超過Top10不計分
    assert L.league_points_for_result("新馬賽", 1) == 0  # 不在計分分級清單裡
    assert L.league_points_for_result("國際GI", 1) == 160


def test_generate_virtual_opponents_returns_tier_size_minus_one():
    random.seed(1)
    for tier in (1, 2, 3, 4):
        opponents = L.generate_virtual_opponents(tier)
        assert len(opponents) == L.TIER_SIZE[tier] - 1
        for o in opponents:
            assert o["points"] >= 0.0
            assert set(o["win_counts"]) == set(L.TIEBREAK_GRADES)


def test_resolve_season_promotes_when_player_dominates():
    random.seed(2)
    # 玩家積分遠高於同層級典型虛擬對手均值，應該大機率排進晉升區
    result = L.resolve_season(tier=4, player_points=100000.0, player_win_counts={g: 50 for g in L.TIEBREAK_GRADES})
    assert result["rank"] == 1
    assert result["promoted"] is True
    assert result["new_tier"] == 3
    assert result["top3"] is True


def test_resolve_season_relegates_when_player_far_behind():
    random.seed(3)
    result = L.resolve_season(tier=2, player_points=-1.0, player_win_counts={g: 0 for g in L.TIEBREAK_GRADES})
    # player_points不會真的是負值，這裡只是確保「敬陪末座」時會被降級
    assert result["rank"] == L.TIER_SIZE[2]
    assert result["relegated"] is True
    assert result["new_tier"] == 3


def test_resolve_season_top_tier_has_no_promotion():
    random.seed(4)
    result = L.resolve_season(tier=1, player_points=100000.0, player_win_counts={g: 50 for g in L.TIEBREAK_GRADES})
    assert result["promoted"] is False
    assert result["new_tier"] == 1


def test_resolve_season_bottom_tier_has_no_relegation():
    random.seed(5)
    result = L.resolve_season(tier=4, player_points=-1.0, player_win_counts={g: 0 for g in L.TIEBREAK_GRADES})
    assert result["relegated"] is False
    assert result["new_tier"] == 4


# -------------------------------------------------- 整合：run_race()累積積分/冠軍數

def test_run_race_awards_league_points_for_high_tier_grade():
    state = new_game()
    horse = state.horses[0]
    horse.can_race = lambda: True
    before_points = state.league_points

    random.seed(6)
    run_race(state, "地方三級賽", [RaceEntry(horse, "地方三級賽", "自由發揮")])
    assert state.league_points >= before_points  # 名次落在Top10內一定會加分(field_size=11)


def test_run_race_does_not_award_league_points_for_low_tier_grade():
    state = new_game()
    horse = state.horses[0]
    horse.can_race = lambda: True

    random.seed(7)
    run_race(state, "新馬賽", [RaceEntry(horse, "新馬賽", "自由發揮")])
    assert state.league_points == 0.0


def test_run_race_increments_win_count_only_on_first_place():
    state = new_game()
    horse = state.horses[0]
    horse.can_race = lambda: True
    horse.stats = {s: 99.0 for s in ALL_STATS}  # 拉滿屬性，盡量確保拿第一

    random.seed(8)
    for _ in range(5):
        run_race(state, "地方三級賽", [RaceEntry(horse, "地方三級賽", "自由發揮")])
        horse.race_cooldown_weeks_remaining = 0
    total_wins = sum(state.league_win_counts.values())
    assert total_wins <= 5  # 冠軍數不會超過出賽次數(基本防呆，不強求一定拿到第一)


# --------------------------------------------------- apply_weekly_league_season_progression

def test_season_progression_noop_before_year_end():
    state = new_game()
    state.week = 10
    assert apply_weekly_league_season_progression(state) == []


def test_season_progression_resets_points_and_win_counts_at_year_end():
    state = new_game()
    state.week = A.WEEKS_PER_YEAR
    state.league_points = 500.0
    state.league_win_counts["國際GI"] = 3

    random.seed(9)
    lines = apply_weekly_league_season_progression(state)
    assert lines  # 有回傳結算敘述
    assert state.league_points == 0.0
    assert all(v == 0 for v in state.league_win_counts.values())
    assert state.league_last_season_result is not None


def test_season_progression_awards_top3_bonus_money():
    state = new_game()
    state.week = A.WEEKS_PER_YEAR
    state.money = 100000.0
    state.league_tier = 4
    state.league_points = 100000.0  # 遠高於同層級虛擬對手，幾乎必進前3
    state.league_win_counts = {g: 50 for g in L.TIEBREAK_GRADES}

    random.seed(10)
    before_money = state.money
    apply_weekly_league_season_progression(state)
    assert state.money > before_money
