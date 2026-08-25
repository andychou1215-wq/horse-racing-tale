"""傷病系統（docs/馬匹/狀態與健康.md「傷病風險」「傷病」「養傷」)，
依使用者2026/8/22決定從「先跳過」清單補回MVP。

依使用者要求，傷病種類與嚴重度參考現實賽馬常見的訓練/比賽耗損型傷病案例（下面只取
通俗名稱與大致恢復期/永久性後果的量級，不追求醫學精確，純供遊戲數值設計參考，
不是醫療資訊）：

- **輕傷**（肌肉拉傷、副骨突起/俗稱夾骨、輕微關節發炎）：賽馬訓練/比賽最常見的
  耗損型小傷，現實中通常休養1~3週即可回歸，不留永久後遺症。但短期內反覆發生會被
  視為體質警訊(狀態與健康.md：「持續性的輕傷可能提升傷病嚴重度」)，這裡簡化成：
  4週內再次觸發傷病判定時，中/重傷的機率會提高。
- **中傷**（脛骨骨膜炎/俗稱buck shins，年輕馬常見、韌帶扭傷、蹄葉炎初期）：恢復期
  拉長到4~8週，依受傷部位對應影響的屬性會有一次性小幅永久減損(3%)——例如脛骨/
  韌帶相關的腿部傷病影響速度/加速/彎道，蹄葉炎影響耐力/起跑。
- **重傷**（屈腱炎/俗稱肌腱部分斷裂、懸韌帶損傷、疲勞性骨折）：現實中賽馬最常見
  也最忌憚的重大傷病，屈腱炎尤其以高復發率跟長期(常需數月)恢復期聞名，疲勞性骨折
  則是高強度訓練/比賽頻率下的常見累積傷。對應遊戲內12~20週的長期停賽，永久減損
  幅度較大(8%)，且有機率直接迫使退役——對應現實中嚴重肌腱/骨折傷病經常導致提早
  退役的案例。

養傷/獸醫規則(狀態與健康.md、經營/員工系統.md)：休養期間傷病週數會自動倒數，
指定獸醫可以加速恢復、也能降低下次觸發傷病的機率；沒有指定獸醫時仍會照基礎速度
自然恢復，向下相容(不強迫玩家一定要聘獸醫才能玩)。
"""
from __future__ import annotations

import random
from dataclasses import dataclass

SEVERITIES = ("輕傷", "中傷", "重傷")

INJURY_TYPES: dict[str, list[dict]] = {
    "輕傷": [
        {"name": "肌肉拉傷", "affected_stats": ()},
        {"name": "副骨突起(夾骨)", "affected_stats": ()},
        {"name": "輕微關節發炎", "affected_stats": ()},
    ],
    "中傷": [
        {"name": "脛骨骨膜炎(buck shins)", "affected_stats": ("速度", "加速", "彎道")},
        {"name": "韌帶扭傷", "affected_stats": ("速度", "彎道")},
        {"name": "蹄葉炎(初期)", "affected_stats": ("耐力", "起跑")},
    ],
    "重傷": [
        {"name": "屈腱炎(肌腱部分斷裂)", "affected_stats": ("速度", "加速", "力量")},
        {"name": "懸韌帶損傷", "affected_stats": ("彎道", "起跑", "戰術")},
        {"name": "疲勞性骨折", "affected_stats": ("耐力", "根性", "力量")},
    ],
}

SEVERITY_RECOVERY_WEEKS = {"輕傷": (1, 3), "中傷": (4, 8), "重傷": (12, 20)}
SEVERITY_PERMANENT_PENALTY_PCT = {"輕傷": 0.0, "中傷": 0.03, "重傷": 0.08}
SEVERITY_RETIREMENT_CHANCE = {"輕傷": 0.0, "中傷": 0.0, "重傷": 0.08}

# 傷病風險分級（狀態與健康.md：「疲勞+健康+訓練強度+比賽頻率」決定分級。MVP簡化
# 只用健康+疲勞換算——疲勞本身就是訓練/比賽強度的累積結果，可視為代理指標，
# 不用再獨立追蹤「訓練強度」「比賽頻率」兩個額外狀態，跟 assumptions.py 的
# state_score() 簡化精神一致）。
INJURY_RISK_TIERS = ("無", "低", "中", "高")
INJURY_BASE_CHANCE_BY_TIER = {"無": 0.01, "低": 0.03, "中": 0.06, "高": 0.12}
INJURY_RACE_WEEK_BONUS = 0.02  # 比賽週高強度活動，額外提高觸發機率

