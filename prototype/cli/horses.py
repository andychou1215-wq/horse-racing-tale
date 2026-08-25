"""馬匹資料模型與開局5匹固定測試馬（docs/MVP範圍.md「先跳過」拍賣/市場，
開局直接配發固定屬性測試馬）。"""
from __future__ import annotations

from dataclasses import dataclass, field

from .injuries import Injury

TRAINABLE_STATS = ("速度", "耐力", "加速", "力量", "根性", "起跑", "戰術", "智力", "彎道")
# MVP範圍.md 原本訓練選項只保留7項(速度/耐力/加速/力量/根性/起跑/戰術) + 休息，
# 跳過智力/彎道/精神/醫療/模擬賽。
#
# 2026/8/22 使用者決定：正式把智力、彎道也開放訓練(9項)，解決「11項屬性平均」評級
# 被凍結屬性拖累的問題——原本4項凍結屬性(智力/彎道/精神/健康)裡，智力/彎道通常是
# 影響彎道階段表現的重要屬性，卻永遠停在起始值，導致像「潛力新星」這種凍結屬性起始值
# 偏低的馬，評級天花板遠低於潛力上限本身(見 assumptions.py GI門檻調整依據)。開放後
# 只剩精神/健康2項維持凍結(先跳過醫療/模擬賽相關系統，這2項屬性沒有對應的訓練管道)。

ALL_STATS = (
    "速度", "耐力", "加速", "力量", "根性", "智力", "起跑", "彎道", "戰術", "精神", "健康",
)


