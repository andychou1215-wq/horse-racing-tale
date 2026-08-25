"""馬匹市場（docs/市場/馬匹市場.md，2026/8/23使用者決定新增現役馬市場，2026/8/24
使用者決定補上剩下3類：幼駒市場/種馬市場/繁殖母馬市場）。

GDD原文的「馬匹市場」分四類(幼駒市場/現役馬市場/種馬市場/繁殖母馬市場)，其中3類都
依賴繁殖/遺傳系統(血統、世代資料)——當初(2026/8/23)MVP還沒有繁殖系統，血統/父母/
世代這些欄位根本不存在，所以只做了「現役馬市場」。2026/8/24補回繁殖系統(見
cli/breeding.py)後，Horse已經有sire_name/dam_name/breeding_role這些欄位可以用，
這次把剩下3類market一併接上：

- **幼駒市場**：0~1歲的幼駒，帶有虛構的NPC「血統」(sire_name/dam_name取自
  `PEDIGREE_NAME_POOL`，純風味用途，不對應遊戲內任何實際存在的Horse物件，所以不會被
  `cli/breeding.py._is_inbred()`誤判近親)。
- **種馬市場/繁殖母馬市場**：已經retired=True、breeding_role已設定好(種馬/繁殖母馬)
  的成熟馬，買回家立刻能配種，不用再自己走一輪「退役→登記」的流程。定價在
  `market_value()`之上再加`HORSE_MARKET_BREEDING_READY_BONUS`溢價(見
  `breeding_stock_value()`)，反映GDD「種馬費由血統+比賽成績決定」——這裡是「直接買斷」
  而非「借配種付一次性種馬費」，所以價格明顯更高；血統/成績的影響則透過這兩類NPC馬
  生成時刻意設定較高的品質中樞、以及`market_value()`既有的評級/潛力/名氣/獎金係數
  間接反映。

交易機制沿用2026/8/23定案的簡化版：GDD原文的完整拍賣流程(拍賣會委員會審核底價、
競標者註冊驗證資金、限時競標價格逐級遞增)先不做，改成「固定開價 + 一鍵購買」。
"""
from __future__ import annotations

import random

from . import assumptions as A
from . import growth as G
from . import traits as T
from .horses import ALL_STATS, Horse

# 市場馬名字池：跟開局5匹固定測試馬(全能強馬/速度型快馬/...)風格不同，避免混淆這批是
# 「玩家自己買來的馬」而非測試馬。名字池用完(理論上不會發生，20個名字遠多於單局會買的
# 馬匹數)時用「市場馬N」編號保底，確保一定生得出不重複的名字。
HORSE_NAME_POOL = (
    "疾風", "黑閃電", "曉光", "赤兔", "白鬃烈影", "追月者", "烈焰蹄", "銀河尊",
    "破浪者", "雷鳴", "紫電", "金鬃王", "夜叉丸", "旋風腳", "怒濤", "無敵風火輪",
    "流星弦", "北斗影", "赤焰駒", "蒼狼",
)
# 幼駒/種馬/繁殖母馬市場共用另一個名字池，避免跟現役馬市場撞名混淆風味。
BREEDING_STOCK_NAME_POOL = (
    "曦皇", "銀月觴", "焰尾", "霜刃", "潮聲", "曠野歌者", "夜幕行者", "金風細雨",
    "斷雲", "赤霄", "碧空行", "玄鐵蹄", "朝暾", "殘月弓", "浮光掠影", "驚鴻步",
    "落霞孤鶩", "青鋒", "玉衡", "天璇",
)
# 虛構的NPC血統名字池，只用來填幼駒/種馬/繁殖母馬市場的sire_name/dam_name欄位營造
# 「有血統來歷」的風味，不對應遊戲內任何實際存在的Horse物件——不會被
# cli/breeding.py._is_inbred()誤判近親，也不會出現在state.horses裡。
PEDIGREE_NAME_POOL = (
    "北境荒原王", "遠雷公爵", "皇家紫焰", "南境流光后", "古堡幽影", "極光公爵",
    "沙丘旋風", "深林隱者", "潮汐女王", "赤霞聖騎",
)
PACES = ("逃", "先", "差", "追")
AFFINITY_GRADES = ("S", "A", "B", "C", "D")

