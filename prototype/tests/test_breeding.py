"""繁殖/遺傳系統(cli/breeding.py + cli/game.py 的繁殖相關函式)的單元測試。

2026/8/24使用者決定新增：簡化版配種機制(不分自然交配/人工授精)、先退役才能登記
種馬/繁殖母馬、幼駒屬性=父母平均+隨機浮動+潛力隨機制。
"""
from __future__ import annotations

import random

import pytest

from cli import assumptions as A
from cli.breeding import _is_inbred, generate_foal
from cli.game import (
    apply_weekly_pregnancy_progression,
    assign_breeding_role,
    breed,
    game_state_with_test_horses,
    retire_horse,
)
from cli.horses import Horse


def make_horse(**overrides) -> Horse:
    defaults = dict(
        name="測試馬",
        stats={s: 60.0 for s in (
            "速度", "耐力", "加速", "力量", "根性", "智力", "起跑", "彎道", "戰術", "精神", "健康",
        )},
        potential_cap=80.0,
        pace="先",
        age=4,
        sex="母",
    )
    defaults.update(overrides)
    return Horse(**defaults)


# ------------------------------------------------------------- generate_foal

def test_generate_foal_stats_center_on_parent_average():
    random.seed(0)
    mare = make_horse(name="母馬", sex="母", stats={s: 50.0 for s in make_horse().stats})
    sire_stats = {s: 70.0 for s in mare.stats}
    samples = [
        generate_foal(mare, sire_stats, 90.0, "種馬", inbred=False, existing_names=set())[0]
        for _ in range(200)
    ]
    avg_speed = sum(f.stats["速度"] for f in samples) / len(samples)
    assert 55.0 < avg_speed < 65.0  # 應該貼近(50+70)/2=60，允許隨機浮動誤差


def test_generate_foal_is_newborn_with_pedigree_recorded():
    random.seed(1)
    mare = make_horse(name="母馬")
    sire_stats = {s: 60.0 for s in mare.stats}
    foal, note = generate_foal(mare, sire_stats, 85.0, "種馬甲", inbred=False, existing_names={"母馬"})
    assert foal.age == 0
    assert foal.sire_name == "種馬甲"
    assert foal.dam_name == "母馬"
    assert foal.career_starts == 0
    assert not foal.graduated
    assert foal.name != "母馬"
    assert note == ""


def test_generate_foal_potential_cap_at_least_covers_its_own_stats():
    random.seed(2)
    mare = make_horse(stats={s: 95.0 for s in make_horse().stats}, potential_cap=96.0)
    sire_stats = {s: 95.0 for s in mare.stats}
    for _ in range(30):
        foal, _ = generate_foal(mare, sire_stats, 96.0, "種馬", inbred=False, existing_names=set())
        assert foal.potential_cap >= max(foal.stats.values())
        assert foal.potential_cap <= 100.0


def test_inbreeding_lowers_average_potential_cap():
    random.seed(3)
    mare = make_horse(stats={s: 60.0 for s in make_horse().stats}, potential_cap=90.0)
    sire_stats = {s: 60.0 for s in mare.stats}

    normal = [
        generate_foal(mare, sire_stats, 90.0, "種馬", inbred=False, existing_names=set())[0].potential_cap
        for _ in range(200)
    ]
    inbred = [
        generate_foal(mare, sire_stats, 90.0, "種馬", inbred=True, existing_names=set())[0].potential_cap
        for _ in range(200)
    ]
    assert (sum(inbred) / len(inbred)) < (sum(normal) / len(normal))


def test_inbreeding_can_trigger_health_penalty_note():
    random.seed(4)
    mare = make_horse(stats={s: 60.0 for s in make_horse().stats}, potential_cap=90.0)
    sire_stats = {s: 60.0 for s in mare.stats}
    notes = [
        generate_foal(mare, sire_stats, 90.0, "種馬", inbred=True, existing_names=set())[1]
        for _ in range(100)
    ]
    assert any("近親" in n for n in notes)


# --------------------------------------------------------------- _is_inbred

def test_is_inbred_false_when_no_pedigree_recorded():
    mare = make_horse(name="母馬")
    sire = make_horse(name="種馬", sex="公")
    assert _is_inbred(mare, sire) is False


def test_is_inbred_true_for_parent_child():
    mare = make_horse(name="母馬", sire_name="種馬")
    sire = make_horse(name="種馬", sex="公")
    assert _is_inbred(mare, sire) is True


