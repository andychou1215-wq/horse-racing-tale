"""比賽模擬（docs/比賽/比賽公式.md、docs/比賽/比賽模擬.md、docs/比賽/體力系統.md）。

六階段：起跑 → 前段 → 中段 → 後段 → 最後彎道 → 最後衝刺 → 終點，採
「階段式排名模擬」。

比賽公式：
    基礎能力分數 × 跑法階段倍率 × 騎師修正 × 距離適性 × 場地適性
    × 狀態倍率 × 負磅修正 × 特性 × 戰術波動 × 隨機波動

本模組把「騎師修正 × 距離適性 × 場地適性 × 狀態倍率 × 負磅修正 × 特性
× 戰術波動 × 隨機波動」合併成單一「外部乘數」，再乘上該階段的跑法
階段倍率，等同於 `數值平衡試算.xlsx`「比賽模擬」分頁的算法：
    修正後分數 = 基礎分數 × 外部乘數 × 跑法階段倍率(該階段)

位置值：
    相對階段表現 = (本馬階段表現 − 全場平均階段表現) ÷ 全場平均階段表現
    位置值(第N階段為止) = 目前為止各階段相對表現的平均值（不複利連乘）
    終點名次依據 = 位置值(衝刺階段為止)，數值越大名次越前面
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .constants import (
    AFFINITY_MULTIPLIER,
    BASE_STAMINA_CONSUMPTION,
    PACE_STAGE_MULTIPLIER,
    PACE_STAMINA_MULTIPLIER,
    RACE_STAGES,
    STATUS_MULTIPLIER,
)


@dataclass
class HorseRaceInput:
    """一匹馬的賽前輸入資料（對應「屬性設定」分頁一列）。"""

    name: str
    speed: float  # 速度
    stamina: float  # 耐力
    acceleration: float  # 加速
    power: float  # 力量
    guts: float  # 根性
    intelligence: float  # 智力
    start: float  # 起跑
    corner: float  # 彎道
    tactic_stat: float  # 戰術(屬性)
    mental: float  # 精神
    health: float  # 健康
    pace: str  # 跑法：逃/先/差/追
    distance_affinity: str  # 距離適性等級 S~D
    terrain_affinity: str  # 場地適性等級 S~D
    status_grade: str  # 狀態等級 S~D
    weight_diff_kg: float  # 負磅差(kg)，正值代表加重
    jockey_correction: float  # 騎師修正(整體)，0.9~1.1 一類的倍率
    jockey_position_judgement: float  # 騎師-位置判斷 0~100
    jockey_rhythm_control: float  # 騎師-節奏控制 0~100
    jockey_route_choice: float  # 騎師-路線選擇 0~100
    trait_bonus_pct: float  # 特性加成% (可為負)
    tactic_volatility_pct: float  # 戰術波動% (可為負)
    random_volatility_pct: float  # 隨機波動% (可為負)
    tactic_stamina_multiplier: float = 1.0  # 戰術體力修正


@dataclass
class HorseStageResult:
    stage: str
    base_score: float
    adjusted_score: float
    field_average: float
    relative_performance: float
    position_value: float  # 目前為止的位置值(累積平均)


@dataclass
class HorseRaceResult:
    name: str
    stages: list[HorseStageResult] = field(default_factory=list)
    final_position_value: float = 0.0
    rank: int = 0
    stamina_remaining: dict[str, float] = field(default_factory=dict)


def external_multiplier(horse: HorseRaceInput) -> float:
    """外部乘數 = 騎師修正 × 距離適性 × 場地適性 × 狀態倍率
    × 負磅修正 × (1+特性) × (1+戰術波動) × (1+隨機波動)。

    對應 `數值平衡試算.xlsx` AG 欄公式。
    """
    return (
        horse.jockey_correction
        * AFFINITY_MULTIPLIER[horse.distance_affinity]
        * AFFINITY_MULTIPLIER[horse.terrain_affinity]
        * STATUS_MULTIPLIER[horse.status_grade]
        * (1 - 0.01 * horse.weight_diff_kg)
        * (1 + horse.trait_bonus_pct)
        * (1 + horse.tactic_volatility_pct)
        * (1 + horse.random_volatility_pct)
    )


def endurance_stamina_modifier(stamina: float) -> float:
    """耐力修正 = 1.2 − (耐力/100) × 0.4，範圍 0.8~1.2（體力系統.md）。"""
    return 1.2 - (stamina / 100) * 0.4


def jockey_affinity_front(horse: HorseRaceInput) -> float:
    """騎師適配度(前段) = 位置判斷×0.6 + 節奏控制×0.4。"""
    return horse.jockey_position_judgement * 0.6 + horse.jockey_rhythm_control * 0.4


def jockey_affinity_mid(horse: HorseRaceInput) -> float:
    """騎師適配度(中段) = 節奏控制×0.5 + 路線選擇×0.5。"""
    return horse.jockey_rhythm_control * 0.5 + horse.jockey_route_choice * 0.5


def base_score_start(horse: HorseRaceInput) -> float:
    """起跑基礎階段表現分數 = 加速×0.3 + 起跑×0.5 + 精神×0.2。"""
    return horse.acceleration * 0.3 + horse.start * 0.5 + horse.mental * 0.2


def base_score_front(horse: HorseRaceInput) -> float:
    """前段基礎階段表現分數 = 速度×0.65 + 騎師適配度×0.35。"""
    return horse.speed * 0.65 + jockey_affinity_front(horse) * 0.35


def base_score_mid(horse: HorseRaceInput) -> float:
    """中段基礎階段表現分數 = 速度×0.3 + 耐力×0.3 + 騎師適配度×0.4。"""
    return horse.speed * 0.3 + horse.stamina * 0.3 + jockey_affinity_mid(horse) * 0.4


def base_score_back(horse: HorseRaceInput, remaining_stamina_after_back: float) -> float:
    """後段基礎階段表現分數 = 耐力×0.5 + 根性×0.2 + 剩餘體力×0.3。

    `remaining_stamina_after_back` 為「後段」結束後(扣除後段自身消耗後)的剩餘體力(%)，
    對應 `數值平衡試算.xlsx` Q欄公式直接引用 AN欄(後段剩餘)，而非中段結束時的剩餘體力。
    """
    return horse.stamina * 0.5 + horse.guts * 0.2 + remaining_stamina_after_back * 0.3


def base_score_corner(horse: HorseRaceInput) -> float:
    """彎道基礎階段表現分數 = 力量×0.2 + 智力×0.4 + 彎道×0.4。"""
    return horse.power * 0.2 + horse.intelligence * 0.4 + horse.corner * 0.4


def base_score_sprint(horse: HorseRaceInput) -> float:
    """衝刺基礎階段表現分數 = 速度×0.4 + 加速×0.4 + 根性×0.2。"""
    return horse.speed * 0.4 + horse.acceleration * 0.4 + horse.guts * 0.2


def stage_stamina_consumption(
    stage: str,
    horse: HorseRaceInput,
    distance_mod: float,
    terrain_mod: float,
) -> float:
    """階段體力消耗 = 基礎消耗 × 距離修正 × 耐力修正 × 跑法修正 × 戰術修正 × 場地修正。

    `stage` 須為 "前段"/"中段"/"後段"/"衝刺"（起跑無消耗計算，恆為100%）。
    """
    base = BASE_STAMINA_CONSUMPTION[stage]
    endurance_mod = endurance_stamina_modifier(horse.stamina)
    pace_mod = PACE_STAMINA_MULTIPLIER[horse.pace][stage]
    return base * distance_mod * endurance_mod * pace_mod * horse.tactic_stamina_multiplier * terrain_mod


def simulate_stamina(
    horse: HorseRaceInput, distance_mod: float, terrain_mod: float
) -> dict[str, float]:
    """依序計算前段/中段/後段結束後的剩餘體力(%)，起跑固定100%。"""
    remaining = {"起跑": 100.0}
    current = 100.0
    for stage in ("前段", "中段", "後段"):
        consumption = stage_stamina_consumption(stage, horse, distance_mod, terrain_mod)
        current = current - consumption
        remaining[stage] = current
    return remaining


_BASE_SCORE_FUNCS = {
    "起跑": lambda h, remaining: base_score_start(h),
    "前段": lambda h, remaining: base_score_front(h),
    "中段": lambda h, remaining: base_score_mid(h),
    "後段": lambda h, remaining: base_score_back(h, remaining["後段"]),
    "彎道": lambda h, remaining: base_score_corner(h),
    "衝刺": lambda h, remaining: base_score_sprint(h),
}


def simulate_race(
    horses: list[HorseRaceInput],
    distance_mod: float = 1.0,
    terrain_mod: float = 1.0,
) -> list[HorseRaceResult]:
    """模擬一整場比賽的六階段位置值與最終名次。

    對應 `數值平衡試算.xlsx`「比賽模擬」分頁的完整計算流程。
    """
    n = len(horses)
    ext_mult = {h.name: external_multiplier(h) for h in horses}
    remaining_stamina = {h.name: simulate_stamina(h, distance_mod, terrain_mod) for h in horses}

    results = {h.name: HorseRaceResult(name=h.name, stamina_remaining=remaining_stamina[h.name]) for h in horses}
    relative_so_far: dict[str, list[float]] = {h.name: [] for h in horses}

    for stage in RACE_STAGES:
        adjusted_scores: dict[str, float] = {}
        base_scores: dict[str, float] = {}
        for h in horses:
            base = _BASE_SCORE_FUNCS[stage](h, remaining_stamina[h.name])
            pace_mult = PACE_STAGE_MULTIPLIER[h.pace][stage]
            adjusted = base * ext_mult[h.name] * pace_mult
            base_scores[h.name] = base
            adjusted_scores[h.name] = adjusted

        field_average = sum(adjusted_scores.values()) / n

        for h in horses:
            relative = (adjusted_scores[h.name] - field_average) / field_average
            relative_so_far[h.name].append(relative)
            position_value = sum(relative_so_far[h.name]) / len(relative_so_far[h.name])
            results[h.name].stages.append(
                HorseStageResult(
                    stage=stage,
                    base_score=base_scores[h.name],
                    adjusted_score=adjusted_scores[h.name],
                    field_average=field_average,
                    relative_performance=relative,
                    position_value=position_value,
                )
            )

    for h in horses:
        results[h.name].final_position_value = results[h.name].stages[-1].position_value

    ranked = sorted(horses, key=lambda h: results[h.name].final_position_value, reverse=True)
    for rank, h in enumerate(ranked, start=1):
        results[h.name].rank = rank

    return [results[h.name] for h in horses]
