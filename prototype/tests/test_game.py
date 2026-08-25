"""CLI 原型的簿記邏輯測試（疲勞、賽事資格門檻、財務結算）。

`engine/` 已有 23 個對照 xlsx 的公式測試；這裡補的是 `cli/` 層本身的
簿記規則（跟 xlsx 無關，純粹是這個原型自己的假設值行為）。
"""
from __future__ import annotations

import pytest

from cli import assumptions as A
from cli.game import (
    MARKET_REFRESH_INTERVAL_WEEKS,
    GameState,
    Jockey,
    RaceEntry,
    apply_race_experience_growth,
    apply_weekly_age_progression,
    apply_weekly_injury_recovery,
    apply_weekly_passive_recovery,
    assign_trainer,
    assign_vet,
    buy_horse,
    eligible_grades,
    fire_trainer,
    fire_vet,
    hire_trainer,
    hire_vet,
    refresh_markets_if_due,
    rest_horse,
    roll_weekly_injuries,
    run_race,
    sell_horse,
    train_horse,
    upgrade_facility,
    weekly_upkeep,
)
from cli.horse_market import generate_horse_market, market_value as horse_market_value
from cli.facilities import DEFAULT_LEVEL, MAX_LEVEL, upgrade_cost
from cli.horses import TRAINABLE_STATS, Horse, starter_horses
from cli.injuries import Injury
from cli.trainers import Trainer
from cli.vets import Vet


def make_horse(**overrides) -> Horse:
    stats = {
        "速度": 60, "耐力": 60, "加速": 60, "力量": 60, "根性": 60,
        "智力": 60, "起跑": 60, "彎道": 60, "戰術": 60, "精神": 60, "健康": 70,
    }
    defaults = dict(name="測試馬", stats=stats, potential_cap=90, pace="先")
    defaults.update(overrides)
    return Horse(**defaults)


def test_no_starter_horse_qualifies_for_gi_at_game_start():
    """調整後：開局5匹測試馬都還不夠格報名國際GI，需要先透過訓練提升評級。"""
    for h in starter_horses():
        assert "國際GI" not in eligible_grades(h), f"{h.name} 評級 {h.overall_rating():.1f} 不應一開局就能報國際GI"


def test_gi_threshold_is_reachable_by_at_least_one_starter_horse_eventually():
    """GI門檻不該高到連潛力上限最高的馬終其一生都摸不到（第二輪調整前的問題）。

    用「11項屬性全部練到潛力上限」這個絕對上限(比實際遊玩寬鬆，因為智力/彎道/
    精神/健康在MVP不可訓練、永遠停在起始值)去檢查，確保至少不是連理論極限都不夠。
    """
    for h in starter_horses():
        theoretical_ceiling = h.potential_cap
        if theoretical_ceiling >= A.GRADE_ELIGIBILITY_THRESHOLD["國際GI"]:
            return  # 至少有一匹馬在潛力上限意義下摸得到GI門檻
    pytest.fail("沒有任何開局測試馬的潛力上限能達到GI門檻，門檻可能設得過高")


def test_all_eleven_race_grades_have_a_reachable_eligibility_threshold():
    """11個賽事分級都要至少有一匹開局測試馬「潛力上限意義下」摸得到，不該有任何一級
    是連理論極限都進不去的死級距(擴充成11級後新增的把關測試)。"""
    ceilings = [h.potential_cap for h in starter_horses()]
    for grade in A.RACE_GRADES:
        threshold = A.GRADE_ELIGIBILITY_THRESHOLD[grade]
        assert any(c >= threshold for c in ceilings), f"沒有任何測試馬的潛力上限能達到{grade}門檻({threshold})"


def test_race_grade_related_tables_are_monotonically_non_decreasing_by_tier():
    """賽事分級由低到高排列(RACE_GRADES順序)，門檻/報名費/對手強度/名氣/比賽經驗成長
    基礎值都該隨分級提升單調不遞減，避免「等級比較高、但門檻或報名費反而比較低」這種
    設計矛盾(GRADE_FIELD_SIZE個別級距刻意持平，不強制要求嚴格遞增)。"""
    grades_in_order = list(A.RACE_GRADES)
    for table in (
        A.GRADE_ELIGIBILITY_THRESHOLD,
        A.GRADE_ENTRY_FEE,
        A.GRADE_OPPONENT_LEVEL,
        A.FAME_GAIN_BY_GRADE,
        A.RACE_GROWTH_BASE_BY_GRADE,
    ):
        values = [table[g] for g in grades_in_order]
        assert values == sorted(values), f"{table} 沒有隨分級單調不遞減：{values}"


def test_every_race_grade_has_complete_config():
    """11個分級在所有對照表裡都要有資料，避免漏掉哪一級忘記補設定值。"""
    for grade in A.RACE_GRADES:
        assert grade in A.GRADE_ELIGIBILITY_THRESHOLD
        assert grade in A.GRADE_FIELD_SIZE
        assert grade in A.GRADE_OPPONENT_LEVEL
        assert grade in A.GRADE_ENTRY_FEE
        assert grade in A.GRADE_PRIZE_TABLE
        assert grade in A.FAME_GAIN_BY_GRADE
        assert grade in A.RACE_GROWTH_BASE_BY_GRADE
        assert len(A.GRADE_PRIZE_TABLE[grade]) <= A.GRADE_FIELD_SIZE[grade], (
            f"{grade} 的獎金名次數({len(A.GRADE_PRIZE_TABLE[grade])})不該超過參賽數上限"
            f"({A.GRADE_FIELD_SIZE[grade]})"
        )


