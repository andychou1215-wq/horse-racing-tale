"""訓練成長公式（docs/培育/培育系統.md）。

一次訓練成長量 = 基礎訓練值 × 潛力餘裕 × 年齡成長倍率 × 訓練師 × 設施 × 狀態
潛力餘裕 = (潛力上限 − 該屬性目前值) ÷ 100

採「潛力餘裕」而非固定「潛力」乘數：越接近潛力上限、單次訓練成長越自然
趨緩，不需要額外的 MIN() 硬上限（見 docs/培育/培育系統.md 修正說明）。
"""
from __future__ import annotations

from dataclasses import dataclass


def potential_margin(potential_cap: float, current_value: float) -> float:
    """潛力餘裕 = (潛力上限 - 目前值) / 100。

    若目前值已經超過潛力上限（例如資料設定失誤，或未來允許暫時超綱的特殊
    效果），餘裕封底於 0，避免訓練公式算出負成長反而把數值往下拉。
    """
    return max(0.0, (potential_cap - current_value) / 100)


def training_growth(
    base_training_value: float,
    potential_cap: float,
    current_value: float,
    age_stage_multiplier: float,
    trainer_multiplier: float = 1.0,
    facility_multiplier: float = 1.0,
    status_multiplier: float = 1.0,
) -> float:
    """單次訓練的能力成長量。

    對應 培育系統.md：
        成長量 = 基礎訓練值 × 潛力餘裕 × 年齡成長倍率 × 訓練師 × 設施 × 狀態
    """
    margin = potential_margin(potential_cap, current_value)
    return (
        base_training_value
        * margin
        * age_stage_multiplier
        * trainer_multiplier
        * facility_multiplier
        * status_multiplier
    )


def apply_training(
    base_training_value: float,
    potential_cap: float,
    current_value: float,
    age_stage_multiplier: float,
    trainer_multiplier: float = 1.0,
    facility_multiplier: float = 1.0,
    status_multiplier: float = 1.0,
) -> float:
    """套用一次訓練後的新能力值，並封頂於潛力上限（不會超過 potential_cap）。"""
    growth = training_growth(
        base_training_value,
        potential_cap,
        current_value,
        age_stage_multiplier,
        trainer_multiplier,
        facility_multiplier,
        status_multiplier,
    )
    return min(current_value + growth, potential_cap)


def growth_stage_for_week(
    week: int,
    rising_end_week: int,
    peak_end_week: int,
    plateau_end_week: int,
) -> str:
    """依週次判斷年齡成長階段：上升期/巔峰期/停滯期/衰退期。"""
    if week <= rising_end_week:
        return "上升期"
    if week <= peak_end_week:
        return "巔峰期"
    if week <= plateau_end_week:
        return "停滯期"
    return "衰退期"


@dataclass
class WeeklyGrowthPoint:
    week: int
    stage: str
    age_multiplier: float
    growth: float
    value: float
    percent_of_cap: float


def simulate_growth_curve(
    weeks: int,
    potential_cap: float,
    start_value: float,
    base_training_value: float,
    trainer_multiplier: float,
    facility_multiplier: float,
    status_multiplier: float,
    rising_end_week: int,
    peak_end_week: int,
    plateau_end_week: int,
    age_stage_multiplier: dict[str, float],
) -> list[WeeklyGrowthPoint]:
    """模擬連續多週、每週訓練一次同一屬性的成長曲線。

    對應 `數值平衡試算.xlsx`「訓練成長模擬」分頁：每週訓練一次，能力值
    封頂於潛力上限（MIN 函數）。
    """
    points: list[WeeklyGrowthPoint] = []
    value = start_value
    for week in range(1, weeks + 1):
        stage = growth_stage_for_week(week, rising_end_week, peak_end_week, plateau_end_week)
        age_mult = age_stage_multiplier[stage]
        growth = training_growth(
            base_training_value,
            potential_cap,
            value,
            age_mult,
            trainer_multiplier,
            facility_multiplier,
            status_multiplier,
        )
        value = min(value + growth, potential_cap)
        points.append(
            WeeklyGrowthPoint(
                week=week,
                stage=stage,
                age_multiplier=age_mult,
                growth=growth,
                value=value,
                percent_of_cap=value / potential_cap,
            )
        )
    return points
