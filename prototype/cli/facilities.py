"""設施系統（docs/經營/設施系統.md），依使用者決定從「簡化」清單補回MVP。

MVP範圍.md原本假設「訓練場固定Lv2，不開放升級，先驗證訓練公式而非經營深度」，
`FIXED_FACILITY_MULTIPLIER=1.1`(對應Lv2)套用在所有訓練屬性。這裡補回可升級版本，
刻意向下相容：所有設施開局都是Lv2，`training_multiplier_for_level(2)` 算出來
剛好等於原本的1.1，玩家不升級的話效果完全不變。

docs列了8種設施(馬房/5種屬性訓練場/恢復中心/醫療中心/育馬場/海外馬房)，一開始MVP先
只做7種真正跟現有可訓練屬性/恢復機制對應的：

- 速度訓練場：加成 速度、加速
- 耐力訓練場：加成 耐力
- 力量訓練場：加成 力量
- 根性訓練場：加成 根性
- 跑道訓練場：加成 智力、起跑、彎道、戰術
- 恢復中心：加成每週被動疲勞回復(疊加訓練師「狀態管理」專長的效果)
- 醫療中心：加成傷病恢復速度(疊加獸醫「恢復效率」的效果)

2026/8/25使用者決定補上剩下3種容量型設施(馬房/育馬場/海外馬房)：跟上面7種共用同一套
`facility_levels`/`upgrade_cost()`升級機制(等級1~5、Lv2預設、升級費用曲線完全相同)，
差別只在「效果」從訓練倍率/回復加成換成「容量」：

- 馬房：容量上限=同時能放在馬房裡的馬匹總數(不分現役/退役)，見`stable_capacity_
  for_level()`，`cli/game.py buy_horse()`/`_buy_breeding_stock()`(涵蓋buy_foal/
  buy_stallion/buy_broodmare)購買前會檔查容量，滿了就擋下購買。配種生出的幼駒不受
  這個上限管制——已登記的母馬懷孕後正常生產，只是生完後馬房可能超過容量，需要玩家
  之後自行處理(賣馬/淘汰)，不會擋下正在進行中的配種週期。
- 育馬場：容量上限=同時能登記為「種馬」或「繁殖母馬」的馬匹總數，見`stud_farm_
  capacity_for_level()`，`cli/game.py assign_breeding_role()`跟`_buy_breeding_
  stock()`(買種馬/繁殖母馬市場馬時會直接帶著登記好的角色)購買/登記前都會檢查。
- 海外馬房：容量上限見`overseas_stable_capacity_for_level()`，可以正常升級/顯示
  容量數字，但海外賽事系統本身MVP範圍還沒做(先跳過清單)，所以這個設施目前是「沉睡」
  狀態——沒有任何馬匹會真的被送進海外馬房佔用容量，等海外賽事系統之後補上才會有實際
  用途(比照特性系統裡重馬場高手/海外適應這2個特性的先例)。

升級是一次性資本支出(沒有像訓練師/獸醫那樣的持續週薪)，等級越高升級費越貴，
跟訓練師/獸醫的「持續薪水」形成不同的投資型態對照。
"""
from __future__ import annotations

MIN_LEVEL = 1
MAX_LEVEL = 5
DEFAULT_LEVEL = 2  # MVP範圍.md 原本的固定假設值，向下相容的起始等級

FACILITY_TYPES = (
    "速度訓練場",
    "耐力訓練場",
    "力量訓練場",
    "根性訓練場",
    "跑道訓練場",
    "恢復中心",
    "醫療中心",
    "馬房",
    "育馬場",
    "海外馬房",
)

FACILITY_STAT_MAP = {
    "速度訓練場": ("速度", "加速"),
    "耐力訓練場": ("耐力",),
    "力量訓練場": ("力量",),
    "根性訓練場": ("根性",),
    "跑道訓練場": ("智力", "起跑", "彎道", "戰術"),
}

UPGRADE_BASE_COST = 8000.0


def default_facility_levels() -> dict[str, int]:
    return {f: DEFAULT_LEVEL for f in FACILITY_TYPES}


def training_multiplier_for_level(level: int) -> float:
    """設施等級對訓練效率的加成倍率。Lv2(預設值)=1.1，對齊這個系統補回前的固定假設值。"""
    return 1.0 + (level - 1) * 0.1


def fatigue_relief_bonus_for_level(level: int) -> float:
    """恢復中心等級對每週被動疲勞回復的額外加成，Lv2(預設)以上才有效果。"""
    return max(0, level - DEFAULT_LEVEL) * 1.0


def injury_recovery_bonus_for_level(level: int) -> int:
    """醫療中心等級對傷病恢復的額外週數加成，Lv2(預設)以上才有效果。"""
    return max(0, level - DEFAULT_LEVEL)


def decline_mitigation_for_level(level: int) -> float:
    """恢復中心等級對衰退期屬性週衰退速度的減緩倍率(2026/8/24隨成長曲線系統補上)。

    docs/馬匹/馬匹成長.md:「可透過設施(恢復中心)、獸醫照護、降低比賽/訓練強度來減緩
    衰退速度，但無法完全消除」——這裡只做「設施」這一個減緩管道，「獸醫照護」與
    「降低比賽/訓練強度」先跳過(獸醫目前的「恢復效率」專長只影響傷病恢復，還沒有
    對應衰退期的效果；訓練強度目前也沒有可調整的檔位)，之後有需要再補。

    Lv2(預設)以上每高一級再減緩衰退速率10%(乘法疊加)：Lv2=1.0(無減緩)、
    Lv5=0.9**3≈0.73(減緩約27%)。不管等級多高都不會讓倍率變成0，對應「無法完全消除」。
    """
    extra_levels = max(0, level - DEFAULT_LEVEL)
    return 0.9 ** extra_levels


STABLE_CAPACITY_BY_LEVEL = {1: 10, 2: 20, 3: 30, 4: 40, 5: 50}  # 設施系統.md「馬房」原文數字
STUD_FARM_CAPACITY_BY_LEVEL = {1: 10, 2: 20, 3: 30, 4: 40, 5: 50}  # 設施系統.md「育馬場」原文數字
OVERSEAS_STABLE_CAPACITY_BY_LEVEL = {1: 5, 2: 10, 3: 15, 4: 20, 5: 25}  # 設施系統.md「海外馬房」原文數字


def stable_capacity_for_level(level: int) -> int:
    """馬房容量上限(同時能放在馬房裡的馬匹總數，不分現役/退役)。"""
    return STABLE_CAPACITY_BY_LEVEL[level]


def stud_farm_capacity_for_level(level: int) -> int:
    """育馬場容量上限(同時能登記為種馬/繁殖母馬的馬匹總數)。"""
    return STUD_FARM_CAPACITY_BY_LEVEL[level]


def overseas_stable_capacity_for_level(level: int) -> int:
    """海外馬房容量上限。海外賽事系統MVP還沒做，這個設施目前沉睡，見模組docstring。"""
    return OVERSEAS_STABLE_CAPACITY_BY_LEVEL[level]


def upgrade_cost(current_level: int) -> float:
    """從 current_level 升到 current_level+1 的費用，等級越高費用越貴。"""
    if current_level >= MAX_LEVEL:
        raise ValueError(f"已經是最高等級(Lv{MAX_LEVEL})，無法再升級")
    return UPGRADE_BASE_COST * current_level


def stat_facility(stat: str) -> str | None:
    """回傳影響指定可訓練屬性的設施類型名稱；沒有對應設施時回傳None。"""
    for facility, stats in FACILITY_STAT_MAP.items():
        if stat in stats:
            return facility
    return None
