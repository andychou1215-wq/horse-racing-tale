"""繁殖/遺傳系統（docs/繁殖/血統與繁殖系統.md、遺傳系統.md 簡化版，
2026/8/24使用者決定新增）。

開工前先跟使用者確認過3個範圍問題(比照第12步現役馬市場的做法)：

1. **配種機制深度**：GDD原文有自然交配/人工授精雙軌(速度/成本/受孕率不同)、21~22天
   發情週期、配種前後獸醫檢查等細節流程。使用者選擇**簡化版**：只做「配種」單一動作，
   選一匹種馬+一匹繁殖母馬、扣配種成本、判定成功率，成功後等待固定產駒期(GESTATION_
   WEEKS)後生產，配種嘗試之間有固定冷卻(BREEDING_ATTEMPT_COOLDOWN_WEEKS)取代真正的
   發情週期倒數。
2. **繁殖資格**：GDD原文「退役馬轉型成為繁殖馬」+ 3~12歲限制。使用者選擇**先退役才能
   繁殖**(照GDD原文精神)，不開放現役中的馬直接配種。
3. **幼駒屬性生成**：使用者選擇**父母屬性平均+隨機浮動+潛力隨機制**——11項屬性=父母
   平均±常態分布浮動，整體潛力=父母潛力平均為中樞的常態分布浮動(可能突破父母)，近親
   繁殖降低潛力中樞、加大健康受損機率。不做特性/性格/適性/血統相性遺傳(GDD雖列了但
   這些是次要遺傳細節，這次範圍刻意不做，注意跟`遺傳系統.md`本文一致：適性/成長曲線
   類型完全不遺傳，性格MVP還沒有性格系統，血統相性也先跳過)。

血統只往上追蹤1代(Horse.sire_name/dam_name)，不建立完整多代血統樹——近親判定
(`_is_inbred`)因此只抓得到「親子」「同父/同母的手足」這兩種情況，抓不到隔代或更遠
親緣的近親繁殖，是這次簡化範圍刻意接受的限制，之後如果要做更完整的血統書可以再擴充。

種馬市場/繁殖母馬市場(GDD第8節「市場與拍賣系統」剩下的2類)這次也還沒接上——玩家
只能拿自己馬房裡已登記的種馬/繁殖母馬互相配種，沒有向外部NPC種馬借配種(付種馬費)
的管道，比照第12步只做現役馬市場、不做完整拍賣流程的簡化精神，避免一次擴張太多範圍。
"""
from __future__ import annotations

import random

from . import assumptions as A
from . import growth as G
from . import traits as T
from .horses import ALL_STATS, Horse

# 幼駒名字池：跟開局5匹固定測試馬、現役馬市場的名字池(cli/horse_market.py)風格都不同，
# 避免混淆這批是「自己馬房裡配種生出來的馬」。
FOAL_NAME_POOL = (
    "初蹄", "曦光", "小旋風", "初雪", "初陽", "嫩草", "萌焰", "初聲",
    "朝露", "破曉", "新綠", "初奔", "微光", "初風", "嫩芽", "初鳴",
    "幼影", "初蕾", "青澀", "初翼",
)
PACES = ("逃", "先", "差", "追")
AFFINITY_GRADES = ("S", "A", "B", "C", "D")


def _unique_foal_name(existing_names: set[str]) -> str:
    for _ in range(50):
        candidate = random.choice(FOAL_NAME_POOL)
        if candidate not in existing_names:
            existing_names.add(candidate)
            return candidate
    i = 1
    while f"幼駒{i}" in existing_names:
        i += 1
    existing_names.add(f"幼駒{i}")
    return f"幼駒{i}"


def _is_inbred(mare: Horse, sire: Horse) -> bool:
    """近親繁殖判定(遺傳系統.md「近親繁殖將會限制子代的潛力上限與健康狀況」)。

    只用1代血統(sire_name/dam_name)判斷，涵蓋：
    - 親子配(其中一方是另一方記錄在案的父/母)
    - 手足配(雙方共享同一個父親或母親)

    開局測試馬/市場馬都沒有血統紀錄(sire_name=dam_name=None)，預設不會被判定近親。
    """
    if sire.name in (mare.sire_name, mare.dam_name):
        return True
    if mare.name in (sire.sire_name, sire.dam_name):
        return True
    mare_ancestors = {n for n in (mare.sire_name, mare.dam_name) if n is not None}
    sire_ancestors = {n for n in (sire.sire_name, sire.dam_name) if n is not None}
    return bool(mare_ancestors & sire_ancestors)


