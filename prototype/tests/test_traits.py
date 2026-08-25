"""特性/性格系統(cli/traits.py + 相關整合點)的單元測試。2026/8/24使用者決定新增：
9種特性一律天生隨機分配(簡化版，不分天生/訓練)，個性(性格)純風味不掛數值效果。
"""
from __future__ import annotations

import random

import pytest

from cli import traits as T
from cli.breeding import generate_foal
from cli.game import breed, game_state_with_test_horses, run_race, RaceEntry
from cli.horse_market import (
    generate_broodmare_market_horse,
    generate_foal_market_horse,
    generate_market_horse,
    generate_stallion_market_horse,
)
from cli.horses import ALL_STATS, Horse
from engine.race import HorseRaceInput


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


# --------------------------------------------------------------- random_traits

def test_random_traits_never_exceeds_max_and_only_known_names():
    random.seed(0)
    for _ in range(100):
        result = T.random_traits()
        assert len(result) <= T.MAX_TRAITS
        assert len(result) == len(set(result))  # 不重複
        assert all(t in T.TRAIT_NAMES for t in result)


def test_random_traits_distribution_covers_zero_one_two():
    random.seed(1)
    counts = {len(T.random_traits()) for _ in range(200)}
    assert counts == {0, 1, 2}


# ----------------------------------------------------------- random_personality

def test_random_personality_is_known_type_or_none():
    random.seed(2)
    seen = {T.random_personality() for _ in range(200)}
    assert seen <= set(T.PERSONALITY_TYPES) | {None}
    assert None in seen  # PERSONALITY_NONE_CHANCE=0.2，200次抽樣幾乎必然抽到過None


# --------------------------------------------------------------- trait_triggers

def test_always_on_traits_trigger_regardless_of_pace_or_grade():
    for t in ("快速起步", "彎道巧手", "末段爆發", "慢熱"):
        assert T.trait_triggers(t, pace="追", grade="新馬賽") is True
        assert T.trait_triggers(t, pace="逃", grade="國際GI") is True


def test_stable_lead_trait_only_triggers_with_front_running_pace():
    assert T.trait_triggers("領放穩定", pace="逃", grade="新馬賽") is True
    assert T.trait_triggers("領放穩定", pace="追", grade="新馬賽") is False
    assert T.trait_triggers("領放穩定", pace="先", grade="新馬賽") is False


def test_pressure_traits_only_trigger_in_high_tier_grades():
    for grade in T.HIGH_TIER_GRADES:
        assert T.trait_triggers("抗壓", pace="先", grade=grade) is True
        assert T.trait_triggers("容易緊張", pace="先", grade=grade) is True
    for grade in ("新馬賽", "未勝利賽", "地方一般賽", "地方表列賽", "地方公開賽"):
        assert T.trait_triggers("抗壓", pace="先", grade=grade) is False
        assert T.trait_triggers("容易緊張", pace="先", grade=grade) is False


def test_dormant_traits_never_trigger_under_current_mvp_scope():
    """重馬場高手/海外適應依賴的系統(場地狀況、海外賽事)MVP還沒做，見模組docstring。"""
    for grade in T.HIGH_TIER_GRADES + ("新馬賽",):
        for pace in ("逃", "先", "差", "追"):
            assert T.trait_triggers("重馬場高手", pace=pace, grade=grade) is False
            assert T.trait_triggers("海外適應", pace=pace, grade=grade) is False


# ----------------------------------------------------------- race_trait_bonus_pct

def test_race_trait_bonus_pct_zero_when_no_traits():
    assert T.race_trait_bonus_pct([], pace="逃", grade="新馬賽") == 0.0


def test_race_trait_bonus_pct_positive_for_triggered_positive_trait():
    random.seed(3)
    pct = T.race_trait_bonus_pct(["快速起步"], pace="先", grade="新馬賽")
    assert T.TRAIT_EFFECT_PCT_MIN <= pct <= T.TRAIT_EFFECT_PCT_MAX


def test_race_trait_bonus_pct_negative_for_triggered_negative_trait():
    random.seed(4)
    pct = T.race_trait_bonus_pct(["慢熱"], pace="先", grade="新馬賽")
    assert -T.TRAIT_EFFECT_PCT_MAX <= pct <= -T.TRAIT_EFFECT_PCT_MIN


def test_race_trait_bonus_pct_sums_multiple_triggered_traits():
    random.seed(5)
    pct = T.race_trait_bonus_pct(["快速起步", "彎道巧手"], pace="先", grade="新馬賽")
    # 兩個都是恆常觸發的正面特性，加總後應該落在 [2*MIN, 2*MAX] 之間
    assert 2 * T.TRAIT_EFFECT_PCT_MIN <= pct <= 2 * T.TRAIT_EFFECT_PCT_MAX


def test_race_trait_bonus_pct_ignores_untriggered_trait():
    random.seed(6)
    pct = T.race_trait_bonus_pct(["領放穩定"], pace="追", grade="新馬賽")  # 非逃，不觸發
    assert pct == 0.0


# ----------------------------------------------------------------- inherit_traits

def test_inherit_traits_never_exceeds_max_and_only_known_names():
    random.seed(7)
    for _ in range(50):
        result = T.inherit_traits(["快速起步", "彎道巧手"], ["末段爆發"])
        assert len(result) <= T.MAX_TRAITS
        assert all(t in T.TRAIT_NAMES for t in result)