def test_race_experience_growth_increases_trainable_stats():
    state = GameState(horses=[], jockeys={})
    horse = make_horse(fatigue=0.0)
    before = {s: horse.stats[s] for s in TRAINABLE_STATS}
    total_growth = apply_race_experience_growth(state, horse, "地方一般賽")
    assert total_growth > 0
    assert all(horse.stats[s] >= before[s] for s in TRAINABLE_STATS)


def test_higher_grade_race_grants_more_experience_growth():
    """分級越高，比賽經驗成長基礎值越高（同一匹馬、同樣狀態下比較）。"""
    state = GameState(horses=[], jockeys={})
    growths = {}
    for grade in ("新馬賽", "地方一般賽", "國際GI"):
        horse = make_horse(fatigue=0.0)
        growths[grade] = apply_race_experience_growth(state, horse, grade)
    assert growths["新馬賽"] < growths["地方一般賽"] < growths["國際GI"]


def test_all_starter_horses_can_enter_新馬賽():
    for h in starter_horses():
        assert "新馬賽" in eligible_grades(h)


def test_rest_reduces_fatigue_more_than_training_increases_it():
    """休息一次的疲勞回復量，應該大於訓練一次的疲勞增加量，休息才有意義。"""
    assert A.REST_FATIGUE_LOSS > A.TRAIN_FATIGUE_GAIN


def test_passive_recovery_prevents_fatigue_from_getting_permanently_stuck_at_100():
    horse = make_horse(fatigue=100.0)
    from cli.game import GameState

    state = GameState(horses=[horse], jockeys={})
    apply_weekly_passive_recovery(state)
    assert horse.fatigue < 100.0
    assert horse.fatigue == pytest.approx(100.0 - A.WEEKLY_PASSIVE_FATIGUE_RECOVERY)


def test_fatigue_never_goes_negative():
    horse = make_horse(fatigue=2.0)
    from cli.game import GameState

    state = GameState(horses=[horse], jockeys={})
    apply_weekly_passive_recovery(state)
    assert horse.fatigue >= 0.0


def test_train_horse_increases_fatigue_and_stat():
    horse = make_horse(fatigue=0.0)
    state = GameState(horses=[horse], jockeys={})
    before_stat = horse.stats["速度"]
    train_horse(state, horse, "速度")
    assert horse.stats["速度"] > before_stat
    assert horse.fatigue == pytest.approx(A.TRAIN_FATIGUE_GAIN)


def test_rest_horse_does_not_change_stats():
    horse = make_horse(fatigue=50.0)
    stats_before = dict(horse.stats)
    rest_horse(horse)
    assert horse.stats == stats_before
    assert horse.fatigue < 50.0


def test_bankruptcy_triggers_when_money_drops_below_threshold():
    from cli.game import GameState

    horse = make_horse()
    state = GameState(horses=[horse], jockeys={}, money=A.BANKRUPTCY_THRESHOLD + 1)
    weekly_upkeep(state, training_sessions=0)
    assert state.bankrupt is True


# ---------------------------------------------------------- 訓練師系統（新增）

def make_trainer(**overrides) -> Trainer:
    defaults = dict(name="測試教練", specialty="速度訓練", skill_level=3, hire_fee=2400.0, weekly_salary=600.0)
    defaults.update(overrides)
    return Trainer(**defaults)


def test_no_trainer_means_baseline_training_multiplier():
    """沒有指定訓練師時，訓練倍率維持1.0（向下相容補回此系統前的假設值）。"""
    horse = make_horse(fatigue=0.0)
    state = GameState(horses=[horse], jockeys={})
    from cli.game import trainer_effective_multiplier

    assert trainer_effective_multiplier(state, horse, "速度") == 1.0


def test_matching_specialty_trainer_increases_training_growth():
    """指定「速度訓練」專長的訓練師，練速度時成長量應該比沒有訓練師時更多。"""
    horse_with = make_horse(fatigue=0.0, assigned_trainer="測試教練")
    horse_without = make_horse(fatigue=0.0)
    trainer = make_trainer(specialty="速度訓練")
    state = GameState(horses=[horse_with, horse_without], jockeys={}, trainers=[trainer])

    before_with = horse_with.stats["速度"]
    before_without = horse_without.stats["速度"]
    train_horse(state, horse_with, "速度")
    train_horse(state, horse_without, "速度")

    assert (horse_with.stats["速度"] - before_with) > (horse_without.stats["速度"] - before_without)


def test_specialty_only_boosts_matching_stat():
    """「速度訓練」專長不應該讓練「耐力」也加成。"""
    horse_with = make_horse(fatigue=0.0, assigned_trainer="測試教練")
    horse_without = make_horse(fatigue=0.0)
    trainer = make_trainer(specialty="速度訓練")
    state = GameState(horses=[horse_with, horse_without], jockeys={}, trainers=[trainer])

    before_with = horse_with.stats["耐力"]
    before_without = horse_without.stats["耐力"]
    train_horse(state, horse_with, "耐力")
    train_horse(state, horse_without, "耐力")

    assert (horse_with.stats["耐力"] - before_with) == pytest.approx(
        horse_without.stats["耐力"] - before_without
    )


