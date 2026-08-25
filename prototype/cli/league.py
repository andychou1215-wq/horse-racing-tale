"""馬主聯盟升降級（docs/賽事/賽事與生涯系統.md「年度馬主聯盟」簡化版，
2026/8/25使用者決定新增，從MVP範圍.md「先跳過」清單補回）。

開工前先確認過4個範圍問題(比照本專案一貫的做法)：

1. **事業等級閘門**：doc「累積聲望可以提升事業等級，等級升級後解鎖拍賣會/馬主聯盟/
   海外賽事/海外馬房」——使用者選擇**不做事業等級系統**，馬主聯盟從新遊戲開局就直接
   生效(`GameState.league_tier`預設就是最低層級)，不需要玩家額外「加入聯盟」的動作
   或聲望門檻，也不影響拍賣會/海外賽事/海外馬房這幾個系統本身要不要做的決定(那些是
   獨立的其他範圍問題)。
2. **積分對手**：doc「其餘11位馬主」需要真的NPC馬主才有意義，但NPC馬主系統.md本身
   的完整決策引擎(自己買賣/配種/報名)這次範圍都還沒做。使用者選擇**虛擬積分對手**：
   每個賽季末(`resolve_season()`)隨機生成同層級的其餘馬主積分，不是真的NPC馬主帶著
   自己的馬房參賽，也不會在賽季之間保留身份(每季重新生成，不追蹤誰是誰)。
3. **海外馬房/海外賽事**：這次只補海外馬房「容量/升級」的設施殼子(見
   cli/facilities.py)，海外賽事系統本身還沒做，海外馬房目前沉睡。
4. **馬房/育馬場容量**：真的卡容量，見cli/game.py buy_horse()/_buy_breeding_stock()/
   assign_breeding_role()。

積分規則：doc「只有地方賽三級賽以上與國際賽事會產生積分」，採階梯型給分——doc只給了
各分級的計分名次上限(三級賽Top10~GI Top3)，沒給具體點值，`LEAGUE_POINTS_BY_GRADE`
是這次新增時的MVP假設值：分級越高基準點數越高，同一分級內名次越前面點數越多(線性
遞減到最後一名還保留一點基本分)。

同分時依doc「聯盟排名」規則逐項比較GI冠軍數→GII→GIII→一級賽→二級賽→三級賽冠軍數
(`TIEBREAK_GRADES`)，仍完全相同才並列(這裡簡化成取排序後第一個符合的位置，不特別
處理「並列」的顯示文字)。由於虛擬對手不是真的馬匹在跑，賽季末生成虛擬對手時順便依
他們的總積分反推一組「看起來合理」的分級冠軍數快照，只是為了讓比較公式能跑，不代表
真的發生過那些比賽。

「各層級Top3的馬主會獲得追加獎金與額外馬主聲望」——doc提到的「馬主聲望」目前沒有
獨立的數值欄位(只有馬匹自己的fame，沒有馬主層級的聲望系統，因為這次決定不做doc提到
的「事業等級」)，這裡簡化成只發追加獎金(`TOP3_BONUS_MONEY`)，聲望純敘事文字，不新增
欄位。
"""
from __future__ import annotations

import random

TIER_NAMES = {1: "頂級聯盟", 2: "第二級聯盟", 3: "第三級聯盟", 4: "第四級聯盟"}
HIGHEST_TIER = 1
LOWEST_TIER = 4

# doc「除最高級聯盟有10位馬主，其餘層級皆為12位」
TIER_SIZE = {1: 10, 2: 12, 3: 12, 4: 12}
# doc「每年最高級聯盟採2升2降，其餘層級採3升3降」——最高級沒有「升」、最低級沒有「降」，
# 這裡不用額外的邊界判斷，PROMOTE_COUNT[1]=0/RELEGATE_COUNT[4]=0本身就會讓對應條件
# 永遠不成立。
PROMOTE_COUNT = {1: 0, 2: 3, 3: 3, 4: 3}
RELEGATE_COUNT = {1: 2, 2: 3, 3: 3, 4: 0}

# doc「只有地方賽三級賽以上與國際賽事會產生積分」，各分級的計分名次上限依doc原文
# (三級賽Top10/二級賽Top8/一級賽Top6/GIII Top5/GII Top4/GI Top3)，具體點值是doc沒給
# 精確數字時的MVP假設值。
LEAGUE_POINTS_BY_GRADE = {
    "地方三級賽": [30, 24, 19, 15, 12, 9, 7, 5, 3, 2],
    "地方二級賽": [45, 36, 29, 22, 17, 12, 8, 5],
    "地方一級賽": [65, 52, 40, 30, 21, 14],
    "國際GIII": [90, 70, 52, 36, 22],
    "國際GII": [120, 92, 66, 42],
    "國際GI": [160, 110, 70],
}
# doc「聯盟排名」同分比較順序：GI冠軍數→GII→GIII→一級賽→二級賽→三級賽冠軍數
TIEBREAK_GRADES = ("國際GI", "國際GII", "國際GIII", "地方一級賽", "地方二級賽", "地方三級賽")

