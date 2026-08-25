"""獸醫系統（docs/經營/員工系統.md「獸醫」)，依使用者2026/8/22決定從「先跳過」
清單補回MVP，跟傷病系統(cli/injuries.py)搭配使用。

MVP簡化：獸醫不像訓練師分専長類型，統一用單一技能等級(1~5)代表員工系統.md列的
「傷病診斷/恢復效率/傷病預防/健康評估精度/配種前後檢查」綜合能力——其中「配種前後
檢查」跟繁殖系統掛勾，MVP還沒有繁殖系統，先跳過；「健康評估精度」屬於資訊類，跟
訓練師的「潛力評估」專長一樣先跳過UI呈現差異的實作，只留「恢復效率」「傷病預防」
兩項真正影響數值(見 cli/injuries.py 的 vet_prevention_multiplier / recovery_weeks_per_tick)。

聘用/容量規則見 cli/injuries.py 模組docstring末段跟 MAX_HORSES_* 常數
（員工系統.md：「一個獸醫最佳照顧5隻馬匹，照顧6～8匹時治療效率下降，並無法
照顧9匹以上」）。
"""
from __future__ import annotations

import random
from dataclasses import dataclass

SKILL_LEVELS = (1, 2, 3, 4, 5)
_SURNAMES = ("周", "許", "鄭", "謝", "郭", "洪", "曾", "廖", "賴", "徐")


@dataclass
class Vet:
    name: str
    skill_level: int  # 1~5
    hire_fee: float
    weekly_salary: float


def hire_fee_for_level(level: int) -> float:
    return 1000.0 * level


def salary_for_level(level: int) -> float:
    return 250.0 * level


def generate_vet_market(count: int = 3) -> list["Vet"]:
    """隨機生成可聘用的獸醫清單（獸醫市場）。"""
    surnames = random.sample(_SURNAMES, k=min(count, len(_SURNAMES)))
    while len(surnames) < count:  # count > 姓氏數量時允許重複
        surnames.append(random.choice(_SURNAMES))

    market: list[Vet] = []
    for surname in surnames:
        level = random.choice(SKILL_LEVELS)
        market.append(
            Vet(
                name=f"{surname}獸醫",
                skill_level=level,
                hire_fee=hire_fee_for_level(level),
                weekly_salary=salary_for_level(level),
            )
        )
    return market