def test_hire_trainer_deducts_hire_fee_and_adds_to_state():
    horse = make_horse()
    state = GameState(horses=[horse], jockeys={}, money=10000.0)
    trainer = make_trainer(hire_fee=2400.0)
    msg = hire_trainer(state, trainer)
    assert state.money == pytest.approx(10000.0 - 2400.0)
    assert trainer in state.trainers
    assert trainer.name in msg


def test_hire_trainer_fails_when_money_insufficient():
    horse = make_horse()
    state = GameState(horses=[horse], jockeys={}, money=100.0)
    trainer = make_trainer(hire_fee=2400.0)
    hire_trainer(state, trainer)
    assert trainer not in state.trainers
    assert state.money == pytest.approx(100.0)


def test_assign_trainer_requires_hired_trainer():
    horse = make_horse()
    state = GameState(horses=[horse], jockeys={})
    msg = assign_trainer(state, horse, "沒聘過的教練")
    assert horse.assigned_trainer is None
    assert "尚未聘用" in msg


def test_assign_trainer_capacity_limit_blocks_13th_horse():
    """一個訓練師最多管理12匹馬（訓練師系統.md），第13匹應該被拒絕。"""
    trainer = make_trainer()
    horses = [make_horse(name=f"馬{i}") for i in range(13)]
    state = GameState(horses=horses, jockeys={}, trainers=[trainer])
    for h in horses[:12]:
        assign_trainer(state, h, trainer.name)
    msg = assign_trainer(state, horses[12], trainer.name)
    assert horses[12].assigned_trainer is None
    assert "上限" in msg


def test_weekly_upkeep_includes_trainer_salaries():
    horse = make_horse()
    trainer = make_trainer(weekly_salary=600.0)
    state = GameState(horses=[horse], jockeys={}, money=100000.0, trainers=[trainer])
    money_before = state.money
    weekly_upkeep(state, training_sessions=0)
    expected_cost = A.STABLE_WEEKLY_COST + 600.0
    assert state.money == pytest.approx(money_before - expected_cost)


def test_fire_trainer_removes_from_state_and_stops_future_salary():
    horse = make_horse(assigned_trainer="測試教練")
    trainer = make_trainer(weekly_salary=600.0)
    state = GameState(horses=[horse], jockeys={}, money=100000.0, trainers=[trainer])

    msg = fire_trainer(state, trainer.name)
    assert trainer not in state.trainers
    assert horse.assigned_trainer is None
    assert horse.name in msg

    money_before = state.money
    weekly_upkeep(state, training_sessions=0)
    assert state.money == pytest.approx(money_before - A.STABLE_WEEKLY_COST)  # 不再含訓練師薪水


def test_fire_trainer_unknown_name_returns_message_without_crash():
    state = GameState(horses=[make_horse()], jockeys={})
    msg = fire_trainer(state, "沒聘過的教練")
    assert "尚未聘用" in msg


def test_status_management_trainer_gives_extra_fatigue_recovery():
    trainer = make_trainer(specialty="狀態管理", skill_level=3)
    horse_with = make_horse(fatigue=50.0, assigned_trainer=trainer.name)
    horse_without = make_horse(fatigue=50.0)
    state = GameState(horses=[horse_with, horse_without], jockeys={}, trainers=[trainer])
    apply_weekly_passive_recovery(state)
    assert horse_with.fatigue < horse_without.fatigue


# ---------------------------------------------------------- 獸醫/傷病系統（新增）

def make_vet(**overrides) -> Vet:
    defaults = dict(name="測試獸醫", skill_level=3, hire_fee=3000.0, weekly_salary=750.0)
    defaults.update(overrides)
    return Vet(**defaults)


def make_injury(**overrides) -> Injury:
    defaults = dict(name="測試傷病", severity="中傷", weeks_remaining=4, affected_stats=("速度",))
    defaults.update(overrides)
    return Injury(**defaults)


def test_hire_vet_deducts_hire_fee_and_adds_to_state():
    horse = make_horse()
    state = GameState(horses=[horse], jockeys={}, money=10000.0)
    vet = make_vet(hire_fee=3000.0)
    msg = hire_vet(state, vet)
    assert state.money == pytest.approx(10000.0 - 3000.0)
    assert vet in state.vets
    assert vet.name in msg


def test_hire_vet_fails_when_money_insufficient():
    horse = make_horse()
    state = GameState(horses=[horse], jockeys={}, money=100.0)
    vet = make_vet(hire_fee=3000.0)
    hire_vet(state, vet)
    assert vet not in state.vets
    assert state.money == pytest.approx(100.0)


def test_assign_vet_requires_hired_vet():
    horse = make_horse()
    state = GameState(horses=[horse], jockeys={})
    msg = assign_vet(state, horse, "沒聘過的獸醫")
    assert horse.assigned_vet is None
    assert "尚未聘用" in msg


