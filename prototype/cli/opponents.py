"""NPC 假對手馬產生器（docs/MVP範圍.md：MVP用固定強度的「假對手馬」出賽即可，
不需要真正跑買賣/訓練/財務的NPC決策AI）。"""
from __future__ import annotations

import random

from engine.race import HorseRaceInput

from .assumptions import GRADE_OPPONENT_LEVEL
from .horses import ALL_STATS

PACES = ("逃", "先", "差", "追")
AFFINITY_GRADES = ("S", "A", "B", "C", "D")


def _rand_stat(center: float, spread: float = 8.0) -> float:
    return max(1.0, min(100.0, random.gauss(center, spread)))


def generate_opponents(grade: str, count: int) -> list[HorseRaceInput]:
    """依賽事分級中樞屬性，隨機生成 `count` 匹NPC假對手馬的比賽輸入資料。"""
    center = GRADE_OPPONENT_LEVEL[grade]
    opponents: list[HorseRaceInput] = []
    for i in range(count):
        stats = {s: _rand_stat(center) for s in ALL_STATS}
        opponents.append(
            HorseRaceInput(
                name=f"NPC假對手{i + 1}",
                speed=stats["速度"],
                stamina=stats["耐力"],
                acceleration=stats["加速"],
                power=stats["力量"],
                guts=stats["根性"],
                intelligence=stats["智力"],
                start=stats["起跑"],
                corner=stats["彎道"],
                tactic_stat=stats["戰術"],
                mental=stats["精神"],
                health=stats["健康"],
                pace=random.choice(PACES),
                distance_affinity=random.choice(AFFINITY_GRADES),
                terrain_affinity=random.choice(AFFINITY_GRADES),
                status_grade=random.choice(("A", "B", "B", "C")),
                weight_diff_kg=0,
                jockey_correction=random.uniform(0.95, 1.05),
                jockey_position_judgement=_rand_stat(center),
                jockey_rhythm_control=_rand_stat(center),
                jockey_route_choice=_rand_stat(center),
                trait_bonus_pct=0.0,
                tactic_volatility_pct=random.uniform(-0.05, 0.05),
                random_volatility_pct=random.uniform(-0.08, 0.08),
                tactic_stamina_multiplier=1.0,
            )
        )
    return opponents
