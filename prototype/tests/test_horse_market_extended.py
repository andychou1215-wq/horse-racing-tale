"""幼駒市場/種馬市場/繁殖母馬市場(cli/horse_market.py 2026/8/24補上的3類)的單元測試。

現役馬市場(generate_market_horse/market_value)已有既有測試覆蓋，這裡只補新增的
3類市場生成邏輯、breeding_stock_value()、以及game.py的buy_foal/buy_stallion/
buy_broodmare。
"""
from __future__ import annotations

import random

import pytest

from cli import assumptions as A
from cli.game import buy_broodmare, buy_foal, buy_stallion, new_game
from cli.horse_market import (
    breeding_stock_value,
    generate_broodmare_market,
    generate_broodmare_market_horse,
    generate_foal_market,
    generate_foal_market_horse,
    generate_stallion_market,
    generate_stallion_market_horse,
    market_value,
)


# ------------------------------------------------------------------- 幼駒市場

def test_generate_foal_market_horse_is_young_with_pedigree():
    random.seed(0)
    for _ in range(30):
        foal = generate_foal_market_horse(set())
        assert foal.age in (0, 1)
        assert foal.career_starts == 0
        assert not foal.graduated
        assert not foal.retired
        assert foal.breeding_role is None
        assert foal.sire_name is not None and foal.dam_name is not None
        assert foal.sire_name != foal.dam_name
        assert foal.potential_cap >= max(foal.stats.values())
        assert foal.potential_cap <= 100.0


def test_generate_foal_market_returns_requested_count_with_unique_names():
    market = generate_foal_market(count=3, existing_names=set())
    assert len(market) == 3
    assert len({h.name for h in market}) == 3


# ----------------------------------------------------------- 種馬/繁殖母馬市場

def test_generate_stallion_market_horse_is_registered_and_retired():
    random.seed(1)
    for _ in range(30):
        stallion = generate_stallion_market_horse(set())
        assert stallion.sex == "公"
        assert stallion.retired is True
        assert stallion.breeding_role == "種馬"
        assert A.BREEDING_MIN_AGE <= stallion.age <= A.BREEDING_MAX_AGE
        assert stallion.graduated is True


def test_generate_broodmare_market_horse_is_registered_and_retired():
    random.seed(2)
    for _ in range(30):
        mare = generate_broodmare_market_horse(set())
        assert mare.sex == "母"
        assert mare.retired is True
        assert mare.breeding_role == "繁殖母馬"
        assert A.BREEDING_MIN_AGE <= mare.age <= A.BREEDING_MAX_AGE


def test_generate_stallion_market_returns_requested_count_with_unique_names():
    market = generate_stallion_market(count=2, existing_names=set())
    assert len(market) == 2
    assert len({h.name for h in market}) == 2


def test_generate_broodmare_market_returns_requested_count_with_unique_names():
    market = generate_broodmare_market(count=2, existing_names=set())
    assert len(market) == 2
    assert len({h.name for h in market}) == 2


def test_breeding_stock_value_adds_ready_bonus_over_market_value():
    random.seed(3)
    stallion = generate_stallion_market_horse(set())
    assert breeding_stock_value(stallion) == pytest.approx(
        market_value(stallion) + A.HORSE_MARKET_BREEDING_READY_BONUS
    )


# ---------------------------------------------------------------- game.py buy_*

def test_buy_foal_adds_to_stable_and_removes_from_market():
    state = new_game()
    state.money = 200000.0
    target = state.foal_market[0].name

    msg = buy_foal(state, target)
    assert "買下了" in msg
    assert any(h.name == target for h in state.horses)
    assert not any(h.name == target for h in state.foal_market)
    assert target in state.jockeys


def test_buy_foal_insufficient_funds_keeps_horse_in_market():
    state = new_game()
    state.money = 0.0
    target = state.foal_market[0].name

    msg = buy_foal(state, target)
    assert "資金不足" in msg
    assert any(h.name == target for h in state.foal_market)
    assert not any(h.name == target for h in state.horses)


def test_buy_stallion_registers_breeding_role_and_is_immediately_ready():
    state = new_game()
    state.money = 500000.0
    target = state.stallion_market[0].name

    msg = buy_stallion(state, target)
    assert "已登記為種馬" in msg
    horse = state.horse_by_name(target)
    assert horse.breeding_role == "種馬"
    assert horse.retired is True


def test_buy_broodmare_registers_breeding_role_and_is_immediately_ready():
    state = new_game()
    state.money = 500000.0
    target = state.broodmare_market[0].name

    msg = buy_broodmare(state, target)
    assert "已登記為繁殖母馬" in msg
    horse = state.horse_by_name(target)
    assert horse.breeding_role == "繁殖母馬"
    assert horse.retired is True


def test_buy_stallion_unknown_name():
    state = new_game()
    assert "找不到" in buy_stallion(state, "不存在的種馬")


def test_market_refresh_replaces_all_four_market_lists():
    from cli.game import MARKET_REFRESH_INTERVAL_WEEKS, refresh_markets_if_due

    state = new_game()
    original = {
        "horse": {h.name for h in state.horse_market},
        "foal": {h.name for h in state.foal_market},
        "stallion": {h.name for h in state.stallion_market},
        "broodmare": {h.name for h in state.broodmare_market},
    }
    state.week += MARKET_REFRESH_INTERVAL_WEEKS
    refresh_markets_if_due(state)
    assert {h.name for h in state.horse_market} != original["horse"]
    assert {h.name for h in state.foal_market} != original["foal"]
    assert {h.name for h in state.stallion_market} != original["stallion"]
    assert {h.name for h in state.broodmare_market} != original["broodmare"]