def test_assign_vet_capacity_limit_blocks_9th_horse():
    """一個獸醫最多照顧8匹馬（員工系統.md），第9匹應該被拒絕。"""
    vet = make_vet()
    horses = [make_horse(name=f"馬{i}") for i in range(9)]
    state = GameState(horses=horses, jockeys={}, vets=[vet])
    for h in horses[:8]:
        assign_vet(state, h, vet.name)
    msg = assign_vet(state, horses[8], vet.name)
    assert horses[8].assigned_vet is None
    assert "上限" in msg


def test_weekly_upkeep_includes_vet_salaries():
    horse = make_horse()
    vet = make_vet(weekly_salary=750.0)
    state = GameState(horses=[horse], jockeys={}, money=100000.0, vets=[vet])
    money_before = state.money
    weekly_upkeep(state, training_sessions=0)
    expected_cost = A.STABLE_WEEKLY_COST + 750.0
    assert state.money == pytest.approx(money_before - expected_cost)


def test_fire_vet_removes_from_state_and_stops_future_salary():
    horse = make_horse(assigned_vet="測試獸醫")
    vet = make_vet(weekly_salary=750.0)
    state = GameState(horses=[horse], jockeys={}, money=100000.0, vets=[vet])

    msg = fire_vet(state, vet.name)
    assert vet not in state.vets
    assert horse.assigned_vet is None
    assert horse.name in msg

    money_before = state.money
    weekly_upkeep(state, training_sessions=0)
    assert state.money == pytest.approx(money_before - A.STABLE_WEEKLY_COST)  # 不再含獸醫薪水


def test_fire_vet_unknown_name_returns_message_without_crash():
    state = GameState(horses=[make_horse()], jockeys={})
    msg = fire_vet(state, "沒聘過的獸醫")
    assert "尚未聘用" in msg


def test_train_horse_blocked_while_injured():
    horse = make_horse(injury=make_injury())
    state = GameState(horses=[horse], jockeys={})
    with pytest.raises(ValueError):
        train_horse(state, horse, "速度")


def test_train_horse_blocked_while_retired():
    horse = make_horse(retired=True)
    state = GameState(horses=[horse], jockeys={})
    with pytest.raises(ValueError):
        train_horse(state, horse, "速度")


def test_apply_weekly_injury_recovery_counts_down_and_clears():
    horse = make_horse(injury=make_injury(weeks_remaining=1))
    state = GameState(horses=[horse], jockeys={})
    lines = apply_weekly_injury_recovery(state)
    assert horse.injury is None
    assert any("痊癒" in line for line in lines)


def test_apply_weekly_injury_recovery_counts_down_without_clearing_early():
    horse = make_horse(injury=make_injury(weeks_remaining=5))
    state = GameState(horses=[horse], jockeys={})
    apply_weekly_injury_recovery(state)
    assert horse.injury is not None
    assert horse.injury.weeks_remaining == 4


def test_vet_speeds_up_recovery():
    vet = make_vet(skill_level=5)
    horse_with = make_horse(injury=make_injury(weeks_remaining=10), assigned_vet=vet.name)
    horse_without = make_horse(injury=make_injury(weeks_remaining=10))
    state = GameState(horses=[horse_with, horse_without], jockeys={}, vets=[vet])
    apply_weekly_injury_recovery(state)
    assert horse_with.injury.weeks_remaining < horse_without.injury.weeks_remaining


def test_roll_weekly_injuries_skips_already_injured_and_retired_horses(monkeypatch):
    import random

    monkeypatch.setattr(random, "random", lambda: 0.0)  # 強制觸發機率
    injured = make_horse(name="傷病馬", injury=make_injury())
    retired = make_horse(name="退役馬", retired=True)
    state = GameState(horses=[injured, retired], jockeys={})
    state.week = 5
    lines = roll_weekly_injuries(state)
    assert lines == []  # 已受傷/已退役的馬不應該再被判定


def test_roll_weekly_injuries_can_injure_healthy_horse(monkeypatch):
    import random

    monkeypatch.setattr(random, "random", lambda: 0.0)  # 強制觸發機率
    horse = make_horse(fatigue=90.0)
    horse.stats["健康"] = 10.0  # 高傷病風險，配合機率強制觸發
    horse.raced_this_week = True  # 2026/8/23：現在改吃逐馬旗標而不是全域is_racing_this_week
    state = GameState(horses=[horse], jockeys={})
    state.week = 5
    lines = roll_weekly_injuries(state)
    assert len(lines) == 1
    assert horse.injury is not None or horse.retired


def test_run_race_filters_out_injured_horses():
    healthy = make_horse(name="健康馬")
    injured = make_horse(name="受傷馬", injury=make_injury())
    state = GameState(horses=[healthy, injured], jockeys={
        "健康馬": None, "受傷馬": None,
    })
    # run_race 需要 state.jockeys 提供每匹出賽馬的騎師資料，這裡補上必要的最小假資料
    from cli.game import Jockey

    state.jockeys = {
        "健康馬": Jockey(correction=1.0, position_judgement=60, rhythm_control=60, route_choice=60),
        "受傷馬": Jockey(correction=1.0, position_judgement=60, rhythm_control=60, route_choice=60),
    }
    entries = [RaceEntry(healthy, "新馬賽", "自由發揮"), RaceEntry(injured, "新馬賽", "自由發揮")]
    lines = run_race(state, "新馬賽", entries)
    assert not any("受傷馬" in line and "第" in line and "名｜" in line for line in lines)