@dataclass
class Horse:
    name: str
    stats: dict[str, float]
    potential_cap: float  # 單一整體潛力(0~100)，11項屬性共用
    pace: str  # 逃/先/差/追
    distance_affinity: str = "B"
    terrain_affinity: str = "B"
    fatigue: float = 0.0  # 疲勞值 0~100
    fame: float = 0.0
    money_earned: float = 0.0
    race_log: list[str] = field(default_factory=list)
    assigned_trainer: str | None = None  # 指定訓練師的名字（訓練師系統.md），None=無指定訓練師
    assigned_vet: str | None = None  # 指定獸醫的名字（員工系統.md「獸醫」），None=無指定獸醫
    injury: Injury | None = None  # 目前的傷病狀態（狀態與健康.md「傷病」），None=沒受傷
    retired: bool = False  # 重傷有機率直接退役（狀態與健康.md「最嚴重者可會導致馬匹立即退役」）
    recent_light_injury_week: int | None = None  # 最近一次輕傷發生的週次，供傷病嚴重度判定用
    race_cooldown_weeks_remaining: int = 0
    # 2026/8/23使用者決定：賽事從每4週一次改成每週一次，但馬匹出賽後接下來2週不可再
    # 參賽(賽事與生涯系統.md精神：避免無限連續出賽)。>0時代表還在冷卻中，can_race()會
    # 擋下報名；每週結算時倒數一週(見 cli/game.py apply_weekly_race_cooldown_recovery)。
    raced_this_week: bool = False
    # 同上，暫存「這週是否剛出賽過」，供本週傷病判定(roll_weekly_injuries)判斷要不要套用
    # 比賽週的額外傷病風險加成——只有真的出賽的馬才吃這個加成，不是恆常對全部馬匹生效。
    # 每週結算時會重置回False(跟上面的冷卻倒數同一個函式處理)。
    age: int = 2
    # 2026/8/23使用者決定新增馬匹年齡系統(對應GDD 3.6「成長與老化」)。開局5匹測試馬固定
    # 2歲(assumptions.py STARTER_HORSE_AGE)，符合doc「2歲可參加新馬賽」的前提，也讓開局
    # 就能報名新馬賽，不用額外等待。每滿WEEKS_PER_YEAR(52)週由 cli/game.py
    # apply_weekly_age_progression() 統一+1歲，退役馬不再累加。2026/8/23新增當下先只做
    # 「年齡數字+新馬賽資格判定」，不做doc 3.6完整的四種成長曲線類型/階段轉換對訓練倍率
    # 的影響；2026/8/24已補回完整版(見下方growth_curve欄位/cli/growth.py)。
    growth_curve: str = "一般"
    # 2026/8/24使用者決定補回doc 3.6完整版：早熟/一般/晚成/持久型4種成長曲線類型，決定
    # 這匹馬在哪些年齡進入上升期/巔峰期/停滯期/衰退期(見 cli/growth.py)，取代原本固定的
    # age_stage_multiplier=1.15。GDD明文「成長遺傳: 馬匹年齡成長類型不會遺傳」，所以只有
    # 開局5匹測試馬用固定指派(下方 starter_horses())，市場馬/foal一律用
    # growth.random_growth_curve() 獨立隨機決定，不參考父母。
    career_starts: int = 0
    # 生涯出賽次數(不分分級、不分名次，只要報名出賽過就+1，見 cli/game.py run_race)。
    # 新馬賽資格「從未參賽」用這個欄位判定：career_starts==0 才符合資格。
    graduated: bool = False
    # 是否已經「畢業」離開新馬賽/未勝利賽的資格限制、可以報名一般賽事(地方一般賽以上)。
    # 依使用者決定：在新馬賽或未勝利賽奪得第1名時觸發(cli/game.py run_race)，兩者只要
    # 贏一次就永久畢業，不會因為之後戰績不好被取消。畢業後這匹馬也不能再回頭報名新馬賽/
    # 未勝利賽(見 cli/game.py eligible_grades)，比照真實賽馬「條件戰」一去不回頭的精神。

    # ---- 血統與繁殖系統.md / 遺傳系統.md，2026/8/24使用者決定新增(簡化版) ----
    sex: str = "母"  # "公"/"母"，繁殖系統需要性別才能判定種馬(公)/繁殖母馬(母)角色
    sire_name: str | None = None  # 父親名字，None=沒有血統紀錄(開局測試馬/市場馬皆如此)
    dam_name: str | None = None   # 母親名字，同上
    # 註：血統只往上追蹤1代(父/母名字)，不建立完整多代血統樹——近親判定(見cli/breeding.py
    # _is_inbred)因此只能抓到「親子」「同父/同母的手足」這兩種情況，抓不到隔代或更遠親緣
    # 的近親繁殖，是這次簡化範圍刻意接受的限制。
    breeding_role: str | None = None
    # None/"種馬"/"繁殖母馬"。只有已退役、3~12歲、性別對應的馬才能登記(見
    # cli/game.py assign_breeding_role)，登記後才能被 breed() 選為配種對象。
    pregnant_weeks_remaining: int = 0  # >0 代表這匹母馬懷孕中，倒數至0時生產(見 cli/game.py apply_weekly_pregnancy_progression)
    pregnant_sire_name: str | None = None  # 懷孕當下記錄的父親名字
    pregnant_sire_stats: dict[str, float] | None = None
    pregnant_sire_potential_cap: float | None = None
    # 懷孕當下把種馬的屬性/潛力「拍照存證」下來，而不是留種馬名字之後臨時去查——避免種馬
    # 在懷孕期間被賣掉/屬性被訓練改變時，幼駒出生當下算不出來或算到錯誤的數值。
    pregnant_inbred: bool = False  # 懷孕當下(breed()呼叫時)就判定好是否近親繁殖，出生時直接讀這個旗標
    breeding_cooldown_weeks_remaining: int = 0
    # 配種嘗試之間的恢復期(簡化版「一年最多4次配種嘗試」+「規律平靜作息」精神的近似值，
    # 不做21~22天發情週期倒數，見 cli/game.py breed())。
    pregnant_sire_traits: list[str] | None = None
    pregnant_sire_personality: str | None = None
    # 跟pregnant_sire_stats同一套「拍照存證」精神，懷孕當下記錄種馬的特性/性格快照，
    # 供出生時 cli/traits.py inherit_traits()/inherit_personality() 使用(2026/8/24
    # 新增特性/性格系統時補上，見下方 traits/personality 欄位)。

    # ---- 馬匹系統.md「個性」「特性」/ 遺傳系統.md「特性遺傳」「性格遺傳」，
    # 2026/8/24使用者決定新增(簡化版：全部天生隨機分配，性格純風味不掛數值效果) ----
    traits: list[str] = field(default_factory=list)
    # 最多2個(見cli/traits.py MAX_TRAITS)，出生/生成當下隨機決定(cli/traits.py
    # random_traits())或配種遺傳(inherit_traits())，比賽當下依cli/traits.py
    # race_trait_bonus_pct()換算成engine/race.py HorseRaceInput.trait_bonus_pct。
    personality: str | None = None
    # 最多1個，None代表沒有明顯個性。純風味欄位，不影響任何訓練/比賽數值(比賽公式.md、
    # 培育系統.md都沒有引用性格，文件本身沒有給具體公式，使用者決定這次不額外自訂效果)。

    def overall_rating(self) -> float:
        """簡化版評級：11項屬性平均，用於決定可報名的賽事分級門檻。"""
        return sum(self.stats.values()) / len(self.stats)

    def growth_room(self) -> float:
        return self.potential_cap - self.overall_rating()

    def can_race(self) -> bool:
        return self.injury is None and not self.retired and self.race_cooldown_weeks_remaining <= 0

    def can_train(self) -> bool:
        """馬匹成長.md：「1歲可以開始訓練」，2026/8/24新增繁殖系統後幼駒可能從0歲開始，
        需要這個門檻擋下還沒滿1歲的幼駒（開局測試馬/市場馬固定2歲起跳，不受影響）。"""
        from . import assumptions as A

        return self.age >= A.MIN_TRAINING_AGE

    def growth_stage(self) -> str:
        """這匹馬目前所屬的成長階段(上升期/巔峰期/停滯期/衰退期)，見 cli/growth.py。"""
        from . import growth as G

        return G.growth_stage(self.growth_curve, self.age)