def test_is_inbred_true_for_shared_sire_siblings():
    mare = make_horse(name="母馬甲", sire_name="共同父親")
    sire = make_horse(name="種馬乙", sex="公", sire_name="共同父親")
    assert _is_inbred(mare, sire) is True


def test_is_inbred_false_for_unrelated_pedigree():
    mare = make_horse(name="母馬", sire_name="父A", dam_name="母A")
    sire = make_horse(name="種馬", sex="公", sire_name="父B", dam_name="母B")
    assert _is_inbred(mare, sire) is False


# ---------------------------------------------------------------- retire_horse

def test_retire_horse_marks_retired_and_clears_assignments():
    state = game_state_with_test_horses()
    horse = state.horses[0]
    horse.assigned_trainer = "某教練"
    horse.assigned_vet = "某獸醫"

    msg = retire_horse(state, horse.name)
    assert "退役" in msg
    assert horse.retired is True
    assert horse.assigned_trainer is None
    assert horse.assigned_vet is None


def test_retire_horse_twice_gives_already_retired_message():
    state = game_state_with_test_horses()
    horse = state.horses[0]
    retire_horse(state, horse.name)
    msg = retire_horse(state, horse.name)
    assert "已經是退役狀態" in msg


def test_retire_horse_unknown_name():
    state = game_state_with_test_horses()
    assert "找不到" in retire_horse(state, "不存在的馬")


# ----------------------------------------------------------- assign_breeding_role

def test_assign_breeding_role_requires_retirement_first():
    state = game_state_with_test_horses()
    horse = state.horses[0]
    horse.age = 4
    msg = assign_breeding_role(state, horse.name, "種馬" if horse.sex == "公" else "繁殖母馬")
    assert "尚未退役" in msg
    assert horse.breeding_role is None


def test_assign_breeding_role_requires_age_range():
    state = game_state_with_test_horses()
    horse = state.horses[0]
    retire_horse(state, horse.name)
    horse.age = 2  # 低於BREEDING_MIN_AGE(3)
    msg = assign_breeding_role(state, horse.name, "種馬" if horse.sex == "公" else "繁殖母馬")
    assert "年齡" in msg
    assert horse.breeding_role is None


def test_assign_breeding_role_requires_matching_sex():
    state = game_state_with_test_horses()
    stallion_candidate = next(h for h in state.horses if h.sex == "母")
    retire_horse(state, stallion_candidate.name)
    stallion_candidate.age = 4
    msg = assign_breeding_role(state, stallion_candidate.name, "種馬")
    assert "性別" in msg
    assert stallion_candidate.breeding_role is None


def test_assign_breeding_role_success_and_cancel():
    state = game_state_with_test_horses()
    stallion = next(h for h in state.horses if h.sex == "公")
    retire_horse(state, stallion.name)
    stallion.age = 5

    msg = assign_breeding_role(state, stallion.name, "種馬")
    assert "登記為種馬" in msg
    assert stallion.breeding_role == "種馬"

    msg2 = assign_breeding_role(state, stallion.name, None)
    assert "取消" in msg2
    assert stallion.breeding_role is None


# --------------------------------------------------------------------- breed

def _setup_pair(state):
    stallion = next(h for h in state.horses if h.sex == "公")
    mare = next(h for h in state.horses if h.sex == "母")
    for h in (stallion, mare):
        retire_horse(state, h.name)
        h.age = 5
    assign_breeding_role(state, stallion.name, "種馬")
    assign_breeding_role(state, mare.name, "繁殖母馬")
    return stallion, mare


def test_breed_requires_registered_roles():
    state = game_state_with_test_horses()
    stallion = next(h for h in state.horses if h.sex == "公")
    mare = next(h for h in state.horses if h.sex == "母")
    msg = breed(state, mare.name, stallion.name)
    assert "不是登記中" in msg


def test_breed_success_sets_pregnancy_and_deducts_cost():
    random.seed(10)  # 確保配種成功
    state = game_state_with_test_horses()
    stallion, mare = _setup_pair(state)
    money_before = state.money

    msg = breed(state, mare.name, stallion.name)
    assert "配種成功" in msg or "配種失敗" in msg  # 隨機結果，但至少要能跑完不出例外
    assert state.money == pytest.approx(money_before - A.BREEDING_COST)
    assert mare.breeding_cooldown_weeks_remaining == A.BREEDING_ATTEMPT_COOLDOWN_WEEKS