# ---------------------------------------------------------- 設施升級系統（新增）

def test_default_facility_levels_reproduce_old_fixed_training_multiplier():
    """向下相容：沒有升級任何設施時，訓練成長量要跟補回這個系統前完全一樣。"""
    from cli.game import facility_effective_multiplier

    horse = make_horse(fatigue=0.0)
    state = GameState(horses=[horse], jockeys={})
    assert facility_effective_multiplier(state, "速度") == pytest.approx(1.1)


def test_upgrading_facility_increases_training_growth_for_its_stats():
    horse_before = make_horse(fatigue=0.0)
    state_before = GameState(horses=[horse_before], jockeys={}, money=100000.0)
    before_stat = horse_before.stats["速度"]
    train_horse(state_before, horse_before, "速度")
    growth_before = horse_before.stats["速度"] - before_stat

    horse_after = make_horse(fatigue=0.0)
    state_after = GameState(horses=[horse_after], jockeys={}, money=100000.0)
    upgrade_facility(state_after, "速度訓練場")
    before_stat2 = horse_after.stats["速度"]
    train_horse(state_after, horse_after, "速度")
    growth_after = horse_after.stats["速度"] - before_stat2

    assert growth_after > growth_before


def test_upgrading_facility_does_not_affect_unrelated_stats():
    """升級「速度訓練場」不該讓練「耐力」也加成（跟訓練師專長一樣是互不影響的設計）。"""
    horse = make_horse(fatigue=0.0)
    state = GameState(horses=[horse], jockeys={}, money=100000.0)
    upgrade_facility(state, "速度訓練場")

    horse_baseline = make_horse(fatigue=0.0)
    state_baseline = GameState(horses=[horse_baseline], jockeys={}, money=100000.0)

    before = horse.stats["耐力"]
    before_baseline = horse_baseline.stats["耐力"]
    train_horse(state, horse, "耐力")
    train_horse(state_baseline, horse_baseline, "耐力")

    assert (horse.stats["耐力"] - before) == pytest.approx(
        horse_baseline.stats["耐力"] - before_baseline
    )


def test_upgrade_facility_deducts_cost_and_increments_level():
    state = GameState(horses=[], jockeys={}, money=100000.0)
    cost = upgrade_cost(DEFAULT_LEVEL)
    money_before = state.money
    msg = upgrade_facility(state, "速度訓練場")
    assert state.facility_levels["速度訓練場"] == DEFAULT_LEVEL + 1
    assert state.money == pytest.approx(money_before - cost)
    assert "速度訓練場" in msg


def test_upgrade_facility_fails_when_money_insufficient():
    state = GameState(horses=[], jockeys={}, money=100.0)
    msg = upgrade_facility(state, "速度訓練場")
    assert state.facility_levels["速度訓練場"] == DEFAULT_LEVEL
    assert state.money == pytest.approx(100.0)
    assert "資金不足" in msg


def test_upgrade_facility_blocks_beyond_max_level():
    state = GameState(horses=[], jockeys={}, money=10_000_000.0)
    for _ in range(MAX_LEVEL - DEFAULT_LEVEL):
        upgrade_facility(state, "速度訓練場")
    assert state.facility_levels["速度訓練場"] == MAX_LEVEL
    msg = upgrade_facility(state, "速度訓練場")
    assert state.facility_levels["速度訓練場"] == MAX_LEVEL
    assert "最高等級" in msg


def test_upgrade_facility_unknown_name_returns_message_without_crash():
    state = GameState(horses=[], jockeys={}, money=100000.0)
    msg = upgrade_facility(state, "不存在的設施")
    assert "沒有這個設施" in msg


def test_recovery_center_upgrade_boosts_weekly_passive_fatigue_recovery():
    horse_with = make_horse(fatigue=100.0)
    state_with = GameState(horses=[horse_with], jockeys={}, money=100000.0)
    upgrade_facility(state_with, "恢復中心")
    apply_weekly_passive_recovery(state_with)

    horse_without = make_horse(fatigue=100.0)
    state_without = GameState(horses=[horse_without], jockeys={})
    apply_weekly_passive_recovery(state_without)

    assert horse_with.fatigue < horse_without.fatigue


def test_medical_center_upgrade_speeds_up_injury_recovery():
    horse_with = make_horse(injury=make_injury(weeks_remaining=10))
    state_with = GameState(horses=[horse_with], jockeys={}, money=100000.0)
    upgrade_facility(state_with, "醫療中心")
    apply_weekly_injury_recovery(state_with)

    horse_without = make_horse(injury=make_injury(weeks_remaining=10))
    state_without = GameState(horses=[horse_without], jockeys={})
    apply_weekly_injury_recovery(state_without)

    assert horse_with.injury.weeks_remaining < horse_without.injury.weeks_remaining


# ---------------------------------------------------------- 訓練師/獸醫市場刷新（新增）

def test_new_game_starts_with_a_trainer_and_vet_market():
    state = GameState(horses=[], jockeys={})
    assert len(state.trainer_market) == 4
    assert len(state.vet_market) == 3
    assert state.last_market_refresh_week == 1


