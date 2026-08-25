"""訓練成長引擎 vs 數值平衡試算.xlsx「訓練成長模擬」分頁 — 逐週比對。"""
import pytest

from engine.training import simulate_growth_curve, training_growth

# 對應 訓練成長模擬 分頁 B2~B14 輸入值
POTENTIAL_CAP = 85
START_VALUE = 30
BASE_TRAINING_VALUE = 2
TRAINER_MULTIPLIER = 1.1
FACILITY_MULTIPLIER = 1.1
STATUS_MULTIPLIER = 1
RISING_END_WEEK = 52
PEAK_END_WEEK = 104
PLATEAU_END_WEEK = 130
AGE_STAGE_MULTIPLIER = {
    "上升期": 1.2,
    "巔峰期": 1.0,
    "停滯期": 0.5,
    "衰退期": 0.1,
}

# 試算表逐週計算結果（週次: (成長量, 累積值, 達潛力上限%)），取自 xlsx 資料列
EXPECTED_POINTS = {
    1: (1.5972, 31.5972, 0.371731764705882),
    2: (1.550817312, 33.148017312, 0.389976674258824),
    3: (1.50578157725952, 34.6537988892595, 0.407691751638347),
    4: (1.4620536802559, 36.1158525695154, 0.42489238317077),
    5: (1.41959564138127, 37.5354482108967, 0.441593508363491),
    53: (0.287506508092738, 73.4070722893846, 0.86361261516923),
    103: (0.0844672526635106, 81.5940849111961, 0.959930410719955),
    150: (0.00559699032142229, 82.6927910723783, 0.972856365557392),
}


@pytest.fixture(scope="module")
def growth_curve():
    return simulate_growth_curve(
        weeks=150,
        potential_cap=POTENTIAL_CAP,
        start_value=START_VALUE,
        base_training_value=BASE_TRAINING_VALUE,
        trainer_multiplier=TRAINER_MULTIPLIER,
        facility_multiplier=FACILITY_MULTIPLIER,
        status_multiplier=STATUS_MULTIPLIER,
        rising_end_week=RISING_END_WEEK,
        peak_end_week=PEAK_END_WEEK,
        plateau_end_week=PLATEAU_END_WEEK,
        age_stage_multiplier=AGE_STAGE_MULTIPLIER,
    )


@pytest.mark.parametrize("week", sorted(EXPECTED_POINTS.keys()))
def test_growth_curve_matches_spreadsheet(growth_curve, week):
    expected_growth, expected_value, expected_pct = EXPECTED_POINTS[week]
    point = growth_curve[week - 1]
    assert point.growth == pytest.approx(expected_growth, rel=1e-9)
    assert point.value == pytest.approx(expected_value, rel=1e-9)
    assert point.percent_of_cap == pytest.approx(expected_pct, rel=1e-9)


def test_growth_never_exceeds_potential_cap(growth_curve):
    assert all(p.value <= POTENTIAL_CAP for p in growth_curve)


def test_growth_converges_to_about_97_percent_by_week_150(growth_curve):
    # 對應 變更紀錄.md: 「150週約收斂於潛力上限97%」
    assert growth_curve[-1].percent_of_cap == pytest.approx(0.9729, abs=0.001)


def test_growth_slows_as_value_approaches_cap():
    """潛力餘裕機制：起始值離上限越近，單次成長量越小（同條件下）。"""
    far = training_growth(2, 100, 10, 1.0)
    near = training_growth(2, 100, 90, 1.0)
    assert far > near > 0


def test_growth_is_zero_at_potential_cap():
    growth = training_growth(2, 100, 100, 1.0)
    assert growth == pytest.approx(0.0)


def test_growth_is_zero_not_negative_when_current_exceeds_cap():
    """資料設定失誤(現有值 > 潛力上限)時，訓練不應該讓數值倒退。"""
    growth = training_growth(2, 85, 90, 1.0)
    assert growth == pytest.approx(0.0)