def starter_horses() -> list[Horse]:
    """開局固定配發的5匹測試馬（屬性沿用 數值平衡試算.xlsx 測試馬設定）。"""
    return [
        Horse(
            name="全能強馬",
            stats={
                "速度": 82, "耐力": 78, "加速": 80, "力量": 75, "根性": 78,
                "智力": 72, "起跑": 76, "彎道": 74, "戰術": 70, "精神": 75, "健康": 80,
            },
            potential_cap=88,
            pace="逃",
            distance_affinity="A",
            terrain_affinity="A",
            sex="公",
            growth_curve="一般",
            traits=["快速起步", "末段爆發"],
            personality="好勝",
        ),
        Horse(
            name="速度型快馬",
            stats={
                "速度": 90, "耐力": 55, "加速": 85, "力量": 60, "根性": 50,
                "智力": 60, "起跑": 82, "彎道": 55, "戰術": 60, "精神": 55, "健康": 70,
            },
            potential_cap=93,  # 需 >= 現有最高屬性(速度90)，否則訓練會把數值往下拉齊潛力上限
            pace="逃",
            distance_affinity="B",
            terrain_affinity="B",
            sex="母",
            growth_curve="早熟",
            traits=["領放穩定", "快速起步"],  # pace="逃"，領放穩定正好吃得到觸發條件
            personality="喜歡領跑",
        ),
        Horse(
            name="耐力追込馬",
            stats={
                "速度": 60, "耐力": 88, "加速": 55, "力量": 65, "根性": 82,
                "智力": 65, "起跑": 55, "彎道": 60, "戰術": 65, "精神": 70, "健康": 75,
            },
            potential_cap=91,  # 需 >= 現有最高屬性(耐力88)
            pace="追",
            distance_affinity="A",
            terrain_affinity="B",
            sex="公",
            growth_curve="持久型",
            traits=["末段爆發"],
            personality="冷靜",
        ),
        Horse(
            name="平衡中庸馬",
            stats={
                "速度": 65, "耐力": 65, "加速": 65, "力量": 65, "根性": 65,
                "智力": 65, "起跑": 65, "彎道": 65, "戰術": 65, "精神": 65, "健康": 65,
            },
            potential_cap=78,
            pace="先",
            distance_affinity="B",
            terrain_affinity="B",
            sex="母",
            growth_curve="一般",
            traits=[],  # 刻意留空，作為「平凡基準馬」的對照組
            personality="慢熱",  # 性格的「慢熱」跟特性池裡的「慢熱」是獨立欄位，見cli/traits.py說明
        ),
        Horse(
            name="潛力新星",
            stats={
                "速度": 45, "耐力": 42, "加速": 48, "力量": 40, "根性": 44,
                "智力": 58, "起跑": 42, "彎道": 60, "戰術": 45, "精神": 62, "健康": 70,
            },
            # 潛力高、目前能力低，是「賭黑馬」的樣板。
            # 調整依據：智力/彎道曾是凍結屬性時，牠偏低的起始值(40/40)會把評級天花板拖到
            # 遠低於潛力上限92(見 assumptions.py GI門檻調整依據)。智力/彎道開放訓練後這個
            # 問題已從根本解決；這裡保留當時調高過的起始值(智力58/彎道60)，作為「未打磨但
            # 底子不差」的黑馬起點，精神62/健康70兩項仍是目前僅剩的凍結屬性起始值。
            potential_cap=92,
            pace="差",
            distance_affinity="C",
            terrain_affinity="C",
            sex="母",
            growth_curve="晚成",  # 「賭黑馬」樣板搭配晚成型：起步慢、後段才會轉強
            traits=["容易緊張"],  # 未打磨的黑馬也帶點負面特性，不是純數值上的贏家
            personality="膽小",
        ),
    ]