def test_market_does_not_refresh_before_interval_elapses():
    state = GameState(horses=[], jockeys={})
    original_trainer_names = [t.name for t in state.trainer_market]
    state.week = MARKET_REFRESH_INTERVAL_WEEKS  # 還沒滿4週(從第1週算)，不該刷新
    msg = refresh_markets_if_due(state)
    assert msg is None
    assert [t.name for t in state.trainer_market] == original_trainer_names
    assert state.last_market_refresh_week == 1


def test_market_refreshes_once_interval_elapses():
    state = GameState(horses=[], jockeys={})
    state.week = 1 + MARKET_REFRESH_INTERVAL_WEEKS
    msg = refresh_markets_if_due(state)
    assert msg is not None
    assert str(state.week) in msg
    assert state.last_market_refresh_week == state.week


def test_market_refresh_does_not_affect_already_hired_trainers_or_vets():
    trainer = make_trainer()
    vet = make_vet()
    state = GameState(horses=[], jockeys={}, money=100000.0, trainers=[trainer], vets=[vet])
    state.week = 1 + MARKET_REFRESH_INTERVAL_WEEKS
    refresh_markets_if_due(state)
    assert trainer in state.trainers
    assert vet in state.vets


def test_market_refresh_is_idempotent_within_the_same_week():
    state = GameState(horses=[], jockeys={})
    state.week = 1 + MARKET_REFRESH_INTERVAL_WEEKS
    refresh_markets_if_due(state)
    market_after_first_refresh = list(state.trainer_market)
    msg = refresh_markets_if_due(state)  # 同一週再呼叫一次，不該重複刷新
    assert msg is None
    assert state.trainer_market == market_after_first_refresh


# ---------------------------------------------------------- 馬匹年齡系統 + 新馬賽/未勝利賽生涯資格制（新增）

def make_jockey(**overrides) -> Jockey:
    defaults = dict(correction=1.0, position_judgement=60, rhythm_control=60, route_choice=60)
    defaults.update(overrides)
    return Jockey(**defaults)


def test_starter_horses_start_at_maiden_age_with_clean_career():
    """開局5匹測試馬都要是MAIDEN_RACE_AGE(2)歲、生涯全新(還沒出賽、還沒畢業)，
    才能一開局就報名新馬賽(對應 test_all_starter_horses_can_enter_新馬賽)。"""
    for h in starter_horses():
        assert h.age == A.STARTER_HORSE_AGE == A.MAIDEN_RACE_AGE
        assert h.career_starts == 0
        assert h.graduated is False


def test_horse_that_has_already_raced_cannot_enter_新馬賽():
    """只要出賽過一次(不論名次、不論分級)，就永久不能再報名新馬賽。"""
    horse = make_horse(career_starts=1)
    assert "新馬賽" not in eligible_grades(horse)


def test_horse_past_maiden_age_with_no_starts_cannot_enter_新馬賽():
    """新馬賽限MAIDEN_RACE_AGE(2)歲，年齡不符時即使從未出賽過也不能報名。"""
    horse = make_horse(age=A.MAIDEN_RACE_AGE + 1, career_starts=0)
    assert "新馬賽" not in eligible_grades(horse)


def test_horse_that_lost_maiden_race_can_enter_未勝利賽_but_not_新馬賽_or_一般賽事():
    """新馬賽沒贏(career_starts>=1、還沒畢業)的馬：能報未勝利賽，不能報新馬賽或一般賽事。"""
    horse = make_horse(career_starts=1, graduated=False)  # rating 60，高於未勝利賽門檻40
    grades = eligible_grades(horse)
    assert "新馬賽" not in grades
    assert "未勝利賽" in grades
    assert "地方一般賽" not in grades


def test_graduated_horse_can_enter_一般賽事_but_not_新馬賽_or_未勝利賽():
    """畢業(贏過新馬賽或未勝利賽)的馬：能報一般賽事以上，不能再回頭報新馬賽/未勝利賽。"""
    horse = make_horse(career_starts=1, graduated=True)  # rating 60，高於地方一般賽門檻58
    grades = eligible_grades(horse)
    assert "新馬賽" not in grades
    assert "未勝利賽" not in grades
    assert "地方一般賽" in grades


def test_horse_that_missed_maiden_age_cannot_debut_in_未勝利賽():
    """超齡未出賽馬不開放從未勝利賽出道；年齡結算會把牠自動退役。"""
    horse = make_horse(age=A.MAIDEN_RACE_AGE + 1, career_starts=0, graduated=False)
    assert eligible_grades(horse) == []


def test_maiden_age_first_time_horse_does_not_see_未勝利賽():
    """仍在新馬賽年齡的初次出賽馬維持原規則，只能先跑新馬賽。"""
    horse = make_horse(age=A.MAIDEN_RACE_AGE, career_starts=0, graduated=False)
    grades = eligible_grades(horse)
    assert "新馬賽" in grades
    assert "未勝利賽" not in grades