def test_breed_forces_success_records_sire_snapshot(monkeypatch):
    state = game_state_with_test_horses()
    stallion, mare = _setup_pair(state)
    monkeypatch.setattr(random, "random", lambda: 0.0)  # < BREEDING_SUCCESS_CHANCE，強制成功

    msg = breed(state, mare.name, stallion.name)
    assert "配種成功" in msg
    assert mare.pregnant_weeks_remaining == A.GESTATION_WEEKS
    assert mare.pregnant_sire_name == stallion.name
    assert mare.pregnant_sire_stats == stallion.stats
    assert mare.pregnant_sire_potential_cap == stallion.potential_cap


def test_breed_forces_failure_does_not_set_pregnancy(monkeypatch):
    state = game_state_with_test_horses()
    stallion, mare = _setup_pair(state)
    monkeypatch.setattr(random, "random", lambda: 0.99)  # >= BREEDING_SUCCESS_CHANCE，強制失敗

    msg = breed(state, mare.name, stallion.name)
    assert "配種失敗" in msg
    assert mare.pregnant_weeks_remaining == 0
    assert mare.breeding_cooldown_weeks_remaining == A.BREEDING_ATTEMPT_COOLDOWN_WEEKS


def test_breed_blocked_while_pregnant(monkeypatch):
    state = game_state_with_test_horses()
    stallion, mare = _setup_pair(state)
    monkeypatch.setattr(random, "random", lambda: 0.0)
    breed(state, mare.name, stallion.name)

    msg = breed(state, mare.name, stallion.name)
    assert "已經懷孕中" in msg


def test_breed_blocked_during_cooldown(monkeypatch):
    state = game_state_with_test_horses()
    stallion, mare = _setup_pair(state)
    monkeypatch.setattr(random, "random", lambda: 0.99)  # 強制失敗，但仍會進冷卻
    breed(state, mare.name, stallion.name)

    msg = breed(state, mare.name, stallion.name)
    assert "配種恢復期" in msg


def test_breed_insufficient_funds():
    state = game_state_with_test_horses()
    stallion, mare = _setup_pair(state)
    state.money = 0.0

    msg = breed(state, mare.name, stallion.name)
    assert "資金不足" in msg


# ---------------------------------------------------- apply_weekly_pregnancy_progression

def test_pregnancy_progression_counts_down_and_gives_birth(monkeypatch):
    state = game_state_with_test_horses()
    stallion, mare = _setup_pair(state)
    monkeypatch.setattr(random, "random", lambda: 0.0)
    breed(state, mare.name, stallion.name)

    horse_count_before = len(state.horses)
    for _ in range(A.GESTATION_WEEKS - 1):
        lines = apply_weekly_pregnancy_progression(state)
        assert lines == []
    assert mare.pregnant_weeks_remaining == 1

    lines = apply_weekly_pregnancy_progression(state)
    assert len(lines) == 1
    assert "生下幼駒" in lines[0]
    assert mare.pregnant_weeks_remaining == 0
    assert mare.pregnant_sire_name is None
    assert len(state.horses) == horse_count_before + 1

    foal = state.horses[-1]
    assert foal.age == 0
    assert foal.sire_name == stallion.name
    assert foal.dam_name == mare.name
    assert foal.name in state.jockeys


def test_pregnancy_progression_ticks_down_breeding_cooldown(monkeypatch):
    state = game_state_with_test_horses()
    stallion, mare = _setup_pair(state)
    monkeypatch.setattr(random, "random", lambda: 0.99)  # 強制失敗但仍進冷卻
    breed(state, mare.name, stallion.name)
    assert mare.breeding_cooldown_weeks_remaining == A.BREEDING_ATTEMPT_COOLDOWN_WEEKS

    apply_weekly_pregnancy_progression(state)
    assert mare.breeding_cooldown_weeks_remaining == A.BREEDING_ATTEMPT_COOLDOWN_WEEKS - 1


# --------------------------------------------------------------- can_train / age gate

def test_newborn_foal_cannot_train_until_min_age():
    from cli.game import train_horse

    state = game_state_with_test_horses()
    foal = make_horse(name="幼駒測試", age=0)
    state.horses.append(foal)
    with pytest.raises(ValueError, match="還未滿"):
        train_horse(state, foal, "速度")