HORSE_MARKET_LISTING_COUNT = 4  # 比照訓練師/獸醫市場一次4名候選人的規模
FOAL_MARKET_LISTING_COUNT = 3
STALLION_MARKET_LISTING_COUNT = 2
BROODMARE_MARKET_LISTING_COUNT = 2
# 幼駒/種馬/繁殖母馬市場規模刻意比現役馬市場小一點——這3類是「錦上添花」的加速手段
# (直接買到有一定水準的血統/種畜)，數量太多會稀釋玩家自己培育/配種的成就感。


def _unique_name(existing_names: set[str], pool: tuple[str, ...] = HORSE_NAME_POOL, fallback_prefix: str = "市場馬") -> str:
    for _ in range(50):
        candidate = random.choice(pool)
        if candidate not in existing_names:
            existing_names.add(candidate)
            return candidate
    i = 1
    while f"{fallback_prefix}{i}" in existing_names:
        i += 1
    existing_names.add(f"{fallback_prefix}{i}")
    return f"{fallback_prefix}{i}"


def _pedigree_names() -> tuple[str, str]:
    """從PEDIGREE_NAME_POOL隨機抽2個不重複的虛構血統名字當sire_name/dam_name。"""
    sire, dam = random.sample(PEDIGREE_NAME_POOL, 2)
    return sire, dam


def _rand_stat(center: float, spread: float = 10.0) -> float:
    return max(1.0, min(100.0, random.gauss(center, spread)))


def generate_market_horse(existing_names: set[str]) -> Horse:
    """隨機生成一匹待售現役馬。

    品質中樞(quality_center)隨機落在40~85之間，模擬市場上「普通馬到不錯的馬」都有；
    真正的頂級馬(接近90+)刻意不出現在市場——這類馬應該是玩家自己培育出來的成果，不該
    直接花錢買到，避免市場變成訓練系統的捷徑，也避免市場馬直接輾壓開局測試馬的平衡。

    年齡2~6歲隨機。2歲馬有4成機率是「還沒出賽的原石」(career_starts=0、graduated=
    False，可以直接報名新馬賽賭一把)，其餘(含所有3歲以上)一律視為已經打出成績、能報
    一般賽事的「畢業」現役馬。超齡未出賽馬依規則會自動退役；市場仍刻意讓3歲以上
    現役馬都帶有戰績且已畢業，維持商品定位與市場價值的一致性。
    """
    quality_center = random.uniform(40, 85)
    stats = {s: _rand_stat(quality_center) for s in ALL_STATS}
    # 潛力上限：至少要 >= 現有最高屬性(否則訓練會被往下拉齊)，再加一段隨機成長空間
    potential_cap = min(100.0, max(stats.values()) + random.uniform(3, 20))

    age = random.randint(A.MAIDEN_RACE_AGE, A.MAIDEN_RACE_AGE + 4)
    if age == A.MAIDEN_RACE_AGE and random.random() < 0.4:
        career_starts, graduated = 0, False
        fame, money_earned = 0.0, 0.0
    else:
        career_starts = random.randint(1, max(1, age * 3))
        graduated = True
        fame = round(random.uniform(0, 30), 1)
        money_earned = round(random.uniform(0, 20000), 0)

    return Horse(
        name=_unique_name(existing_names),
        stats=stats,
        potential_cap=potential_cap,
        pace=random.choice(PACES),
        distance_affinity=random.choice(AFFINITY_GRADES),
        terrain_affinity=random.choice(AFFINITY_GRADES),
        age=age,
        career_starts=career_starts,
        graduated=graduated,
        fame=fame,
        money_earned=money_earned,
        sex=random.choice(("公", "母")),
        # 2026/8/24新增繁殖系統後市場馬也需要性別，才能在買回家後登記為種馬/繁殖母馬。
        # 市場馬沒有血統紀錄(sire_name/dam_name維持預設None)，不影響近親判定。
        growth_curve=G.random_growth_curve(),
        # 2026/8/24新增成長曲線系統後補上：GDD明文「成長遺傳: 馬匹年齡成長類型不會遺傳」，
        # 市場馬一律獨立隨機決定，不參考(虛構或真實)血統。
        traits=T.random_traits(),
        personality=T.random_personality(),
        # 2026/8/24新增特性/性格系統後補上：市場馬沒有真實血統可以遺傳，一律走天生隨機池
        # (跟成長曲線同一個理由，見cli/traits.py模組docstring)。
    )