def test_run_race_increments_career_starts_regardless_of_grade_or_rank():
    weak = make_horse(name="生涯新兵", stats={s: 20.0 for s in TRAINABLE_STATS} | {"精神": 20, "健康": 20})
    state = GameState(horses=[weak], jockeys={"生涯新兵": make_jockey()}, money=100000.0)
    assert weak.career_starts == 0
    run_race(state, "新馬賽", [RaceEntry(weak, "新馬賽", "自由發揮")])
    assert weak.career_starts == 1


def test_winning_maiden_race_sets_graduated_and_opens_up_一般賽事():
    """用壓倒性屬性(全100)對上新馬賽NPC(中樞45)確保奪冠，驗證奪冠即畢業的規則。"""
    ace = make_horse(
        name="奪冠新星",
        stats={s: 100.0 for s in TRAINABLE_STATS} | {"精神": 100, "健康": 100},
        potential_cap=100,
    )
    state = GameState(horses=[ace], jockeys={"奪冠新星": make_jockey()}, money=100000.0)
    lines = run_race(state, "新馬賽", [RaceEntry(ace, "新馬賽", "自由發揮")])
    assert any("奪冠新星：第1名" in line for line in lines), f"預期壓倒性屬性應該奪冠，結果：{lines}"
    assert ace.graduated is True
    assert ace.career_starts == 1
    grades = eligible_grades(ace)
    assert "新馬賽" not in grades
    assert "未勝利賽" not in grades
    assert "地方一般賽" in grades


def test_winning_未勝利賽_also_sets_graduated():
    ace = make_horse(
        name="補考狀元",
        stats={s: 100.0 for s in TRAINABLE_STATS} | {"精神": 100, "健康": 100},
        potential_cap=100,
        career_starts=1,  # 已經跑過一次新馬賽、沒贏
        graduated=False,
    )
    state = GameState(horses=[ace], jockeys={"補考狀元": make_jockey()}, money=100000.0)
    lines = run_race(state, "未勝利賽", [RaceEntry(ace, "未勝利賽", "自由發揮")])
    assert any("補考狀元：第1名" in line for line in lines), f"預期壓倒性屬性應該奪冠，結果：{lines}"
    assert ace.graduated is True


def test_losing_maiden_race_increments_starts_but_does_not_graduate():
    weak = make_horse(name="陪跑馬", stats={s: 5.0 for s in TRAINABLE_STATS} | {"精神": 5, "健康": 5})
    state = GameState(horses=[weak], jockeys={"陪跑馬": make_jockey()}, money=100000.0)
    lines = run_race(state, "新馬賽", [RaceEntry(weak, "新馬賽", "自由發揮")])
    assert not any("陪跑馬：第1名" in line for line in lines), f"預期壓倒性劣勢不該奪冠，結果：{lines}"
    assert weak.career_starts == 1
    assert weak.graduated is False
    assert "新馬賽" not in eligible_grades(weak)


def test_age_progression_only_triggers_at_year_boundary():
    horse = make_horse()
    original_age = horse.age
    state = GameState(horses=[horse], jockeys={})

    state.week = A.WEEKS_PER_YEAR - 1
    lines = apply_weekly_age_progression(state)
    assert lines == []
    assert horse.age == original_age

    state.week = A.WEEKS_PER_YEAR
    lines = apply_weekly_age_progression(state)
    assert horse.age == original_age + 1
    assert any(horse.name in line for line in lines)


def test_age_progression_skips_retired_horses():
    horse = make_horse(retired=True)
    original_age = horse.age
    state = GameState(horses=[horse], jockeys={})
    state.week = A.WEEKS_PER_YEAR
    apply_weekly_age_progression(state)
    assert horse.age == original_age


def test_age_progression_auto_retires_horse_that_missed_maiden_debut():
    horse = make_horse(
        age=A.MAIDEN_RACE_AGE,
        career_starts=0,
        graduated=False,
        assigned_trainer="測試訓練師",
        assigned_vet="測試獸醫",
    )
    state = GameState(horses=[horse], jockeys={})
    state.week = A.WEEKS_PER_YEAR

    lines = apply_weekly_age_progression(state)

    assert horse.age == A.MAIDEN_RACE_AGE + 1
    assert horse.retired is True
    assert horse.breeding_role is None
    assert horse.assigned_trainer is None
    assert horse.assigned_vet is None
    assert any("自動退役" in line and "選擇退役路線" in line for line in lines)


def test_age_progression_does_not_auto_retire_horse_with_career_start():
    horse = make_horse(age=A.MAIDEN_RACE_AGE, career_starts=1, graduated=False)
    state = GameState(horses=[horse], jockeys={})
    state.week = A.WEEKS_PER_YEAR

    apply_weekly_age_progression(state)

    assert horse.age == A.MAIDEN_RACE_AGE + 1
    assert horse.retired is False


# ---------------------------------------------------------- 現役馬市場（新增）

def test_new_game_populates_horse_market_without_name_collision():
    state = GameState(horses=starter_horses(), jockeys={})
    state.horse_market = generate_horse_market(4, {h.name for h in state.horses})
    assert len(state.horse_market) == 4
    market_names = {h.name for h in state.horse_market}
    starter_names = {h.name for h in state.horses}
    assert len(market_names) == 4, "市場馬彼此不該同名"
    assert market_names.isdisjoint(starter_names), "市場馬不該跟開局測試馬同名"


