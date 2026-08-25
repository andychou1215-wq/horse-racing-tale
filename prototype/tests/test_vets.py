"""cli/vets.py 純函式的單元測試。"""
from __future__ import annotations

import pytest

from cli.vets import generate_vet_market


def test_generate_vet_market_returns_requested_count_with_unique_names():
    market = generate_vet_market(count=3)
    assert len(market) == 3
    assert len({v.name for v in market}) == 3


def test_generate_vet_market_hire_fee_and_salary_scale_with_level():
    market = generate_vet_market(count=10)
    for v in market:
        assert v.hire_fee == pytest.approx(1000.0 * v.skill_level)
        assert v.weekly_salary == pytest.approx(250.0 * v.skill_level)