def generate_horse_market(count: int, existing_names: set[str]) -> list[Horse]:
    return [generate_market_horse(existing_names) for _ in range(count)]


def generate_foal_market_horse(existing_names: set[str]) -> Horse:
    """幼駒市場：0~1歲的幼駒，帶有虛構NPC血統(見模組docstring)。

    stats/potential的算法比照cli/breeding.py generate_foal()的精神(「父母」屬性平均+
    隨機浮動、潛力隨機制可能突破「父母」)，但這裡的「父母」是虛構的品質中樞值
    (FOAL_MARKET_QUALITY_MIN~MAX，50~90)，不是真的Horse物件——比玩家自己配種通常
    拿到的野生市場馬(quality_center 40~85)稍微優質一些，這是專門販售的血統幼駒，
    價格會透過market_value()的潛力餘裕係數反映出來。
    """
    sire_quality = random.uniform(A.FOAL_MARKET_QUALITY_MIN, A.FOAL_MARKET_QUALITY_MAX)
    dam_quality = random.uniform(A.FOAL_MARKET_QUALITY_MIN, A.FOAL_MARKET_QUALITY_MAX)
    parent_mean = (sire_quality + dam_quality) / 2
    stats = {s: _rand_stat(parent_mean) for s in ALL_STATS}

    potential_floor = max(stats.values()) + random.uniform(3, 20)
    potential_sample = random.gauss(parent_mean + 10, 8.0)  # 中樞刻意比屬性平均再高一些，代表幼駒還有成長空間
    potential_cap = min(100.0, max(potential_floor, potential_sample))

    sire_name, dam_name = _pedigree_names()
    return Horse(
        name=_unique_name(existing_names, BREEDING_STOCK_NAME_POOL, "幼駒市場馬"),
        stats=stats,
        potential_cap=round(potential_cap, 1),
        pace=random.choice(PACES),
        distance_affinity=random.choice(AFFINITY_GRADES),
        terrain_affinity=random.choice(AFFINITY_GRADES),
        age=random.choice((0, 1)),
        sex=random.choice(("公", "母")),
        sire_name=sire_name,
        dam_name=dam_name,
        growth_curve=G.random_growth_curve(),  # 不遺傳，獨立隨機(見generate_market_horse同一句說明)
        traits=T.random_traits(),  # 幼駒市場的血統是虛構的(sire_name/dam_name不對應真實Horse)，
        personality=T.random_personality(),  # 沒有真的父母資料可以遺傳，一律隨機
    )


def generate_foal_market(count: int, existing_names: set[str]) -> list[Horse]:
    return [generate_foal_market_horse(existing_names) for _ in range(count)]