def test_market_horse_potential_cap_is_at_least_its_highest_stat():
    """向下相容既有規則：潛力上限必須 >= 目前最高屬性，否則訓練會被往下拉齊(horses.py)。"""
    state = GameState(horses=starter_horses(), jockeys={})
    market = generate_horse_market(20, {h.name for h in state.horses})  # 生成夠多次降低漏檢機率
    for h in market:
        assert h.potential_cap >= max(h.stats.values())


def test_market_horse_over_maiden_age_is_sold_with_graduated_career():
    """市場定位維持不變：2歲可為未出賽新馬，3歲以上現役馬一律已有戰績且已畢業。"""
    state = GameState(horses=starter_horses(), jockeys={})
    market = generate_horse_market(30, {h.name for h in state.horses})
    for h in market:
        if h.age == A.MAIDEN_RACE_AGE:
            assert h.career_starts == 0 or h.graduated
        else:
            assert h.graduated


def test_market_value_increases_with_rating_potential_room_fame_and_earnings():
    base = make_horse(fame=0.0, money_earned=0.0, graduated=False, potential_cap=60)
    base.stats = {s: 60.0 for s in base.stats}
    base_value = horse_market_value(base)

    higher_rating = make_horse(fame=0.0, money_earned=0.0, graduated=False, potential_cap=90)
    higher_rating.stats = {s: 80.0 for s in higher_rating.stats}
    assert horse_market_value(higher_rating) > base_value

    more_potential_room = make_horse(fame=0.0, money_earned=0.0, graduated=False, potential_cap=95)
    more_potential_room.stats = {s: 60.0 for s in more_potential_room.stats}
    assert horse_market_value(more_potential_room) > base_value

    more_fame = make_horse(fame=50.0, money_earned=0.0, graduated=False, potential_cap=60)
    more_fame.stats = {s: 60.0 for s in more_fame.stats}
    assert horse_market_value(more_fame) > base_value

    more_earnings = make_horse(fame=0.0, money_earned=100000.0, graduated=False, potential_cap=60)
    more_earnings.stats = {s: 60.0 for s in more_earnings.stats}
    assert horse_market_value(more_earnings) > base_value

    graduated = make_horse(fame=0.0, money_earned=0.0, graduated=True, potential_cap=60)
    graduated.stats = {s: 60.0 for s in graduated.stats}
    assert horse_market_value(graduated) > base_value


def test_buy_horse_deducts_money_adds_to_stable_and_removes_from_market():
    market_horse = make_horse(name="市場馬測試", potential_cap=80)
    state = GameState(horses=[], jockeys={}, money=100000.0, horse_market=[market_horse])
    price = horse_market_value(market_horse)

    msg = buy_horse(state, "市場馬測試")
    assert "買下了" in msg
    assert state.money == pytest.approx(100000.0 - price)
    assert any(h.name == "市場馬測試" for h in state.horses)
    assert not any(h.name == "市場馬測試" for h in state.horse_market)
    assert "市場馬測試" in state.jockeys
    assert state.transaction_history == [f"第1週｜購入現役馬 市場馬測試｜-{price:,.0f}"]


def test_buy_horse_skips_when_money_insufficient():
    market_horse = make_horse(name="買不起的馬", potential_cap=80)
    state = GameState(horses=[], jockeys={}, money=0.0, horse_market=[market_horse])

    msg = buy_horse(state, "買不起的馬")
    assert "資金不足" in msg
    assert state.money == 0.0
    assert not any(h.name == "買不起的馬" for h in state.horses)
    assert any(h.name == "買不起的馬" for h in state.horse_market)  # 沒買到，還留在市場上


def test_buy_horse_with_unknown_name_returns_message_without_crashing():
    state = GameState(horses=[], jockeys={}, money=100000.0, horse_market=[])
    msg = buy_horse(state, "不存在的馬")
    assert "找不到" in msg


def test_sell_horse_adds_money_and_removes_from_stable_and_jockeys():
    horse = make_horse(name="待售馬")
    state = GameState(
        horses=[horse], jockeys={"待售馬": make_jockey()}, money=50000.0,
    )
    price = horse_market_value(horse)

    msg = sell_horse(state, "待售馬")
    assert "賣掉了" in msg
    assert state.money == pytest.approx(50000.0 + price)
    assert not any(h.name == "待售馬" for h in state.horses)
    assert "待售馬" not in state.jockeys
    assert state.transaction_history == [f"第1週｜出售 待售馬｜+{price:,.0f}"]


def test_transaction_history_keeps_latest_twenty_successful_trades():
    state = GameState(horses=[], jockeys={})
    state.transaction_history = [f"舊交易{i}" for i in range(20)]
    horse = make_horse(name="第21筆", potential_cap=80)
    state.horse_market = [horse]
    state.money = 100000.0

    buy_horse(state, horse.name)

    assert len(state.transaction_history) == 20
    assert state.transaction_history[0].startswith("第1週｜購入現役馬 第21筆")
    assert "舊交易19" not in state.transaction_history


def test_sell_horse_with_unknown_name_returns_message_without_crashing():
    state = GameState(horses=[], jockeys={}, money=50000.0)
    msg = sell_horse(state, "不存在的馬")
    assert "找不到" in msg
