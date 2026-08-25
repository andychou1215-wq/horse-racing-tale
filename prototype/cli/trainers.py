"""訓練師系統（docs/培育/訓練師系統.md），依使用者2026/8/22決定從「先跳過」清單補回MVP。

MVP簡化範圍（訓練師系統.md列了7種專長，這裡先做3種會直接影響數值計算的 + 1種影響
被動疲勞回復的，其餘2種先跳過）：
- 保留：速度訓練能力、耐力訓練能力、戰術能力（各自對應一項可訓練屬性的訓練加成）、
  狀態管理（額外提供每週被動疲勞回復加成，見 cli/game.py apply_weekly_passive_recovery）。
- 先跳過：幼駒培育（MVP裡馬匹全程「上升期」不跨成長階段，這個專長目前沒有意義）、
  傷病預防（MVP還沒有傷病系統，只有隨機事件清單.md簡化版的2項事件，等未來做傷病系統
  時再一起補這個專長的效果）、潛力評估（純資訊類專長，不影響數值，先跳過UI呈現差異，
  之後如果要做「潛力上限模糊化顯示」可以再回來接這個專長）。

聘用/委託管理（訓練師系統.md）：
- 訓練師市場隨機生成N名可聘用訓練師，各有專長+技能等級(1~5)，聘用要付一次性聘用費，
  之後每週固定支付薪水（見 cli/game.py weekly_upkeep）。
- 一個馬匹最多指定一個訓練師，一個訓練師最佳管理8匹馬；9~12匹時訓練效率打折
  （capacity_multiplier）；13匹以上不可再指定。
- 沒有指定訓練師的馬，訓練倍率維持1.0（等同MVP先前「固定1名訓練師、不做專長加成」
  的假設值，是這個系統補回前的預設行為，向下相容）。
"""
from __future__ import annotations

import random
from dataclasses import dataclass

# 對應數值加成的3種專長 + 1種疲勞回復專長。訓練師系統.md原文列了7種，另外3種
# （幼駒培育/傷病預防/潛力評估）見上方模組docstring的跳過理由。
SPECIALTIES = ("速度訓練", "耐力訓練", "戰術訓練", "狀態管理")

SPECIALTY_STAT_MAP = {
    "速度訓練": "速度",
    "耐力訓練": "耐力",
    "戰術訓練": "戰術",
}

SKILL_LEVELS = (1, 2, 3, 4, 5)

_SURNAMES = ("陳", "林", "黃", "張", "李", "王", "吳", "劉", "蔡", "楊")

MAX_HORSES_FULL_EFFICIENCY = 8   # 最佳管理數
MAX_HORSES_REDUCED_EFFICIENCY = 12  # 9~12匹效率下降的上限
CAPACITY_PENALTY_MULTIPLIER = 0.85  # 9~12匹時的訓練倍率折扣


@dataclass
class Trainer:
    name: str
    specialty: str
    skill_level: int  # 1~5
    hire_fee: float
    weekly_salary: float


def hire_fee_for_level(level: int) -> float:
    return 800.0 * level


def salary_for_level(level: int) -> float:
    return 200.0 * level


def generate_trainer_market(count: int = 4) -> list["Trainer"]:
    """隨機生成可聘用的訓練師清單（訓練師市場）。"""
    surnames = random.sample(_SURNAMES, k=min(count, len(_SURNAMES)))
    while len(surnames) < count:  # count > 姓氏數量時允許重複
        surnames.append(random.choice(_SURNAMES))

    market: list[Trainer] = []
    for surname in surnames:
        specialty = random.choice(SPECIALTIES)
        level = random.choice(SKILL_LEVELS)
        market.append(
            Trainer(
                name=f"{surname}教練",
                specialty=specialty,
                skill_level=level,
                hire_fee=hire_fee_for_level(level),
                weekly_salary=salary_for_level(level),
            )
        )
    return market


def training_multiplier(trainer: "Trainer | None", stat: str) -> float:
    """訓練師對指定訓練屬性的加成倍率。

    沒有指定訓練師，或訓練師專長跟這個屬性無關時回傳1.0（不加成也不懲罰）。
    有對應專長時，等級每高1級加8%（Lv1=1.08x ～ Lv5=1.40x）。
    """
    if trainer is None:
        return 1.0
    if SPECIALTY_STAT_MAP.get(trainer.specialty) == stat:
        return 1.0 + trainer.skill_level * 0.08
    return 1.0


def fatigue_relief_bonus(trainer: "Trainer | None") -> float:
    """「狀態管理」專長訓練師額外提供的每週被動疲勞回復加成（等級每高1級+1點）。"""
    if trainer is None or trainer.specialty != "狀態管理":
        return 0.0
    return float(trainer.skill_level)


def capacity_multiplier(horse_count: int) -> float:
    """一個訓練師同時管理的馬匹數對訓練效率的影響。

    訓練師系統.md：最佳管理8匹馬，管理9~12匹時訓練效率下降，13匹以上無法管理。
    """
    if horse_count <= MAX_HORSES_FULL_EFFICIENCY:
        return 1.0
    if horse_count <= MAX_HORSES_REDUCED_EFFICIENCY:
        return CAPACITY_PENALTY_MULTIPLIER
    raise ValueError(f"單一訓練師最多管理{MAX_HORSES_REDUCED_EFFICIENCY}匹馬，目前{horse_count}匹")


def can_assign(horse_count_excluding_target: int) -> bool:
    """指定馬匹給該訓練師前的容量檢查（不含正要指定的這匹）。"""
    return horse_count_excluding_target + 1 <= MAX_HORSES_REDUCED_EFFICIENCY