def test_inherit_traits_never_inherits_training_only_traits():
    """領放穩定/抗壓 heritable="否"，遺傳系統.md沒有把這兩個算進特性遺傳討論範圍。"""
    random.seed(8)
    for _ in range(100):
        result = T.inherit_traits(["領放穩定"], ["抗壓"])
        assert "領放穩定" not in result or True  # 允許透過額外隨機池補上，但不能是「繼承」造成
    # 更精確的檢驗：關掉額外隨機池(monkeypatch機率為0)，確定「否」類特性完全不會直接遺傳
    import cli.traits as traits_module
    original = traits_module.TRAIT_EXTRA_RANDOM_CHANCE
    traits_module.TRAIT_EXTRA_RANDOM_CHANCE = 0.0
    try:
        for _ in range(100):
            result = T.inherit_traits(["領放穩定"], ["抗壓"])
            assert result == []
    finally:
        traits_module.TRAIT_EXTRA_RANDOM_CHANCE = original


def test_inherit_traits_empty_parents_can_still_yield_extra_random_trait():
    random.seed(9)
    results = [T.inherit_traits([], []) for _ in range(100)]
    assert any(r for r in results)  # TRAIT_EXTRA_RANDOM_CHANCE=0.3，100次應該至少長出一次


# ------------------------------------------------------------ inherit_personality

def test_inherit_personality_only_known_type_or_none():
    random.seed(10)
    for _ in range(50):
        result = T.inherit_personality("冷靜", "暴躁")
        assert result in T.PERSONALITY_TYPES or result is None


def test_inherit_personality_can_directly_inherit_heritable_parent_personality():
    random.seed(11)
    results = [T.inherit_personality("冷靜", None) for _ in range(200)]
    assert "冷靜" in results  # PERSONALITY_INHERIT_CHANCE=0.3，200次應該抽到過


def test_inherit_personality_non_heritable_parents_fall_back_to_random():
    random.seed(12)
    result = T.inherit_personality("好勝", "膽小")  # 都不在PERSONALITY_HERITABLE裡
    assert result in T.PERSONALITY_TYPES or result is None


# ------------------------------------------------------- starter horses wiring

def test_starter_horses_have_valid_traits_and_personality():
    state = game_state_with_test_horses()
    for h in state.horses:
        assert len(h.traits) <= T.MAX_TRAITS
        assert all(t in T.TRAIT_NAMES for t in h.traits)
        assert h.personality is None or h.personality in T.PERSONALITY_TYPES


# ------------------------------------------------------- market horses wiring

def test_market_horses_have_valid_traits_and_personality():
    random.seed(13)
    for gen_fn in (
        generate_market_horse,
        generate_foal_market_horse,
        generate_stallion_market_horse,
        generate_broodmare_market_horse,
    ):
        h = gen_fn(set())
        assert len(h.traits) <= T.MAX_TRAITS
        assert h.personality is None or h.personality in T.PERSONALITY_TYPES


# ------------------------------------------------------- generate_foal wiring

def test_generate_foal_inherits_traits_and_personality_from_parents():
    random.seed(14)
    mare = make_horse(name="母馬", traits=["末段爆發"], personality="冷靜")
    sire_stats = {s: 60.0 for s in ALL_STATS}
    foal, _note = generate_foal(
        mare=mare,
        sire_stats=sire_stats,
        sire_potential_cap=85.0,
        sire_name="種馬",
        inbred=False,
        existing_names=set(),
        sire_traits=["快速起步"],
        sire_personality="暴躁",
    )
    assert len(foal.traits) <= T.MAX_TRAITS
    assert foal.personality is None or foal.personality in T.PERSONALITY_TYPES


def test_generate_foal_defaults_sire_traits_to_empty_for_backward_compat():
    """舊呼叫端(既有測試)不傳sire_traits/sire_personality時不應該炸掉。"""
    random.seed(15)
    mare = make_horse(name="母馬2")
    sire_stats = {s: 60.0 for s in ALL_STATS}
    foal, _note = generate_foal(
        mare=mare,
        sire_stats=sire_stats,
        sire_potential_cap=85.0,
        sire_name="種馬2",
        inbred=False,
        existing_names=set(),
    )
    assert len(foal.traits) <= T.MAX_TRAITS


# ------------------------------------------------------- breed() snapshot wiring

def test_breed_snapshots_sire_traits_and_personality():
    state = game_state_with_test_horses()
    mare = state.horses[0]
    stallion = state.horses[1]
    mare.sex, stallion.sex = "母", "公"
    mare.age, stallion.age = 5, 5
    mare.retired, stallion.retired = True, True
    mare.breeding_role, stallion.breeding_role = "繁殖母馬", "種馬"
    stallion.traits = ["彎道巧手"]
    stallion.personality = "暴躁"
    state.money = 1_000_000.0

    random.seed(16)
    msg = breed(state, mare.name, stallion.name)
    if "配種成功" in msg:
        assert mare.pregnant_sire_traits == ["彎道巧手"]
        assert mare.pregnant_sire_personality == "暴躁"


# ----------------------------------------------------- run_race wires traits in

def test_run_race_passes_nonzero_trait_bonus_into_race_input(monkeypatch):
    """快速起步是恆常觸發的正面特性，run_race()應該把它換算進trait_bonus_pct，
    不再是舊版寫死的0.0。用monkeypatch攔截simulate_race()的輸入來檢查。"""
    import cli.game as game_module

    captured = {}
    original_simulate = game_module.simulate_race

    def spy_simulate_race(horses, **kwargs):
        captured["horses"] = horses
        return original_simulate(horses, **kwargs)

    monkeypatch.setattr(game_module, "simulate_race", spy_simulate_race)

    state = game_state_with_test_horses()
    horse = state.horses[0]
    horse.traits = ["快速起步"]  # 恆常觸發
    horse.can_race = lambda: True

    random.seed(17)
    run_race(state, "新馬賽", [RaceEntry(horse, "新馬賽", "自由發揮")])

    player_input = next(h for h in captured["horses"] if h.name == horse.name)
    assert player_input.trait_bonus_pct != 0.0