def _rand_stat(mean: float, spread: float) -> float:
    return round(max(1.0, min(100.0, random.gauss(mean, spread))), 1)


def generate_foal(
    mare: Horse,
    sire_stats: dict[str, float],
    sire_potential_cap: float,
    sire_name: str,
    inbred: bool,
    existing_names: set[str],
    sire_traits: list[str] | None = None,
    sire_personality: str | None = None,
) -> tuple[Horse, str]:
    """依父母資料生成一匹新出生的幼駒(0歲)，回傳(幼駒, 額外備註文字)。

    `sire_stats`/`sire_potential_cap`/`sire_traits`/`sire_personality` 是配種當下
    (breed())拍照存證的種馬資料快照，不是即時去查活著的種馬物件——避免種馬在懷孕期間
    被賣掉/屬性被訓練改變時算不出來或算錯。`sire_traits`/`sire_personality`是
    2026/8/24新增特性/性格系統時補上的參數，預設None/[]是為了跟舊呼叫端(測試)向下
    相容，實際上cli/game.py apply_weekly_pregnancy_progression()一定會傳值進來。
    """
    stats = {
        stat: _rand_stat((mare.stats[stat] + sire_stats[stat]) / 2, A.BREEDING_STAT_SPREAD)
        for stat in ALL_STATS
    }
    # 幼駒代表「先天傾向」的起始值，比照遺傳系統.md「父母突出屬性子代成長也較快」的精神，
    # MVP簡化成直接讓幼駒起始值貼近父母平均(而非另外模擬一套「該屬性成長更快」的獨立
    # 倍率機制——MVP潛力餘裕公式本來就是11項屬性共用同一個整體潛力上限，沒有逐屬性
    # 獨立成長速度的概念可以掛)。

    potential_mean = (mare.potential_cap + sire_potential_cap) / 2
    note = ""
    if inbred:
        potential_mean *= 1 - A.BREEDING_INBREEDING_POTENTIAL_PENALTY_PCT
    potential_sample = random.gauss(potential_mean, A.BREEDING_POTENTIAL_SPREAD)
    # 潛力有「突破父母」的可能(遺傳系統.md「潛力採隨機制，存在突破父母的可能」)：不對
    # potential_sample做上限裁切成max(sire,dam)，讓常態分布自然偶爾超越雙親。
    # 保底：潛力上限至少要能比幼駒目前最高屬性再高一截，否則訓練會被立刻拉平(比照
    # cli/horse_market.py generate_market_horse同樣的保底邏輯)。
    potential_floor = max(stats.values()) + random.uniform(2, 15)
    potential_cap = round(min(100.0, max(A.BREEDING_POTENTIAL_MIN, potential_floor, potential_sample)), 1)

    if inbred and random.random() < A.BREEDING_INBREEDING_HEALTH_ISSUE_CHANCE:
        stats["健康"] = round(stats["健康"] * (1 - A.BREEDING_INBREEDING_HEALTH_ISSUE_PENALTY_PCT), 1)
        note = "（近親繁殖遺傳疾病，健康受損）"

    foal = Horse(
        name=_unique_foal_name(existing_names),
        stats=stats,
        potential_cap=potential_cap,
        # 跑法/距離適性/場地適性不遺傳(遺傳系統.md「適性遺傳」)，跟市場馬一樣純隨機生成。
        pace=random.choice(PACES),
        distance_affinity=random.choice(AFFINITY_GRADES),
        terrain_affinity=random.choice(AFFINITY_GRADES),
        age=0,
        sex=random.choice(("公", "母")),
        sire_name=sire_name,
        dam_name=mare.name,
        growth_curve=G.random_growth_curve(),
        # 2026/8/24新增成長曲線系統後補上：遺傳系統.md/growth.py docstring都明文「成長
        # 遺傳: 馬匹年齡成長類型不會遺傳」，幼駒的成長曲線類型跟跑法/適性一樣純隨機決定，
        # 不參考父母的growth_curve。
        traits=T.inherit_traits(sire_traits or [], mare.traits),
        personality=T.inherit_personality(sire_personality, mare.personality),
        # 2026/8/24新增特性/性格系統後補上：跟成長曲線相反，特性/性格「部分會遺傳」
        # (遺傳系統.md「特性遺傳」「性格遺傳」)，所以這裡呼叫inherit_traits()/
        # inherit_personality()而不是隨機生成，見cli/traits.py模組docstring的機率設計。
    )
    return foal, note
