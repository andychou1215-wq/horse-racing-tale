"""特性/性格系統（docs/馬匹/馬匹系統.md「個性」「特性」、docs/繁殖/遺傳系統.md「特性
遺傳」「性格遺傳」簡化版，2026/8/24使用者決定新增）。

開工前先跟使用者確認過2個範圍問題(比照第12步現役馬市場、第13步繁殖系統的做法)：

1. **特性取得方式**：馬匹系統.md 9種特性各自標記「天生」「訓練」或「天生/訓練」三種
   取得管道其中之一。使用者選擇**簡化版**：不分天生/訓練，9種特性統一在馬匹出生/生成
   當下隨機分配(0~2個，見MAX_TRAITS)，包含文件寫「訓練」限定的領放穩定/抗壓也一併
   開放進天生隨機池——如果堅持照文件只能靠訓練取得，這次沒有做「透過特定訓練機率習得」
   的機制，這2個特性就會永遠不會出現。之後如果要做「訓練習得」可以再加，不影響這裡的
   資料結構(Horse.traits 就是最終的特性清單，不管是怎麼「拿到」的)。
2. **個性(性格)**：使用者選擇**純風味**，不掛任何數值效果——比賽公式.md、培育系統.md
   都沒有引用性格，文件本身也沒有給具體公式。這裡只做顯示欄位 + 遺傳系統.md「部分性格
   會受父母影響，如冷靜、暴躁等，且性格也不會完全受父母影響」的簡化版遺傳規則，不影響
   任何訓練/比賽數值。

特性效果強度：文件「±5%~8%，依特性稀有度浮動」，這裡簡化不分稀有度，統一在
TRAIT_EFFECT_PCT_MIN~MAX(5%~8%)之間均勻隨機。

比賽公式.md的「特性」是跟騎師修正/距離適性同一層級、全場次適用一次的外部乘數項
(engine/race.py external_multiplier()裡的trait_bonus_pct，套用在所有六階段，不是
逐階段套用)——這跟馬匹系統.md文字描述的「每個特性觸發時對『所屬階段』表現修正」字面上
不完全一致，但數值平衡試算.xlsx「比賽模擬」分頁本身就是把特性算成單一全場次百分比套進
外部乘數，既有22個核心引擎測試都是照這個公式比對到1e-9精度，這裡刻意不改動
engine/race.py：每匹馬賽前把「這場比賽會觸發的特性」加總成一個trait_bonus_pct
(race_trait_bonus_pct())，傳進HorseRaceInput，維持引擎既有算法完全不變。

「重馬場高手」「海外適應」這兩個特性依賴的系統(場地狀況變化、海外賽事)目前都還沒做
(MVP範圍.md先跳過清單)，這裡照樣正常生成/遺傳，只是trait_triggers()在目前MVP範圍內
永遠回傳False(固定良好場地、沒有海外賽事)，等對應系統之後補上就會自動生效，不用改
這個模組本身。
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class TraitDef:
    name: str
    kind: str  # "正面"/"負面"
    trigger_desc: str  # 觸發條件的敘述文字，UI顯示用
    heritable: str  # "是"/"否"/"可能"（遺傳系統.md「特性遺傳」用）


TRAIT_DEFS: dict[str, TraitDef] = {
    "快速起步": TraitDef("快速起步", "正面", "起跑階段（每場比賽恆常觸發）", "是"),
    "彎道巧手": TraitDef("彎道巧手", "正面", "彎道階段（每場比賽恆常觸發）", "是"),
    "重馬場高手": TraitDef("重馬場高手", "正面", "重馬場（MVP固定良好場地，目前不會觸發）", "可能"),
    "末段爆發": TraitDef("末段爆發", "正面", "最後衝刺（每場比賽恆常觸發）", "是"),
    "領放穩定": TraitDef("領放穩定", "正面", "起跑/前段，限「逃」跑法", "否"),
    "抗壓": TraitDef("抗壓", "正面", "地方三級賽以上/國際賽事", "否"),
    "海外適應": TraitDef("海外適應", "正面", "海外賽事（MVP尚未實作，目前不會觸發）", "是"),
    "容易緊張": TraitDef("容易緊張", "負面", "地方三級賽以上/國際賽事", "可能"),
    "慢熱": TraitDef("慢熱", "負面", "起跑/前段（每場比賽恆常觸發）", "可能"),
}
TRAIT_NAMES = tuple(TRAIT_DEFS)

MAX_TRAITS = 2
TRAIT_EFFECT_PCT_MIN = 0.05
TRAIT_EFFECT_PCT_MAX = 0.08

# 馬匹出生/生成時擁有0/1/2個特性的機率分布，文件沒有給具體數字，這是MVP假設值：
# 大部分馬匹平凡(0個)、部分有亮點(1個)、少數是「多特性好馬」(2個，MAX_TRAITS上限)。
TRAIT_COUNT_WEIGHTS = {0: 0.45, 1: 0.40, 2: 0.15}

# 遺傳系統.md「部分父母的特性將會影響子代，讓子代在訓練時比較容易獲取該特性」——這次
# 簡化版沒有「訓練習得」管道可以掛「比較容易獲取」，改成直接的機率直接遺傳，依
# TRAIT_DEFS.heritable分級：「是」機率較高、「可能」機率較低、「否」(領放穩定/抗壓，
# 本來就不是天生特性)完全不遺傳，呼應遺傳系統.md沒有把這兩個特性算進討論範圍。
TRAIT_INHERIT_CHANCE = {"是": 0.35, "可能": 0.15, "否": 0.0}
# 遺傳沒選滿MAX_TRAITS的部分，保留一點機率讓幼駒額外隨機長出全新特性(比照天生隨機池的
# 精神，避免「父母沒有特性=子代不可能有特性」過度決定論)。
TRAIT_EXTRA_RANDOM_CHANCE = 0.3

HIGH_TIER_GRADES = ("地方三級賽", "地方二級賽", "地方一級賽", "國際GIII", "國際GII", "國際GI")
# 抗壓/容易緊張的「高層級賽事」門檻，比照GDD 6.5聯盟積分「只有地方三級賽以上與國際賽事
# 產生積分」的同一個定義，沒有另外新造一套門檻。

PERSONALITY_TYPES = ("膽小", "好勝", "冷靜", "暴躁", "慢熱", "喜歡領跑", "不喜歡被包圍")
# 註：性格池裡的「慢熱」跟TRAIT_DEFS裡的負面特性「慢熱」是文件本身在兩處分別列出的
# 重疊用詞，彼此是獨立欄位(Horse.personality vs Horse.traits)，不互相影響、不互相排除。
PERSONALITY_NONE_CHANCE = 0.2  # 「一匹馬最多1個個性」暗示也可能0個，MVP假設2成馬沒有明顯個性
PERSONALITY_HERITABLE = ("冷靜", "暴躁")  # 遺傳系統.md「如冷靜、暴躁等」明確舉例的可遺傳性格
PERSONALITY_INHERIT_CHANCE = 0.3  # 父母任一方有上述可遺傳性格時，子代直接繼承其中之一的機率


def _weighted_trait_count() -> int:
    counts = list(TRAIT_COUNT_WEIGHTS.keys())
    weights = list(TRAIT_COUNT_WEIGHTS.values())
    return random.choices(counts, weights=weights, k=1)[0]


def random_traits() -> list[str]:
    """馬匹出生/生成當下隨機決定的特性清單(0~2個，見TRAIT_COUNT_WEIGHTS)。"""
    count = _weighted_trait_count()
    return random.sample(TRAIT_NAMES, k=count) if count else []


def inherit_traits(sire_traits: list[str], dam_traits: list[str]) -> list[str]:
    """配種生出的幼駒的特性清單：父母特性池依遺傳機率各自判定是否直接遺傳，
    沒遺傳滿MAX_TRAITS的部分保留一點機率額外隨機補上全新特性。"""
    pool = list(dict.fromkeys(sire_traits + dam_traits))  # 去重、保留順序
    inherited = [t for t in pool if random.random() < TRAIT_INHERIT_CHANCE[TRAIT_DEFS[t].heritable]]
    random.shuffle(inherited)
    inherited = inherited[:MAX_TRAITS]
    if len(inherited) < MAX_TRAITS and random.random() < TRAIT_EXTRA_RANDOM_CHANCE:
        extra_pool = [t for t in TRAIT_NAMES if t not in inherited]
        inherited.append(random.choice(extra_pool))
    return inherited


def random_personality() -> str | None:
    """馬匹出生/生成當下隨機決定的性格(可能是None，代表沒有明顯個性)。"""
    if random.random() < PERSONALITY_NONE_CHANCE:
        return None
    return random.choice(PERSONALITY_TYPES)


def inherit_personality(sire_personality: str | None, dam_personality: str | None) -> str | None:
    """配種生出的幼駒的性格：父母任一方帶有PERSONALITY_HERITABLE裡的性格時，有機率
    直接繼承其中之一；否則(含父母都沒有可遺傳性格的情況)一律走獨立隨機。"""
    candidates = [p for p in (sire_personality, dam_personality) if p in PERSONALITY_HERITABLE]
    if candidates and random.random() < PERSONALITY_INHERIT_CHANCE:
        return random.choice(candidates)
    return random_personality()


def trait_triggers(trait_name: str, pace: str, grade: str) -> bool:
    """這場比賽(給定跑法/賽事分級)這個特性會不會觸發，見各TraitDef.trigger_desc。"""
    if trait_name in ("快速起步", "彎道巧手", "末段爆發", "慢熱"):
        return True  # 起跑/彎道/衝刺/起跑-前段每場比賽都會經過，恆常觸發
    if trait_name == "領放穩定":
        return pace == "逃"
    if trait_name in ("抗壓", "容易緊張"):
        return grade in HIGH_TIER_GRADES
    if trait_name in ("重馬場高手", "海外適應"):
        return False  # MVP尚未實作對應系統，見模組docstring
    return False


def race_trait_bonus_pct(traits: list[str], pace: str, grade: str) -> float:
    """這匹馬這場比賽的特性加總百分比，直接對應engine/race.py HorseRaceInput.
    trait_bonus_pct——每個觸發的特性各自獨立抽樣5%~8%幅度，正面特性加、負面特性減，
    多個特性同時觸發時直接加總(馬匹系統.md「效果分開計算，不額外疊加倍率」)。"""
    total = 0.0
    for t in traits:
        if not trait_triggers(t, pace, grade):
            continue
        magnitude = random.uniform(TRAIT_EFFECT_PCT_MIN, TRAIT_EFFECT_PCT_MAX)
        sign = 1.0 if TRAIT_DEFS[t].kind == "正面" else -1.0
        total += sign * magnitude
    return total