def _generate_breeding_stock(
    existing_names: set[str], sex: str, role: str, quality_min: float, quality_max: float
) -> Horse:
    """種馬市場/繁殖母馬市場共用的生成邏輯：已退役、breeding_role已設定好、3~12歲、
    帶有還算不錯的生涯戰績(fame/money_earned)，買回家立刻能配種，不用再自己走一輪
    「退役→登記」的流程。
    """
    quality_center = random.uniform(quality_min, quality_max)
    stats = {s: _rand_stat(quality_center) for s in ALL_STATS}
    potential_cap = min(100.0, max(stats.values()) + random.uniform(2, 12))

    age = random.randint(A.BREEDING_MIN_AGE, A.BREEDING_MAX_AGE)
    career_starts = random.randint(3, max(3, age * 3))
    fame = round(random.uniform(10, 60), 1)
    money_earned = round(random.uniform(5000, 80000), 0)
    # 有5成機率帶有虛構血統(另外5成沒有，代表「素質不錯但血統平凡」的種畜也存在，
    # 增加市場多樣性，不是每匹都要有響亮的血統名字)。
    sire_name, dam_name = _pedigree_names() if random.random() < 0.5 else (None, None)

    return Horse(
        name=_unique_name(existing_names, BREEDING_STOCK_NAME_POOL, f"{role}市場馬"),
        stats=stats,
        potential_cap=round(potential_cap, 1),
        pace=random.choice(PACES),
        distance_affinity=random.choice(AFFINITY_GRADES),
        terrain_affinity=random.choice(AFFINITY_GRADES),
        age=age,
        sex=sex,
        career_starts=career_starts,
        graduated=True,
        fame=fame,
        money_earned=money_earned,
        retired=True,
        breeding_role=role,
        sire_name=sire_name,
        dam_name=dam_name,
        growth_curve=G.random_growth_curve(),  # 不遺傳，獨立隨機(見generate_market_horse同一句說明)
        traits=T.random_traits(),
        personality=T.random_personality(),
    )


def generate_stallion_market_horse(existing_names: set[str]) -> Horse:
    return _generate_breeding_stock(
        existing_names, "公", "種馬", A.STALLION_MARKET_QUALITY_MIN, A.STALLION_MARKET_QUALITY_MAX
    )


def generate_stallion_market(count: int, existing_names: set[str]) -> list[Horse]:
    return [generate_stallion_market_horse(existing_names) for _ in range(count)]


def generate_broodmare_market_horse(existing_names: set[str]) -> Horse:
    return _generate_breeding_stock(
        existing_names, "母", "繁殖母馬", A.BROODMARE_MARKET_QUALITY_MIN, A.BROODMARE_MARKET_QUALITY_MAX
    )


def generate_broodmare_market(count: int, existing_names: set[str]) -> list[Horse]:
    return [generate_broodmare_market_horse(existing_names) for _ in range(count)]


def market_value(horse: Horse) -> float:
    """簡化版市場價值估算，比照GDD「市場價值 = 血統+年齡+戰績+能力+潛力+健康+人氣」的
    精神，但沒有另外設「血統」係數(這個函式所有4類市場共用，2026/8/24補上幼駒/種馬/
    繁殖母馬市場時決定不改動這個既有公式——「血統較好」改成透過這3類市場生成時刻意設定
    較高的品質中樞來反映，而不是在這裡加一個只有部分Horse才有意義的血統加價項)；
    「健康」則因為本來就是11項屬性之一，已經算進overall_rating()裡了，不再重複計價，
    避免雙重計算。種馬/繁殖母馬的「已登記可立即配種」溢價另外用breeding_stock_value()
    疊加，不混進這個通用公式。

    年齡對價格沒有獨立加減項——MVP沒有做完整的成長曲線/衰退期，沒有「巔峰年齡」概念
    可以拿來加價或打折；年齡只透過「戰績」(career_starts/graduated/money_earned/fame，
    通常年齡越大生涯累積得越多)間接反映在價格上。
    """
    value = A.HORSE_MARKET_BASE_PRICE
    value += horse.overall_rating() * A.HORSE_MARKET_RATING_COEF
    value += horse.growth_room() * A.HORSE_MARKET_POTENTIAL_ROOM_COEF
    value += horse.fame * A.HORSE_MARKET_FAME_COEF
    value += horse.money_earned * A.HORSE_MARKET_EARNED_COEF
    if horse.graduated:
        value += A.HORSE_MARKET_GRADUATED_BONUS
    return round(value, -2)  # 湊整百，價格好讀


def breeding_stock_value(horse: Horse) -> float:
    """種馬市場/繁殖母馬市場的定價 = market_value() + 「已退役+已登記可立即配種」的
    便利性溢價(HORSE_MARKET_BREEDING_READY_BONUS)。比照GDD「種馬費由血統+比賽成績
    決定」的精神：這裡是「買斷」而非「借配種付一次性種馬費」，所以價格明顯比單純市場
    價值更高。
    """
    return round(market_value(horse) + A.HORSE_MARKET_BREEDING_READY_BONUS, -2)
