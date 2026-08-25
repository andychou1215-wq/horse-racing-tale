"""馬匹成長曲線與階段轉換（docs/馬匹/馬匹成長.md，2026/8/24從「先跳過」清單補回GDD 3.6
完整版本，取代原本固定的 assumptions.FIXED_AGE_STAGE_MULTIPLIER=1.15）。

4種成長曲線類型(早熟/一般/晚成/持久型)，各自在不同年齡進入上升期/巔峰期/停滯期/衰退期，
對應不同的訓練成長倍率；除智力/精神外的9項屬性進入衰退期後，會隨每週緩慢衰退
(可透過恢復中心設施、獸醫照護減緩，但無法完全消除——見 facilities.decline_mitigation_for_level)。

GDD明文規定「成長遺傳: 馬匹年齡成長類型不會遺傳」，所以foal/市場馬的growth_curve一律
獨立隨機決定，不會參考父母。
"""
from __future__ import annotations

import random

GROWTH_CURVE_TYPES = ("早熟", "一般", "晚成", "持久型")

# {成長曲線類型: {階段: (起始年齡, 結束年齡；None代表此後所有年齡都維持這個階段)}}
# 對照 docs/馬匹/馬匹成長.md 的四種類型階段表。
STAGE_AGE_TABLE: dict[str, dict[str, tuple[int, int | None]]] = {
    "早熟":   {"上升期": (2, 2), "巔峰期": (3, 3), "停滯期": (4, 4), "衰退期": (5, None)},
    "一般":   {"上升期": (2, 3), "巔峰期": (4, 4), "停滯期": (5, 5), "衰退期": (6, None)},
    "晚成":   {"上升期": (2, 4), "巔峰期": (5, 5), "停滯期": (6, 6), "衰退期": (7, None)},
    "持久型": {"上升期": (2, 3), "巔峰期": (4, 5), "停滯期": (6, 7), "衰退期": (8, None)},
}

# 各階段對訓練/比賽經驗成長的倍率。上升期/巔峰期沿用MVP原本FIXED_AGE_STAGE_MULTIPLIER=1.15
# 開局馬(2~3歲)的手感；停滯期/衰退期倍率是這次新增、doc只定性沒定量，屬MVP假設值。
STAGE_MULTIPLIER = {
    "上升期": 1.15,
    "巔峰期": 1.00,
    "停滯期": 0.6,
    "衰退期": 0.3,
}

DECLINE_EXEMPT_STATS = ("智力", "精神")  # 進入衰退期後，這2項不受週衰退影響(視為經驗/心理素質，不隨體能衰退)
DECLINE_BASE_RATE_MIN = 0.003  # 每週衰退基礎值：doc定為0.3%~0.5%
DECLINE_BASE_RATE_MAX = 0.005


def growth_stage(growth_curve: str, age: int) -> str:
    """回傳指定成長曲線類型的馬匹在這個年齡屬於哪個階段。

    doc的階段表格從2歲開始定義；0~1歲(幼駒/尚不能出賽的幼馬)簡化統一視為「上升期」，
    不另外切一個「幼年期」出來，維持補回本機制前的訓練手感。
    """
    if age < 2:
        return "上升期"
    for stage, (start, end) in STAGE_AGE_TABLE[growth_curve].items():
        if age >= start and (end is None or age <= end):
            return stage
    return "衰退期"  # 防呆：理論上表格已涵蓋2歲以上所有年齡，不會走到這裡


def age_stage_multiplier(growth_curve: str, age: int) -> float:
    """train_horse()/apply_race_experience_growth() 用的動態版
    age_stage_multiplier，取代原本的固定常數。"""
    return STAGE_MULTIPLIER[growth_stage(growth_curve, age)]


def random_growth_curve() -> str:
    """給市場馬/foal使用的隨機成長曲線指派(GDD:「馬匹年齡成長類型不會遺傳」)。"""
    return random.choice(GROWTH_CURVE_TYPES)


def individual_decline_factor(guts: float, health: float) -> float:
    """依馬匹個體差異(根性/健康)換算衰退速率的個體浮動係數。

    doc只說「具體衰退率依馬匹個體差異(如根性、健康)浮動」，沒有給公式，這是MVP假設值：
    以根性/健康的平均分(0~100)線性換算到0.7~1.3倍——底子越好(平均分越高)衰退越慢
    (最低可打7折)，底子越差衰退越快(最高加重3成)。
    """
    avg = (guts + health) / 2
    return 1.3 - (avg / 100.0) * 0.6


def weekly_decline_rate(guts: float, health: float, facility_mitigation: float = 1.0) -> float:
    """單一屬性本週的衰退比例 = 隨機基礎值(0.3%~0.5%) x 個體差異係數 x 設施/照護減緩係數。

    facility_mitigation 是 <=1.0 的倍率(見 facilities.decline_mitigation_for_level)，
    代表恢復中心等設施可以「減緩」衰退但doc明文「無法完全消除」，所以這裡刻意不允許減緩
    到0。
    """
    base_rate = random.uniform(DECLINE_BASE_RATE_MIN, DECLINE_BASE_RATE_MAX)
    return base_rate * individual_decline_factor(guts, health) * facility_mitigation