RECENT_LIGHT_INJURY_WINDOW_WEEKS = 4
SEVERITY_WEIGHTS_BASE = {"輕傷": 70, "中傷": 25, "重傷": 5}
SEVERITY_WEIGHTS_AFTER_RECENT_LIGHT_INJURY = {"輕傷": 50, "中傷": 35, "重傷": 15}

# 獸醫容量（經營/員工系統.md：「一個獸醫最佳照顧5隻馬匹，照顧6～8匹時治療效率
# 下降，並無法照顧9匹以上」）。
MAX_HORSES_FULL_EFFICIENCY = 5
MAX_HORSES_REDUCED_EFFICIENCY = 8
CAPACITY_PENALTY_MULTIPLIER = 0.85


@dataclass
class Injury:
    name: str
    severity: str  # "輕傷" | "中傷" | "重傷"
    weeks_remaining: int
    affected_stats: tuple[str, ...]


def injury_risk_score(health: float, fatigue: float) -> float:
    return (100 - health) * 0.6 + fatigue * 0.4


def injury_risk_tier(health: float, fatigue: float) -> str:
    score = injury_risk_score(health, fatigue)
    if score < 20:
        return "無"
    if score < 40:
        return "低"
    if score < 65:
        return "中"
    return "高"


def vet_prevention_multiplier(vet) -> float:
    """獸醫「傷病預防」項目：降低傷病觸發機率，等級每高1級再降10%(乘法疊加)。"""
    if vet is None:
        return 1.0
    return max(0.0, 1.0 - vet.skill_level * 0.10)


def roll_injury(
    health: float,
    fatigue: float,
    is_racing_this_week: bool,
    recent_light_injury: bool,
    vet=None,
) -> Injury | None:
    """判定本週是否觸發新傷病，回傳 Injury 或 None（沒觸發）。"""
    tier = injury_risk_tier(health, fatigue)
    chance = INJURY_BASE_CHANCE_BY_TIER[tier]
    if is_racing_this_week:
        chance += INJURY_RACE_WEEK_BONUS
    chance *= vet_prevention_multiplier(vet)

    if random.random() >= chance:
        return None

    weights = (
        SEVERITY_WEIGHTS_AFTER_RECENT_LIGHT_INJURY if recent_light_injury else SEVERITY_WEIGHTS_BASE
    )
    severity = random.choices(list(weights.keys()), weights=list(weights.values()), k=1)[0]
    injury_type = random.choice(INJURY_TYPES[severity])
    low, high = SEVERITY_RECOVERY_WEEKS[severity]
    weeks = random.randint(low, high)
    return Injury(
        name=injury_type["name"],
        severity=severity,
        weeks_remaining=weeks,
        affected_stats=injury_type["affected_stats"],
    )


def recovery_weeks_per_tick(vet=None, assigned_horse_count: int = 0) -> int:
    """每週結算養傷時，傷病剩餘週數倒數的量。獸醫「恢復效率」項目：等級每高2級
    多恢復1週；照顧馬匹數超過最佳容量時，這個額外加成打折(基礎1週不受影響)。
    """
    if vet is None:
        return 1
    bonus = vet.skill_level // 2
    if assigned_horse_count > MAX_HORSES_FULL_EFFICIENCY:
        bonus = int(bonus * capacity_multiplier(assigned_horse_count))
    return 1 + bonus


def capacity_multiplier(horse_count: int) -> float:
    if horse_count <= MAX_HORSES_FULL_EFFICIENCY:
        return 1.0
    if horse_count <= MAX_HORSES_REDUCED_EFFICIENCY:
        return CAPACITY_PENALTY_MULTIPLIER
    raise ValueError(f"單一獸醫最多照顧{MAX_HORSES_REDUCED_EFFICIENCY}匹馬，目前{horse_count}匹")


def can_assign(horse_count_excluding_target: int) -> bool:
    return horse_count_excluding_target + 1 <= MAX_HORSES_REDUCED_EFFICIENCY