TOP3_BONUS_MONEY = {1: 60000.0, 2: 40000.0, 3: 30000.0, 4: 20000.0}  # 依所在層級給不同額度，MVP假設值

# 虛擬對手的積分生成參數：層級越高平均積分越高(對應「聯盟對手實力隨層級提升」的直覺)，
# 常態分布浮動，doc沒給精確數字的MVP假設值。
VIRTUAL_OPPONENT_POINTS_MEAN_BY_TIER = {1: 380.0, 2: 260.0, 3: 160.0, 4: 80.0}
VIRTUAL_OPPONENT_POINTS_SPREAD = 90.0
# 「每40分約等於1場奪冠」的粗略換算，用來把虛擬對手的總積分反推成一組分級冠軍數快照
# (只給tie-break用，見模組docstring)，同樣是MVP假設值。
VIRTUAL_OPPONENT_POINTS_PER_WIN = 40.0


def league_points_for_result(grade: str, rank: int) -> int:
    """這場比賽這個名次可以拿到的聯盟積分，不計分的分級/名次回傳0。"""
    table = LEAGUE_POINTS_BY_GRADE.get(grade)
    if table is None or rank > len(table):
        return 0
    return table[rank - 1]


def _random_virtual_win_counts(points: float) -> dict[str, int]:
    """依虛擬對手的總積分反推一組分級冠軍數快照，只用於同分時的tie-break排序，
    不代表真的發生過這些比賽——見模組docstring。"""
    counts = {g: 0 for g in TIEBREAK_GRADES}
    remaining = max(0, int(points // VIRTUAL_OPPONENT_POINTS_PER_WIN))
    for _ in range(remaining):
        # 高分級冠軍比較稀有，用遞增權重讓低分級冠軍出現得比較頻繁
        grade = random.choices(TIEBREAK_GRADES, weights=(1, 2, 3, 4, 5, 6))[0]
        counts[grade] += 1
    return counts


def generate_virtual_opponents(tier: int) -> list[dict]:
    """賽季末生成這個層級的虛擬對手清單(人數=TIER_SIZE[tier]-1，扣掉玩家自己那個
    名額)。每個虛擬對手是{"points": float, "win_counts": dict}，只在這次排名判定時
    使用，不會被存起來跨賽季追蹤身份。"""
    count = TIER_SIZE[tier] - 1
    mean = VIRTUAL_OPPONENT_POINTS_MEAN_BY_TIER[tier]
    opponents = []
    for _ in range(count):
        points = max(0.0, random.gauss(mean, VIRTUAL_OPPONENT_POINTS_SPREAD))
        opponents.append({"points": points, "win_counts": _random_virtual_win_counts(points)})
    return opponents


def _sort_key(points: float, win_counts: dict[str, int]) -> tuple:
    """排名用的排序鍵：先比總積分，再依TIEBREAK_GRADES順序逐項比較冠軍數。"""
    return (points, *(win_counts.get(g, 0) for g in TIEBREAK_GRADES))


def resolve_season(tier: int, player_points: float, player_win_counts: dict[str, int]) -> dict:
    """賽季末結算：生成虛擬對手、把玩家排進去、決定名次與升降級結果。

    回傳{"rank": 玩家名次(1起算), "field_size": 這層級總人數, "new_tier": 結算後的
    層級, "promoted": bool, "relegated": bool, "top3": bool}。
    """
    opponents = generate_virtual_opponents(tier)
    player_key = _sort_key(player_points, player_win_counts)
    opponent_keys = [_sort_key(o["points"], o["win_counts"]) for o in opponents]
    # 玩家排名 = 積分/tie-break贏過玩家的對手數 + 1
    player_rank = sum(1 for k in opponent_keys if k > player_key) + 1

    field_size = TIER_SIZE[tier]
    new_tier = tier
    promoted = False
    relegated = False
    if player_rank <= PROMOTE_COUNT[tier]:
        new_tier = tier - 1
        promoted = True
    elif player_rank > field_size - RELEGATE_COUNT[tier]:
        new_tier = tier + 1
        relegated = True

    return {
        "rank": player_rank,
        "field_size": field_size,
        "new_tier": new_tier,
        "promoted": promoted,
        "relegated": relegated,
        "top3": player_rank <= 3,
    }
