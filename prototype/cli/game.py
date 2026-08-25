"""遊戲狀態與核心迴圈邏輯（訓練/休息/比賽日/週結算），供 cli/play.py 呼叫。

所有實際數值計算一律呼叫 engine/ 現有公式；本檔只負責「串接」——把
Horse 的資料轉成 engine 需要的輸入格式、處理疲勞/資金/名氣等 MVP 層的
簿記，以及依 docs/培育/隨機事件清單.md 精神做簡化版隨機事件。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from engine.race import HorseRaceInput, simulate_race
from engine.training import apply_training

from . import assumptions as A
from . import growth as G
from . import league as L
from . import traits as T
from .breeding import generate_foal, _is_inbred
from .facilities import (
    decline_mitigation_for_level as facility_decline_mitigation,
    default_facility_levels,
    fatigue_relief_bonus_for_level as facility_fatigue_relief_bonus,
    injury_recovery_bonus_for_level as facility_injury_recovery_bonus,
    overseas_stable_capacity_for_level as facility_overseas_stable_capacity,
    stable_capacity_for_level as facility_stable_capacity,
    stat_facility,
    stud_farm_capacity_for_level as facility_stud_farm_capacity,
    training_multiplier_for_level as facility_training_multiplier,
)
from .facilities import MAX_LEVEL as FACILITY_MAX_LEVEL
from .facilities import upgrade_cost as facility_upgrade_cost
from .horse_market import (
    BROODMARE_MARKET_LISTING_COUNT,
    FOAL_MARKET_LISTING_COUNT,
    HORSE_MARKET_LISTING_COUNT,
    STALLION_MARKET_LISTING_COUNT,
    generate_broodmare_market,
    generate_foal_market,
    generate_horse_market,
    generate_stallion_market,
)
from .horse_market import breeding_stock_value as horse_breeding_stock_value
from .horse_market import market_value as horse_market_value
from .horses import ALL_STATS, Horse, TRAINABLE_STATS
from .injuries import (
    RECENT_LIGHT_INJURY_WINDOW_WEEKS,
    SEVERITY_PERMANENT_PENALTY_PCT,
    SEVERITY_RETIREMENT_CHANCE,
    Injury,
    recovery_weeks_per_tick,
    roll_injury,
)
from .injuries import can_assign as vet_can_assign
from .injuries import MAX_HORSES_REDUCED_EFFICIENCY as VET_MAX_HORSES_REDUCED_EFFICIENCY
from .opponents import generate_opponents
from .trainers import (
    Trainer,
    capacity_multiplier,
    fatigue_relief_bonus,
    generate_trainer_market,
    training_multiplier,
)
from .vets import Vet, generate_vet_market


@dataclass
class Jockey:
    correction: float
    position_judgement: float
    rhythm_control: float
    route_choice: float


@dataclass
class GameState:
    horses: list[Horse]
    jockeys: dict[str, Jockey]
    money: float = A.STARTING_MONEY
    week: int = 1
    bankrupt: bool = False
    log: list[str] = field(default_factory=list)
    trainers: list[Trainer] = field(default_factory=list)
    # 訓練師系統.md，2026/8/22使用者決定補回：已聘用的訓練師清單。開局沒有聘用任何
    # 訓練師（等同這個系統補回前的假設值：訓練倍率固定1.0），需要玩家自行從市場聘用。
    vets: list[Vet] = field(default_factory=list)
    # 獸醫/傷病系統.md，2026/8/22使用者決定補回：已聘用的獸醫清單，同樣開局沒有聘用，
    # 沒有指定獸醫時傷病仍會自然恢復，只是速度較慢、預防加成為0（向下相容）。
    facility_levels: dict[str, int] = field(default_factory=default_facility_levels)
    # 設施系統.md，使用者決定補回：7種設施(5種屬性訓練場+恢復中心+醫療中心)開局都是
    # Lv2，等同這個系統補回前的固定假設值(FIXED_FACILITY_MULTIPLIER=1.1)，向下相容。
    trainer_market: list[Trainer] = field(default_factory=lambda: generate_trainer_market(count=4))
    vet_market: list[Vet] = field(default_factory=lambda: generate_vet_market(count=3))
    last_market_refresh_week: int = 1
    # 2026/8/22使用者決定：訓練師/獸醫市場每MARKET_REFRESH_INTERVAL_WEEKS(4)週自動
    # 刷新一次未聘用的候選人清單，讓玩家有新的員工可以選擇（見 refresh_markets_if_due）。
    # 已聘用的訓練師/獸醫(state.trainers/state.vets)是獨立清單，不受刷新影響。
    horse_market: list[Horse] = field(default_factory=list)
    # 2026/8/23使用者決定新增現役馬市場(cli/horse_market.py)：待售馬匹清單，跟trainer_
    # market/vet_market同一套MARKET_REFRESH_INTERVAL_WEEKS刷新節奏(見refresh_markets_
    # if_due)。預設空清單、由new_game()明確生成，理由是要避開跟開局5匹測試馬同名，
    # 不能用dataclass field default_factory在建構當下就決定(那時候還看不到state.horses)。
    foal_market: list[Horse] = field(default_factory=list)
    stallion_market: list[Horse] = field(default_factory=list)
    broodmare_market: list[Horse] = field(default_factory=list)
    # 2026/8/24使用者決定補上GDD市場章節剩下的3類(見cli/horse_market.py模組docstring)，
    # 跟horse_market同一套刷新節奏、同樣理由用空清單default_factory再由new_game()明確生成。

    league_tier: int = L.LOWEST_TIER
    # 2026/8/25使用者決定補上馬主聯盟升降級系統(見cli/league.py模組docstring)：不做
    # doc提到的「事業等級」解鎖門檻，新遊戲開局就直接在最低層級(比照doc「玩家若選擇
    # 加入聯盟則將從最低層級開始」，只是這裡省略「選擇加入」的動作，恆常視為已加入)。
    league_points: float = 0.0  # 本賽季累積積分，見cli/game.py run_race()裡的league_points_for_result()呼叫
    league_win_counts: dict[str, int] = field(default_factory=lambda: {g: 0 for g in L.TIEBREAK_GRADES})
    # 本賽季各分級冠軍數，供賽季末同分時的tie-break排序用(見cli/league.py TIEBREAK_GRADES)
    league_last_season_result: str | None = None
    # 上一次賽季結算的敘述文字(升降級/Top3獎勵)，純顯示用，見
    # apply_weekly_league_season_progression()

    def horse_by_name(self, name: str) -> Horse:
        for h in self.horses:
            if h.name == name:
                return h
        raise KeyError(name)

    def trainer_by_name(self, name: str | None) -> Trainer | None:
        if name is None:
            return None
        for t in self.trainers:
            if t.name == name:
                return t
        return None

    def vet_by_name(self, name: str | None) -> Vet | None:
        if name is None:
            return None
        for v in self.vets:
            if v.name == name:
                return v
        return None


def new_game() -> GameState:
    from .horses import starter_horses

    horses = starter_horses()
    jockeys = {
        h.name: Jockey(
            correction=round(random.uniform(0.95, 1.08), 3),
            position_judgement=round(random.uniform(55, 85), 1),
            rhythm_control=round(random.uniform(55, 85), 1),
            route_choice=round(random.uniform(55, 85), 1),
        )
        for h in horses
    }
    state = GameState(horses=horses, jockeys=jockeys)
    existing_names = {h.name for h in horses}
    # 2026/8/24使用者決定補上幼駒/種馬/繁殖母馬市場後，4類市場共用同一個existing_names
    # 集合、依序生成(而不是各自獨立算一次{h.name for h in horses})，確保這4份清單彼此
    # 之間也不會撞名(BREEDING_STOCK_NAME_POOL/HORSE_NAME_POOL本身不重疊，但保險起見還是
    # 共用同一個集合)。
    state.horse_market = generate_horse_market(count=HORSE_MARKET_LISTING_COUNT, existing_names=existing_names)
    state.foal_market = generate_foal_market(count=FOAL_MARKET_LISTING_COUNT, existing_names=existing_names)
    state.stallion_market = generate_stallion_market(count=STALLION_MARKET_LISTING_COUNT, existing_names=existing_names)
    state.broodmare_market = generate_broodmare_market(count=BROODMARE_MARKET_LISTING_COUNT, existing_names=existing_names)
    return state


MARKET_REFRESH_INTERVAL_WEEKS = 4  # 跟比賽週同週期(is_race_week)，使用者決定的刷新頻率


def refresh_markets_if_due(state: "GameState") -> str | None:
    """訓練師/獸醫市場每 MARKET_REFRESH_INTERVAL_WEEKS 週自動刷新一次未聘用的候選人。

    只換掉「市場清單」(state.trainer_market/vet_market)，已聘用的訓練師/獸醫
    (state.trainers/state.vets)是獨立清單，完全不受影響——刷新不會辭退玩家已經
    聘用的人力，只是讓「還沒聘的話可以選誰」定期換新，避免玩家卡在同一批候選人裡。

    呼叫時機：每次 state.week 更新之後(webapp/cli 各自的週進度推進點)。同一週內
    重複呼叫是安全的(週數差距不到門檻就直接跳過，不會重複刷新)。
    """
    weeks_since_refresh = state.week - state.last_market_refresh_week
    if weeks_since_refresh < MARKET_REFRESH_INTERVAL_WEEKS:
        return None
    state.trainer_market = generate_trainer_market(count=4)
    state.vet_market = generate_vet_market(count=3)
    # 2026/8/23使用者決定新增現役馬市場後，比照同一個刷新節奏：未售出的市場馬匹整批換新
    # (不像訓練師/獸醫是「未聘用的候選人」被替換，這裡是「還沒被買走的待售馬匹」被替換，
    # 已經買下、進了state.horses的馬完全不受影響)。2026/8/24補上幼駒/種馬/繁殖母馬市場
    # 後同樣套用這個刷新節奏，4類市場共用同一個existing_names集合依序生成，理由同
    # new_game()。
    existing_names = {h.name for h in state.horses}
    state.horse_market = generate_horse_market(count=HORSE_MARKET_LISTING_COUNT, existing_names=existing_names)
    state.foal_market = generate_foal_market(count=FOAL_MARKET_LISTING_COUNT, existing_names=existing_names)
    state.stallion_market = generate_stallion_market(count=STALLION_MARKET_LISTING_COUNT, existing_names=existing_names)
    state.broodmare_market = generate_broodmare_market(count=BROODMARE_MARKET_LISTING_COUNT, existing_names=existing_names)
    state.last_market_refresh_week = state.week
    return f"訓練師/獸醫/馬匹市場刷新了，第{state.week}週起有新的人選/馬匹可以選擇"


# ---------------------------------------------------------------- 訓練/休息

def roll_weekly_event(is_racing_this_week: bool) -> str | None:
    """MVP範圍.md：只保留「幸運訓練」(正面)、「疲勞加劇」(負面)兩項隨機事件。

    對應 培育/隨機事件清單.md 的機率精神：基礎5%，比賽週+3%，簡化為單一
    對象(馬匹)判定，正負各半。
    """
    chance = A.EVENT_BASE_CHANCE + (A.EVENT_RACE_WEEK_BONUS if is_racing_this_week else 0)
    if random.random() >= chance:
        return None
    return "幸運訓練" if random.random() < A.LUCKY_TRAINING_CHANCE else "疲勞加劇"


def trainer_effective_multiplier(state: "GameState", horse: Horse, stat: str) -> float:
    """指定馬匹在這個屬性上實際拿到的訓練師倍率：專長加成 x 管理容量折扣。

    沒有指定訓練師時回傳1.0（見 GameState.trainers 的說明，向下相容補回這個系統前的假設值）。
    """
    trainer = state.trainer_by_name(horse.assigned_trainer)
    base_mult = training_multiplier(trainer, stat)
    if trainer is None:
        return base_mult
    assigned_count = sum(1 for h in state.horses if h.assigned_trainer == trainer.name)
    return base_mult * capacity_multiplier(assigned_count)


def train_horse(state: "GameState", horse: Horse, stat: str, event: str | None = None) -> str:
    """對一匹馬執行一次訓練，回傳結果敘述。"""
    if horse.retired:
        raise ValueError(f"{horse.name} 已經退役，無法訓練")
    if horse.injury is not None:
        raise ValueError(
            f"{horse.name} 正在養傷（{horse.injury.name}，剩餘{horse.injury.weeks_remaining}週），"
            "暫時無法訓練，只能休養"
        )
    if not horse.can_train():
        raise ValueError(
            f"{horse.name} 還未滿{A.MIN_TRAINING_AGE}歲（目前{horse.age}歲），還不能開始訓練"
        )
    if stat not in TRAINABLE_STATS:
        raise ValueError(f"MVP 範圍不支援訓練項目：{stat}（僅支援 {TRAINABLE_STATS}）")

    before = horse.stats[stat]
    status = A.state_grade(horse.stats["健康"], horse.fatigue)
    status_mult = {"S": 1.2, "A": 1.1, "B": 1.0, "C": 0.9, "D": 0.8}[status]

    base = A.BASE_TRAINING_VALUE
    fatigue_gain = A.TRAIN_FATIGUE_GAIN

    if event == "幸運訓練":
        base *= 2  # 訓練效果加倍，不影響疲勞累積
        fatigue_gain = 0
    elif event == "疲勞加劇":
        fatigue_gain *= 1.8  # 疲勞值大幅上升，本週訓練效果打折
        base *= 0.6

    trainer_mult = trainer_effective_multiplier(state, horse, stat)
    facility_mult = facility_effective_multiplier(state, stat)
    new_value = apply_training(
        base_training_value=base,
        potential_cap=horse.potential_cap,
        current_value=before,
        age_stage_multiplier=G.age_stage_multiplier(horse.growth_curve, horse.age),
        trainer_multiplier=trainer_mult,
        facility_multiplier=facility_mult,
        status_multiplier=status_mult,
    )
    horse.stats[stat] = new_value
    horse.fatigue = min(100.0, horse.fatigue + fatigue_gain)

    gain = new_value - before
    msg = f"{horse.name} 進行「{stat}訓練」：{before:.1f} → {new_value:.1f}（+{gain:.2f}，狀態{status}）"
    if trainer_mult != 1.0:
        msg += f" ｜訓練師加成x{trainer_mult:.2f}"
    if event:
        msg += f" ｜觸發隨機事件「{event}」"
    return msg


def facility_effective_multiplier(state: "GameState", stat: str) -> float:
    """指定屬性目前對應設施等級帶來的訓練倍率（設施系統.md）。

    沒有對應設施(理論上不會發生，9項可訓練屬性都有對應設施)時回傳1.0。
    """
    facility = stat_facility(stat)
    if facility is None:
        return 1.0
    return facility_training_multiplier(state.facility_levels[facility])


def rest_horse(horse: Horse, event: str | None = None) -> str:
    """休息：降低疲勞，不成長屬性。"""
    before = horse.fatigue
    loss = A.REST_FATIGUE_LOSS
    if event == "疲勞加劇":
        loss *= 0.5  # 疲勞加劇當週連休息效果都打折
    horse.fatigue = max(0.0, horse.fatigue - loss)
    msg = f"{horse.name} 休息：疲勞 {before:.1f} → {horse.fatigue:.1f}"
    if event:
        msg += f" ｜觸發隨機事件「{event}」"
    return msg


# -------------------------------------------------------------------- 比賽

def eligible_grades(horse: Horse) -> list[str]:
    """依評級門檻 + 使用者決定新增的「新馬賽/未勝利賽生涯資格制」共同決定可報名分級。

    2026/8/23使用者決定的生涯資格制(疊加在原本的評級門檻之上，兩者都要滿足)：
    - 新馬賽：限MAIDEN_RACE_AGE(2)歲、且生涯從未出賽過(career_starts==0)的馬才能報名，
      出賽過一次(不論名次)就永久不能再報名新馬賽——對應「只要參加過新馬賽的馬匹便不可
      再參加新馬賽」。
    - 未勝利賽：限已經出賽過(career_starts>=1)、但還沒「畢業」(not graduated)的馬報名。
      贏得未勝利賽會在run_race()裡把graduated設為True，之後不能再回頭報名未勝利賽。
    - 地方一般賽以上（一般賽事）：限已經「畢業」(graduated，代表贏過新馬賽或未勝利賽)的馬
      才能報名——對應「新馬賽獲勝的馬獲得參加一般賽事的權利」。

    2026/8/25最終規則：從未出賽的馬若錯過新馬賽年齡，會在年齡結算時自動退役，再由玩家
    透過既有繁殖頁面/CLI選擇退役路線；不開放超齡馬直接從未勝利賽出道。
    """
    rating = horse.overall_rating()
    result = []
    for grade in A.RACE_GRADES:
        if rating < A.GRADE_ELIGIBILITY_THRESHOLD[grade]:
            continue
        if grade == "新馬賽":
            if horse.age == A.MAIDEN_RACE_AGE and horse.career_starts == 0:
                result.append(grade)
        elif grade == "未勝利賽":
            if horse.career_starts >= 1 and not horse.graduated:
                result.append(grade)
        else:
            if horse.graduated:
                result.append(grade)
    return result


def is_race_week(week: int) -> bool:
    """2026/8/23使用者決定：賽事舉辦時間從原本每4週一次改成每週一次，所以恆為True。

    保留這個函式而非把呼叫端(webapp/cli/tools/financial_simulation)的分支拿掉，理由：
    (1) 呼叫端原本就是靠這個flag決定「訓練送出後要不要導向報名頁」，現在導向永遠成立，
    語意仍然正確、不用改呼叫端邏輯；(2) EVENT_RACE_WEEK_BONUS(隨機事件加成)也是吃這個
    flag，改成週週開賽後這個加成變成恆常生效，是這次規則調整的自然結果(代表整個馬房
    每週都在比賽節奏中，不是bug)；(3) 保留這個切點，之後如果要做「非賽季」之類的概念
    仍有現成的擴充點。註：「馬匹個別是否能出賽」現在改由 Horse.can_race()(受傷/退役/
    出賽冷卻中)把關，不是靠這個全域flag。
    """
    return True


def _horse_to_race_input(state: GameState, horse: Horse, tactic: str, grade: str) -> HorseRaceInput:
    jockey = state.jockeys[horse.name]
    status = A.state_grade(horse.stats["健康"], horse.fatigue)
    tactic_volatility = random.uniform(0.03, 0.05) * random.choice((1, -1))
    tactic_stamina_mult = 0.85 if tactic == "保存體力" else 1.0
    return HorseRaceInput(
        name=horse.name,
        speed=horse.stats["速度"],
        stamina=horse.stats["耐力"],
        acceleration=horse.stats["加速"],
        power=horse.stats["力量"],
        guts=horse.stats["根性"],
        intelligence=horse.stats["智力"],
        start=horse.stats["起跑"],
        corner=horse.stats["彎道"],
        tactic_stat=horse.stats["戰術"],
        mental=horse.stats["精神"],
        health=horse.stats["健康"],
        pace=horse.pace,
        distance_affinity=horse.distance_affinity,
        terrain_affinity=horse.terrain_affinity,
        status_grade=status,
        weight_diff_kg=0,
        jockey_correction=jockey.correction,
        jockey_position_judgement=jockey.position_judgement,
        jockey_rhythm_control=jockey.rhythm_control,
        jockey_route_choice=jockey.route_choice,
        trait_bonus_pct=T.race_trait_bonus_pct(horse.traits, horse.pace, grade),
        # 2026/8/24新增特性系統後補上：見cli/traits.py模組docstring，這裡把「這場比賽
        # 會觸發的特性」加總成單一全場次百分比，維持engine/race.py既有算法完全不變。
        tactic_volatility_pct=tactic_volatility,
        random_volatility_pct=random.uniform(-0.10, 0.10),
        tactic_stamina_multiplier=tactic_stamina_mult,
    )


@dataclass
class RaceEntry:
    horse: Horse
    grade: str
    tactic: str  # "自由發揮" | "保存體力"


def run_race(state: GameState, grade: str, entries: list[RaceEntry]) -> list[str]:
    """跑一場指定分級的比賽：玩家報名馬 + NPC假對手馬補滿賽事名額。

    回傳結果敘述文字列表（純文字結算，依 UI流程與遊戲迴圈.md 定案）。
    """
    entries = [e for e in entries if e.horse.can_race()]  # 防呆：受傷/退役的馬不應該出賽
    if not entries:
        return [f"=== {grade}：報名馬匹皆已受傷或退役，本場取消 ==="]

    field_size = A.GRADE_FIELD_SIZE[grade]
    player_inputs = [_horse_to_race_input(state, e.horse, e.tactic, grade) for e in entries]
    npc_count = max(0, field_size - len(player_inputs))
    npc_inputs = generate_opponents(grade, npc_count)
    all_inputs = player_inputs + npc_inputs

    results = simulate_race(all_inputs, distance_mod=1.0, terrain_mod=1.0)
    results_by_name = {r.name: r for r in results}

    lines = [f"=== {grade} 結果（{len(all_inputs)} 匹出賽）==="]
    for stage in ("起跑", "前段", "中段", "後段", "彎道", "衝刺"):
        leader = max(results, key=lambda r: next(s.position_value for s in r.stages if s.stage == stage))
        lines.append(f"[{stage}] 暫居領先：{leader.name}")

    ranked = sorted(results, key=lambda r: r.rank)
    lines.append("-- 最終名次 --")
    for r in ranked[: min(10, len(ranked))]:
        lines.append(f"{r.rank:>2}. {r.name}（位置值 {r.final_position_value:+.3f}）")

    prize_table = A.GRADE_PRIZE_TABLE[grade]
    for entry in entries:
        result = results_by_name[entry.horse.name]
        entry_fee = A.GRADE_ENTRY_FEE[grade]
        state.money -= entry_fee
        prize = 0.0
        if result.rank <= len(prize_table):
            gross = prize_table[result.rank - 1]
            prize = gross * (1 - A.STAFF_CUT_RATE)
            state.money += prize
            entry.horse.money_earned += prize
            entry.horse.fame += A.FAME_GAIN_BY_GRADE[grade] * (len(prize_table) - result.rank + 1) / len(prize_table)
        entry.horse.fatigue = min(100.0, entry.horse.fatigue + A.RACE_FATIGUE_GAIN)
        entry.horse.career_starts += 1  # 生涯出賽次數，新馬賽資格判定(從未參賽)靠這個欄位
        if grade in ("新馬賽", "未勝利賽") and result.rank == 1 and not entry.horse.graduated:
            # 2026/8/23使用者決定：新馬賽或未勝利賽奪冠即「畢業」，取得報名一般賽事的資格，
            # 且永久不能再回頭報名新馬賽/未勝利賽(見 eligible_grades)。
            entry.horse.graduated = True
        entry.horse.raced_this_week = True  # 供本週roll_weekly_injuries判斷比賽週加成
        # +1是刻意的：這次結算稍後會呼叫一次 apply_weekly_race_cooldown_recovery()把所有
        # 馬匹的冷卻週數倒數1週(包含這匹馬剛設定的新值)，要多留1週緩衝，倒數後才會精準
        # 對應「接下來2週不可參賽」(賽事與生涯系統.md，2026/8/23使用者決定)。
        entry.horse.race_cooldown_weeks_remaining = A.RACE_COOLDOWN_WEEKS + 1
        growth_total = apply_race_experience_growth(state, entry.horse, grade)
        league_points = L.league_points_for_result(grade, result.rank)
        league_note = ""
        if league_points:
            state.league_points += league_points
            if result.rank == 1 and grade in state.league_win_counts:
                state.league_win_counts[grade] += 1
            league_note = f"｜聯盟積分+{league_points}"
            # 2026/8/25使用者決定補上馬主聯盟系統(見cli/league.py模組docstring)：只有
            # 地方三級賽以上/國際賽事會產生積分，league_points_for_result()對不計分的
            # 分級/名次一律回傳0，這裡用if league_points過濾掉不計分的情況。
        log_line = (
            f"{entry.horse.name}：第{result.rank}名｜報名費-{entry_fee:.0f}｜"
            f"獎金+{prize:.0f}（已扣人員分成）｜名氣+{entry.horse.fame:.1f}｜"
            f"比賽經驗成長 合計+{growth_total:.2f}{league_note}"
        )
        entry.horse.race_log.append(f"第{state.week}週 {grade} 第{result.rank}名")
        lines.append(log_line)

    return lines


def apply_race_experience_growth(state: "GameState", horse: Horse, grade: str) -> float:
    """出賽本身也帶來小幅屬性成長（不論名次），對應 RACE_GROWTH_BASE_BY_GRADE 的假設值。

    套用跟週間訓練同一套潛力餘裕公式，只是基礎值遠低於週間訓練，所以主要作用是
    「拉高高潛力馬長期能摸到的上限」，不會取代週間訓練的主要成長來源。回傳本次
    出賽總共增加的屬性點數(所有可訓練屬性合計)，供 UI 顯示。

    比賽經驗成長代表馬匹自身出賽歷練，跟訓練師的專長指導無關，所以固定用1.0倍率，
    不吃 trainer_effective_multiplier（訓練師系統.md：訓練師是「聘來訓練」，不是
    比賽當天在場邊指導）。
    """
    base = A.RACE_GROWTH_BASE_BY_GRADE[grade]
    status = A.state_grade(horse.stats["健康"], horse.fatigue)
    status_mult = {"S": 1.2, "A": 1.1, "B": 1.0, "C": 0.9, "D": 0.8}[status]
    total_growth = 0.0
    for stat in TRAINABLE_STATS:
        before = horse.stats[stat]
        after = apply_training(
            base_training_value=base,
            potential_cap=horse.potential_cap,
            current_value=before,
            age_stage_multiplier=G.age_stage_multiplier(horse.growth_curve, horse.age),
            trainer_multiplier=1.0,
            facility_multiplier=facility_effective_multiplier(state, stat),
            status_multiplier=status_mult,
        )
        horse.stats[stat] = after
        total_growth += after - before
    return total_growth


# ------------------------------------------------------------------ 週結算

def apply_weekly_passive_recovery(state: GameState) -> None:
    """每週結算時，所有馬匹額外回復一點疲勞（不論本週選了訓練或休息）。

    代表訓練/比賽之外的日常靜養時間，避免「訓練選項8個裡只有1個是休息」導致
    疲勞值只漲不跌、很快頂到100（見 assumptions.py 的調整依據說明）。

    指定了「狀態管理」專長訓練師的馬，額外多回復一些（訓練師系統.md「狀態管理」專長）。
    """
    facility_bonus = facility_fatigue_relief_bonus(state.facility_levels["恢復中心"])
    for horse in state.horses:
        trainer = state.trainer_by_name(horse.assigned_trainer)
        bonus = fatigue_relief_bonus(trainer) + facility_bonus
        horse.fatigue = max(0.0, horse.fatigue - A.WEEKLY_PASSIVE_FATIGUE_RECOVERY - bonus)


def hire_trainer(state: GameState, trainer: Trainer) -> str:
    """從訓練師市場聘用一名訓練師：支付一次性聘用費，之後每週固定支付薪水。"""
    if any(t.name == trainer.name for t in state.trainers):
        return f"已經聘用過 {trainer.name}，不能重複聘用"
    if state.money < trainer.hire_fee:
        return f"資金不足，無法聘用 {trainer.name}（需要聘用費 {trainer.hire_fee:,.0f}）"
    state.money -= trainer.hire_fee
    state.trainers.append(trainer)
    return (
        f"聘用 {trainer.name}（{trainer.specialty} Lv{trainer.skill_level}）："
        f"支付聘用費 {trainer.hire_fee:,.0f}，之後每週薪水 {trainer.weekly_salary:,.0f}"
    )


def assign_trainer(state: GameState, horse: Horse, trainer_name: str | None) -> str:
    """把已聘用的訓練師指定給一匹馬（或傳 None 取消指定）。

    訓練師系統.md：一個馬匹最多指定一個訓練師，一個訓練師最佳管理8匹馬，
    9~12匹時效率下降（見 trainers.capacity_multiplier），13匹以上無法再指定。
    """
    if trainer_name is None:
        horse.assigned_trainer = None
        return f"{horse.name} 取消指定訓練師"

    trainer = state.trainer_by_name(trainer_name)
    if trainer is None:
        return f"尚未聘用訓練師「{trainer_name}」，無法指定"

    already_assigned = sum(
        1 for h in state.horses if h.assigned_trainer == trainer_name and h.name != horse.name
    )
    from .trainers import MAX_HORSES_REDUCED_EFFICIENCY, can_assign

    if not can_assign(already_assigned):
        return f"{trainer.name} 已管理達上限（{MAX_HORSES_REDUCED_EFFICIENCY}匹），無法再指定"

    horse.assigned_trainer = trainer_name
    return f"{horse.name} 指定訓練師：{trainer.name}"


def fire_trainer(state: GameState, trainer_name: str) -> str:
    """解雇一名已聘用的訓練師，削減人力成本：之後不再支付這名訓練師的週薪。

    原本指定給這名訓練師的馬匹會一併取消指定(訓練倍率回到沒有訓練師的基礎值1.0)。
    不退還當初的聘用費(視為沉沒成本)。
    """
    trainer = state.trainer_by_name(trainer_name)
    if trainer is None:
        return f"尚未聘用訓練師「{trainer_name}」，無法解雇"

    state.trainers.remove(trainer)
    affected = [h.name for h in state.horses if h.assigned_trainer == trainer_name]
    for horse in state.horses:
        if horse.assigned_trainer == trainer_name:
            horse.assigned_trainer = None

    msg = f"解雇 {trainer.name}，之後每週省下薪水 {trainer.weekly_salary:,.0f}"
    if affected:
        msg += f"（原指定的{len(affected)}匹馬已取消指定：{'、'.join(affected)}）"
    return msg


def hire_vet(state: GameState, vet: Vet) -> str:
    """從獸醫市場聘用一名獸醫：支付一次性聘用費，之後每週固定支付薪水。"""
    if any(v.name == vet.name for v in state.vets):
        return f"已經聘用過 {vet.name}，不能重複聘用"
    if state.money < vet.hire_fee:
        return f"資金不足，無法聘用 {vet.name}（需要聘用費 {vet.hire_fee:,.0f}）"
    state.money -= vet.hire_fee
    state.vets.append(vet)
    return (
        f"聘用 {vet.name}（Lv{vet.skill_level}）：支付聘用費 {vet.hire_fee:,.0f}，"
        f"之後每週薪水 {vet.weekly_salary:,.0f}"
    )


def assign_vet(state: GameState, horse: Horse, vet_name: str | None) -> str:
    """把已聘用的獸醫指定給一匹馬（或傳 None 取消指定）。

    員工系統.md：一個獸醫最佳照顧5匹馬，6~8匹時治療效率下降，9匹以上無法再指定。
    """
    if vet_name is None:
        horse.assigned_vet = None
        return f"{horse.name} 取消指定獸醫"

    vet = state.vet_by_name(vet_name)
    if vet is None:
        return f"尚未聘用獸醫「{vet_name}」，無法指定"

    already_assigned = sum(
        1 for h in state.horses if h.assigned_vet == vet_name and h.name != horse.name
    )
    if not vet_can_assign(already_assigned):
        return f"{vet.name} 已照顧達上限（{VET_MAX_HORSES_REDUCED_EFFICIENCY}匹），無法再指定"

    horse.assigned_vet = vet_name
    return f"{horse.name} 指定獸醫：{vet.name}"


def fire_vet(state: GameState, vet_name: str) -> str:
    """解雇一名已聘用的獸醫，削減人力成本：之後不再支付這名獸醫的週薪。

    原本指定給這名獸醫的馬匹會一併取消指定(傷病仍會自然恢復，只是沒有加速跟預防加成)。
    不退還當初的聘用費(視為沉沒成本)。
    """
    vet = state.vet_by_name(vet_name)
    if vet is None:
        return f"尚未聘用獸醫「{vet_name}」，無法解雇"

    state.vets.remove(vet)
    affected = [h.name for h in state.horses if h.assigned_vet == vet_name]
    for horse in state.horses:
        if horse.assigned_vet == vet_name:
            horse.assigned_vet = None

    msg = f"解雇 {vet.name}，之後每週省下薪水 {vet.weekly_salary:,.0f}"
    if affected:
        msg += f"（原指定的{len(affected)}匹馬已取消指定：{'、'.join(affected)}）"
    return msg


# ------------------------------------------------------------------ 馬房/育馬場容量

def _stable_capacity(state: "GameState") -> int:
    return facility_stable_capacity(state.facility_levels["馬房"])


def _stud_farm_capacity(state: "GameState") -> int:
    return facility_stud_farm_capacity(state.facility_levels["育馬場"])


def _stud_farm_occupied(state: "GameState", exclude: Horse | None = None) -> int:
    """目前登記為種馬/繁殖母馬的馬匹數(供育馬場容量檢查用)。exclude用在
    assign_breeding_role()重新登記同一匹馬時，不把牠自己算進「已佔用」裡。"""
    return sum(1 for h in state.horses if h.breeding_role is not None and h is not exclude)


# ------------------------------------------------------------------ 現役馬市場

def buy_horse(state: GameState, horse_name: str) -> str:
    """從市場買下一匹待售馬，加入玩家馬房(cli/horse_market.py，2026/8/23使用者決定新增)。

    價格固定按 horse_market_value() 現場算(簡化版拍賣，見該模組docstring)，資金不足時
    直接跳過不丟例外(比照hire_trainer/hire_vet的防呆風格)。買下後這匹馬會有自己的騎師
    (比照new_game()開局配置的隨機生成方式)，並從市場清單移除(不像訓練師/獸醫市場那樣
    留在清單裡等被指定——馬匹本身就是資產，買下代表這隻馬離開市場、進了玩家馬房)。

    2026/8/25使用者決定補上馬房容量系統後，購買前會先檢查馬房是否還有空位(見
    cli/facilities.py stable_capacity_for_level())，滿了就擋下購買。
    """
    horse = next((h for h in state.horse_market if h.name == horse_name), None)
    if horse is None:
        return f"市場上找不到「{horse_name}」，可能已經被買走或市場剛好刷新了"

    cap = _stable_capacity(state)
    if len(state.horses) >= cap:
        return f"馬房已滿(Lv{state.facility_levels['馬房']}，上限{cap}匹)，需要先升級馬房或賣掉/淘汰馬匹才能買下{horse.name}"

    price = horse_market_value(horse)
    if state.money < price:
        return f"資金不足，買不起{horse.name}（需要{price:,.0f}，目前只有{state.money:,.0f}）"

    state.money -= price
    state.horse_market = [h for h in state.horse_market if h.name != horse.name]
    state.horses.append(horse)
    state.jockeys[horse.name] = Jockey(
        correction=round(random.uniform(0.95, 1.08), 3),
        position_judgement=round(random.uniform(55, 85), 1),
        rhythm_control=round(random.uniform(55, 85), 1),
        route_choice=round(random.uniform(55, 85), 1),
    )
    return f"買下了{horse.name}！花費{price:,.0f}，目前馬房共有{len(state.horses)}匹馬"


def _buy_breeding_stock(
    state: GameState, market_attr: str, horse_name: str, label: str
) -> str:
    """種馬市場/繁殖母馬市場/幼駒市場共用的購買邏輯(2026/8/24使用者決定補上，見
    cli/horse_market.py模組docstring)：跟buy_horse()一樣「從市場清單移除+加入馬房+
    配發新騎師」，差別是種馬/繁殖母馬用breeding_stock_value()定價(已經retired=True、
    breeding_role已設定好，買回家立刻能配種)，幼駒則跟現役馬市場一樣用market_value()。

    2026/8/25使用者決定補上容量系統後，購買前會先檢查馬房空位；如果這匹馬本身已經
    帶著種馬/繁殖母馬角色(種馬市場/繁殖母馬市場的馬買回家就直接能配種)，還要多檢查
    一次育馬場空位，兩者都滿了就擋下購買(見cli/facilities.py模組docstring)。
    """
    market_list: list[Horse] = getattr(state, market_attr)
    horse = next((h for h in market_list if h.name == horse_name), None)
    if horse is None:
        return f"{label}市場上找不到「{horse_name}」，可能已經被買走或市場剛好刷新了"

    stable_cap = _stable_capacity(state)
    if len(state.horses) >= stable_cap:
        return f"馬房已滿(Lv{state.facility_levels['馬房']}，上限{stable_cap}匹)，需要先升級馬房或賣掉/淘汰馬匹才能買下{horse.name}"
    if horse.breeding_role is not None:
        stud_cap = _stud_farm_capacity(state)
        if _stud_farm_occupied(state) >= stud_cap:
            return f"育馬場已滿(Lv{state.facility_levels['育馬場']}，上限{stud_cap}匹)，需要先升級育馬場或取消其他種馬/繁殖母馬的登記才能買下{horse.name}"

    price = horse_breeding_stock_value(horse) if horse.breeding_role else horse_market_value(horse)
    if state.money < price:
        return f"資金不足，買不起{horse.name}（需要{price:,.0f}，目前只有{state.money:,.0f}）"

    state.money -= price
    setattr(state, market_attr, [h for h in market_list if h.name != horse.name])
    state.horses.append(horse)
    state.jockeys[horse.name] = Jockey(
        correction=round(random.uniform(0.95, 1.08), 3),
        position_judgement=round(random.uniform(55, 85), 1),
        rhythm_control=round(random.uniform(55, 85), 1),
        route_choice=round(random.uniform(55, 85), 1),
    )
    role_note = f"，已登記為{horse.breeding_role}，可直接配種" if horse.breeding_role else ""
    return f"買下了{horse.name}（{label}）！花費{price:,.0f}{role_note}，目前馬房共有{len(state.horses)}匹馬"


def buy_foal(state: GameState, horse_name: str) -> str:
    return _buy_breeding_stock(state, "foal_market", horse_name, "幼駒")


def buy_stallion(state: GameState, horse_name: str) -> str:
    return _buy_breeding_stock(state, "stallion_market", horse_name, "種馬")


def buy_broodmare(state: GameState, horse_name: str) -> str:
    return _buy_breeding_stock(state, "broodmare_market", horse_name, "繁殖母馬")


def sell_horse(state: GameState, horse_name: str) -> str:
    """把玩家馬房裡的一匹馬賣掉換錢(cli/horse_market.py)。

    賣價一樣用 horse_market_value() 現場算(固定開價，沒有議價/haircut)，不限制馬匹狀態
    (受傷/冷卻中/退役都能賣)——賣掉後這匹馬從state.horses跟state.jockeys一併移除，
    原本指定的訓練師/獸醫欄位是這匹馬自己身上的資料，隨馬匹一起消失，不用額外清理
    trainer/vet那邊的清單(容量計算是逐週用state.horses現場數，不會有殘留參照)。沒有
    限制不能賣到剩0匹馬——MVP沒有「馬房容量下限」的概念，玩家清空馬房只是沒馬可訓練/
    比賽，不會讓遊戲迴圈出錯。
    """
    horse = next((h for h in state.horses if h.name == horse_name), None)
    if horse is None:
        return f"找不到「{horse_name}」，可能已經賣掉了"

    price = horse_market_value(horse)
    state.money += price
    state.horses = [h for h in state.horses if h.name != horse_name]
    state.jockeys.pop(horse_name, None)
    return f"賣掉了{horse.name}，收入{price:,.0f}"


def retire_horse(state: GameState, horse_name: str) -> str:
    """把一匹還沒退役的馬手動退役(馬匹成長.md「若馬匹比賽表現不如預期或本身不適合比賽，
    可將其直接退役」)。之前退役只會在重傷時自動觸發(見 roll_weekly_injuries)，這裡補上
    玩家可以主動退役的管道，2026/8/24使用者新增繁殖系統時一併補上——繁殖系統要求「先
    退役才能登記為種馬/繁殖母馬」(見 assign_breeding_role)，沒有這個函式玩家會完全無法
    使用繁殖系統(除非等重傷機率隨機命中)。

    退役後自動取消指定的訓練師/獸醫(這匹馬不會再訓練，繼續佔用訓練師/獸醫的管理容量
    沒有意義)；沒有退款/懲罰，比照 fire_trainer/fire_vet 的簡化精神。
    """
    horse = next((h for h in state.horses if h.name == horse_name), None)
    if horse is None:
        return f"找不到「{horse_name}」"
    if horse.retired:
        return f"{horse.name} 已經是退役狀態"

    horse.retired = True
    horse.assigned_trainer = None
    horse.assigned_vet = None
    return f"{horse.name} 正式退役，之後可以考慮登記為種馬/繁殖母馬（血統與繁殖系統.md）"


# ------------------------------------------------------------------ 繁殖/遺傳

def assign_breeding_role(state: GameState, horse_name: str, role: str | None) -> str:
    """把一匹已退役的馬登記為種馬(role="種馬")或繁殖母馬(role="繁殖母馬")，或取消登記
    (role=None)。血統與繁殖系統.md：3~12歲、已退役才能繁殖；種馬限公馬、繁殖母馬限母馬。

    2026/8/25使用者決定補上育馬場容量系統後，登記前(取消登記不受限)會先檢查育馬場是否
    還有空位，滿了就擋下登記。
    """
    horse = next((h for h in state.horses if h.name == horse_name), None)
    if horse is None:
        return f"找不到「{horse_name}」"

    if role is None:
        horse.breeding_role = None
        return f"{horse.name} 取消繁殖角色登記"

    if role not in ("種馬", "繁殖母馬"):
        return f"不支援的繁殖角色「{role}」"
    if not horse.retired:
        return f"{horse.name} 尚未退役，需先退役才能登記為{role}（血統與繁殖系統.md）"
    if not (A.BREEDING_MIN_AGE <= horse.age <= A.BREEDING_MAX_AGE):
        return f"{horse.name} 年齡{horse.age}歲不符合繁殖年齡範圍（{A.BREEDING_MIN_AGE}~{A.BREEDING_MAX_AGE}歲）"
    expected_sex = "公" if role == "種馬" else "母"
    if horse.sex != expected_sex:
        return f"{horse.name} 性別為{horse.sex}，不能登記為{role}"
    if horse.breeding_role != role:
        stud_cap = _stud_farm_capacity(state)
        occupied = _stud_farm_occupied(state, exclude=horse)
        if occupied >= stud_cap:
            return f"育馬場已滿(Lv{state.facility_levels['育馬場']}，上限{stud_cap}匹)，需要先升級育馬場或取消其他種馬/繁殖母馬的登記才能登記{horse.name}"

    horse.breeding_role = role
    return f"{horse.name} 登記為{role}"


def breed(state: GameState, mare_name: str, stallion_name: str) -> str:
    """讓一匹已登記的繁殖母馬跟一匹已登記的種馬配種(簡化版，見 cli/breeding.py 模組
    docstring：不分自然交配/人工授精，扣固定成本後判定成功率，成功則進入產駒期倒數)。
    """
    mare = next((h for h in state.horses if h.name == mare_name), None)
    if mare is None:
        return f"找不到「{mare_name}」"
    stallion = next((h for h in state.horses if h.name == stallion_name), None)
    if stallion is None:
        return f"找不到「{stallion_name}」"

    if mare.breeding_role != "繁殖母馬":
        return f"{mare.name} 不是登記中的繁殖母馬，無法配種"
    if stallion.breeding_role != "種馬":
        return f"{stallion.name} 不是登記中的種馬，無法配種"
    if mare.pregnant_weeks_remaining > 0:
        return f"{mare.name} 已經懷孕中，還要等{mare.pregnant_weeks_remaining}週才會生產"
    if mare.breeding_cooldown_weeks_remaining > 0:
        return f"{mare.name} 還在配種恢復期，還要等{mare.breeding_cooldown_weeks_remaining}週才能再嘗試"
    if not (A.BREEDING_MIN_AGE <= mare.age <= A.BREEDING_MAX_AGE):
        return f"{mare.name} 年齡{mare.age}歲已不符合繁殖年齡範圍（{A.BREEDING_MIN_AGE}~{A.BREEDING_MAX_AGE}歲）"
    if not (A.BREEDING_MIN_AGE <= stallion.age <= A.BREEDING_MAX_AGE):
        return f"{stallion.name} 年齡{stallion.age}歲已不符合繁殖年齡範圍（{A.BREEDING_MIN_AGE}~{A.BREEDING_MAX_AGE}歲）"
    if state.money < A.BREEDING_COST:
        return f"資金不足，無法支付配種成本（需要{A.BREEDING_COST:,.0f}）"

    state.money -= A.BREEDING_COST
    mare.breeding_cooldown_weeks_remaining = A.BREEDING_ATTEMPT_COOLDOWN_WEEKS
    # 種馬本身沒有冷卻(血統與繁殖系統.md「種馬一年可無限制進行繁殖」)，這裡刻意跳過doc
    # 提到的「過度繁殖影響精液品質/疲勞」細節，屬於這次簡化範圍先不做的部分。

    if random.random() >= A.BREEDING_SUCCESS_CHANCE:
        return f"{mare.name} × {stallion.name} 配種失敗，本次未受孕（花費{A.BREEDING_COST:,.0f}）"

    mare.pregnant_weeks_remaining = A.GESTATION_WEEKS
    mare.pregnant_sire_name = stallion.name
    mare.pregnant_sire_stats = dict(stallion.stats)
    mare.pregnant_sire_potential_cap = stallion.potential_cap
    mare.pregnant_sire_traits = list(stallion.traits)
    mare.pregnant_sire_personality = stallion.personality
    mare.pregnant_inbred = _is_inbred(mare, stallion)
    inbred_note = "（血緣相近，之後可能出現近親繁殖的負面影響）" if mare.pregnant_inbred else ""
    return (
        f"{mare.name} × {stallion.name} 配種成功！花費{A.BREEDING_COST:,.0f}，"
        f"預計{A.GESTATION_WEEKS}週後生產{inbred_note}"
    )


def apply_weekly_pregnancy_progression(state: GameState) -> list[str]:
    """本週結算：懷孕中的母馬產駒期倒數，倒數到0時生產一匹新幼駒加入馬房；同時所有馬匹
    的配種恢復冷卻也一併倒數(比照 apply_weekly_race_cooldown_recovery 的模式)。

    這個函式每週結算都要呼叫一次(不論這週有沒有馬懷孕/配種)，是產駒期/配種冷卻倒數
    唯一的遞減入口(webapp/cli/財務驗證工具三處呼叫點都要記得呼叫)。
    """
    lines: list[str] = []
    existing_names = {h.name for h in state.horses}
    for horse in state.horses:
        if horse.breeding_cooldown_weeks_remaining > 0:
            horse.breeding_cooldown_weeks_remaining -= 1

        if horse.pregnant_weeks_remaining <= 0:
            continue
        horse.pregnant_weeks_remaining -= 1
        if horse.pregnant_weeks_remaining > 0:
            continue

        foal, note = generate_foal(
            mare=horse,
            sire_stats=horse.pregnant_sire_stats,
            sire_potential_cap=horse.pregnant_sire_potential_cap,
            sire_name=horse.pregnant_sire_name,
            sire_traits=horse.pregnant_sire_traits or [],
            sire_personality=horse.pregnant_sire_personality,
            inbred=horse.pregnant_inbred,
            existing_names=existing_names,
        )
        sire_name = horse.pregnant_sire_name
        inbred = horse.pregnant_inbred
        horse.pregnant_sire_name = None
        horse.pregnant_sire_stats = None
        horse.pregnant_sire_potential_cap = None
        horse.pregnant_sire_traits = None
        horse.pregnant_sire_personality = None
        horse.pregnant_inbred = False

        state.horses.append(foal)
        state.jockeys[foal.name] = Jockey(
            correction=round(random.uniform(0.95, 1.08), 3),
            position_judgement=round(random.uniform(55, 85), 1),
            rhythm_control=round(random.uniform(55, 85), 1),
            route_choice=round(random.uniform(55, 85), 1),
        )
        inbred_note = "（近親繁殖）" if inbred else ""
        lines.append(f"{horse.name} 生下幼駒「{foal.name}」！父：{sire_name}{inbred_note}{note}")
    return lines


def upgrade_facility(state: GameState, facility_name: str) -> str:
    """把指定設施升一級：支付一次性資本支出，之後訓練/恢復效果立即生效（沒有像
    訓練師/獸醫那樣的持續週薪，跟聘用人力形成不同的投資型態對照，設施系統.md）。
    """
    if facility_name not in state.facility_levels:
        return f"沒有這個設施「{facility_name}」"

    current_level = state.facility_levels[facility_name]
    if current_level >= FACILITY_MAX_LEVEL:
        return f"{facility_name} 已經是最高等級(Lv{FACILITY_MAX_LEVEL})，無法再升級"

    cost = facility_upgrade_cost(current_level)
    if state.money < cost:
        return f"資金不足，無法升級 {facility_name}（需要 {cost:,.0f}）"

    state.money -= cost
    state.facility_levels[facility_name] = current_level + 1
    return (
        f"{facility_name} 升級到 Lv{current_level + 1}，支付 {cost:,.0f}"
        f"（一次性支出，之後沒有額外週薪）"
    )


def _apply_permanent_injury_penalty(horse: Horse, injury: Injury) -> None:
    """中傷/重傷依受傷部位對應屬性造成一次性永久減損（狀態與健康.md）。"""
    pct = SEVERITY_PERMANENT_PENALTY_PCT[injury.severity]
    if pct <= 0 or not injury.affected_stats:
        return
    for stat in injury.affected_stats:
        horse.stats[stat] = max(1.0, horse.stats[stat] * (1 - pct))


def roll_weekly_injuries(state: GameState) -> list[str]:
    """本週傷病判定：對還沒受傷、還沒退役的馬各自判定一次是否觸發新傷病。

    對重傷額外判定退役機率；中/重傷立即套用永久減損。回傳結果敘述文字列表
    (沒有任何馬觸發時回傳空列表)。

    2026/8/23使用者決定「賽事改成每週一次」之前，比賽週的傷病風險加成
    (INJURY_RACE_WEEK_BONUS)是用一個全域flag(is_racing_this_week)套用在「所有」還沒
    受傷退役的馬身上——3級距時代這個近似還算合理，因為比賽週本來就少(每4週一次)、
    符合資格的馬通常也都會報名。改成每週開賽、且出賽後有2週冷卻後，同一週裡大部分馬
    其實都在冷卻中或選擇不出賽，如果還套用全域flag等於「沒出賽的馬也要吃出賽的傷病
    風險」，明顯不合理。因此改成讀每匹馬自己的 `raced_this_week`(由 run_race() 設定，
    只有真的出賽的馬才是True)，只有真的出賽的馬才會加這個風險。
    """
    lines: list[str] = []
    for horse in state.horses:
        if horse.retired or horse.injury is not None:
            continue

        vet = state.vet_by_name(horse.assigned_vet)
        recent_light = (
            horse.recent_light_injury_week is not None
            and state.week - horse.recent_light_injury_week <= RECENT_LIGHT_INJURY_WINDOW_WEEKS
        )
        injury = roll_injury(
            health=horse.stats["健康"],
            fatigue=horse.fatigue,
            is_racing_this_week=horse.raced_this_week,
            recent_light_injury=recent_light,
            vet=vet,
        )
        if injury is None:
            continue

        if injury.severity == "輕傷":
            horse.recent_light_injury_week = state.week

        _apply_permanent_injury_penalty(horse, injury)

        if injury.severity == "重傷" and random.random() < SEVERITY_RETIREMENT_CHANCE[injury.severity]:
            horse.retired = True
            horse.injury = None
            lines.append(f"{horse.name}：觸發重傷「{injury.name}」，傷勢過重，宣告退役")
            continue

        horse.injury = injury
        penalty_note = ""
        if injury.affected_stats and SEVERITY_PERMANENT_PENALTY_PCT[injury.severity] > 0:
            penalty_note = f"，永久減損：{'、'.join(injury.affected_stats)}"
        lines.append(
            f"{horse.name}：觸發{injury.severity}「{injury.name}」，"
            f"預計休養{injury.weeks_remaining}週{penalty_note}"
        )
    return lines


def apply_weekly_injury_recovery(state: GameState) -> list[str]:
    """本週結算：所有正在養傷的馬，傷病週數倒數，倒數完畢時解除傷病狀態、恢復可訓練/可比賽。"""
    lines: list[str] = []
    for horse in state.horses:
        if horse.injury is None:
            continue
        vet = state.vet_by_name(horse.assigned_vet)
        assigned_count = (
            sum(1 for h in state.horses if h.assigned_vet == horse.assigned_vet)
            if horse.assigned_vet
            else 0
        )
        ticks = recovery_weeks_per_tick(vet, assigned_count) + facility_injury_recovery_bonus(
            state.facility_levels["醫療中心"]
        )
        horse.injury.weeks_remaining -= ticks
        if horse.injury.weeks_remaining <= 0:
            lines.append(f"{horse.name}：「{horse.injury.name}」傷勢痊癒，獸醫確認可以恢復訓練/比賽")
            horse.injury = None
    return lines


def apply_weekly_race_cooldown_recovery(state: GameState) -> None:
    """本週結算：出賽冷卻中的馬匹冷卻週數倒數1週；並重置「這週是否出賽過」的暫存旗標。

    2026/8/23使用者決定：賽事改成每週一次，馬匹出賽後接下來2週不可再參賽(見
    Horse.race_cooldown_weeks_remaining)。這個函式每週結算都要呼叫一次(不論這週有沒有
    馬出賽)，是這個倒數機制唯一的遞減入口。`raced_this_week` 的重置也放在這裡一起做，
    確保下一週開始時這個旗標是乾淨的(run_race() 會在馬匹真的出賽時重新設回True)。
    """
    for horse in state.horses:
        if horse.race_cooldown_weeks_remaining > 0:
            horse.race_cooldown_weeks_remaining -= 1
        horse.raced_this_week = False


def apply_weekly_age_progression(state: GameState) -> list[str]:
    """本週結算：滿A.WEEKS_PER_YEAR(52)週時，所有未退役馬匹年齡+1歲。

    2026/8/23使用者決定新增馬匹年齡系統：MVP簡化把「一年」直接對應52個遊戲週，開局
    5匹測試馬都同時起算(同一批「出生」)，所以固定每滿52週整批一起長一歲，不用替每匹馬
    分別追蹤生日。用 state.week % WEEKS_PER_YEAR == 0 判斷「這週剛好滿一年」，跟
    apply_weekly_race_cooldown_recovery一樣、要在 state.week 遞增到下一週之前呼叫，
    才會精準對應「滿52週」這個時間點(第52週結算時觸發，第53週開局就是新的歲數)。
    退役馬不再計算年齡增長(對玩法沒有意義，也避免無謂的資料變動)。若一匹從未出賽的馬
    在本次結算後超過新馬賽年齡，立即自動退役並清除訓練師/獸醫指派；繁殖角色保持None，
    由玩家之後在繁殖頁面或CLI選擇登記為種馬/繁殖母馬，或維持一般退役狀態。
    """
    if state.week % A.WEEKS_PER_YEAR != 0:
        return []
    lines = []
    for horse in state.horses:
        if horse.retired:
            continue
        horse.age += 1
        lines.append(f"{horse.name}：滿{A.WEEKS_PER_YEAR}週，年齡增長為{horse.age}歲")
        if horse.age > A.MAIDEN_RACE_AGE and horse.career_starts == 0:
            retire_horse(state, horse.name)
            lines.append(
                f"{horse.name}：已錯過新馬賽年齡且從未出賽，自動退役；"
                "請選擇退役路線（種馬/繁殖母馬或維持一般退役）"
            )
    return lines


def apply_weekly_league_season_progression(state: GameState) -> list[str]:
    """本週結算：滿A.WEEKS_PER_YEAR(52)週時的馬主聯盟賽季結算——生成虛擬對手、排名、
    升降級判定、Top3追加獎勵，然後重置本季積分/冠軍數，開始下一季(見cli/league.py
    模組docstring)。跟apply_weekly_age_progression同一個「滿52週」判斷時機，比照它的
    呼叫模式接進webapp/cli/財務驗證工具三處呼叫點。
    """
    if state.week % A.WEEKS_PER_YEAR != 0:
        return []

    result = L.resolve_season(state.league_tier, state.league_points, state.league_win_counts)
    lines = [
        f"【馬主聯盟】{L.TIER_NAMES[state.league_tier]}賽季結束："
        f"第{result['rank']}/{result['field_size']}名，積分{state.league_points:.0f}"
    ]
    if result["promoted"]:
        lines.append(f"　→ 升級至{L.TIER_NAMES[result['new_tier']]}！")
    elif result["relegated"]:
        lines.append(f"　→ 降級至{L.TIER_NAMES[result['new_tier']]}")
    else:
        lines.append(f"　→ 留在{L.TIER_NAMES[result['new_tier']]}")
    if result["top3"]:
        bonus_money = L.TOP3_BONUS_MONEY[state.league_tier]
        state.money += bonus_money
        lines.append(f"　【本季前3名】獲得追加獎金{bonus_money:,.0f}與額外馬主聲望")
        # 「額外馬主聲望」doc有提到但這次沒有獨立的馬主聲望數值欄位(見cli/league.py
        # 模組docstring：不做「事業等級」)，這裡只發追加獎金，聲望純敘事文字。

    state.league_last_season_result = "\n".join(lines)
    state.league_tier = result["new_tier"]
    state.league_points = 0.0
    state.league_win_counts = {g: 0 for g in L.TIEBREAK_GRADES}
    return lines


def apply_weekly_stat_decline(state: GameState) -> list[str]:
    """本週結算：處於「衰退期」的馬匹，9項可衰退屬性(排除智力/精神)各自小幅衰退。

    2026/8/24使用者決定補回GDD 3.6完整版成長曲線後新增：doc「大部分能力會隨著年齡增長
    退化...衰退期：能力開始下降，需要更多維護」。跟 apply_weekly_age_progression 不同，
    這裡刻意不排除已退役馬——退役種馬/繁殖母馬的屬性快照會被之後配種的 breed() 直接拿去
    生成幼駒(見 cli/breeding.py generate_foal)，讓退役種馬持續老化衰退是刻意的設計，
    不是漏改。只排除還在懷孕/沒有意義的邊界情況一律照跑，沒有特別排除。

    衰退速率吃 cli/growth.py 的個體差異(根性/健康)公式，並疊加恢復中心設施等級的
    減緩倍率(facilities.decline_mitigation_for_level)——doc提到的「獸醫照護」「降低
    比賽/訓練強度」兩個額外減緩管道這次先跳過，只做設施這一個(見 decline_mitigation_
    for_level 說明)。
    """
    lines = []
    for horse in state.horses:
        if horse.growth_stage() != "衰退期":
            continue
        mitigation = facility_decline_mitigation(state.facility_levels["恢復中心"])
        # 用衰退前的根性/健康快照決定本週個體差異係數，避免同一週內先衰退的屬性
        # (剛好可能就是根性/健康本身)影響到後面才算的屬性，讓同一週內每項屬性站在
        # 同一個基準點上。
        guts0 = horse.stats["根性"]
        health0 = horse.stats["健康"]
        total_loss = 0.0
        for stat in ALL_STATS:
            if stat in G.DECLINE_EXEMPT_STATS:
                continue
            rate = G.weekly_decline_rate(guts0, health0, mitigation)
            loss = horse.stats[stat] * rate
            horse.stats[stat] = max(1.0, horse.stats[stat] - loss)
            total_loss += loss
        if total_loss > 0:
            lines.append(f"{horse.name}：已進入衰退期，本週屬性合計衰退{total_loss:.2f}點")
    return lines


def weekly_upkeep(state: GameState, training_sessions: int) -> str:
    apply_weekly_passive_recovery(state)
    salary_cost = sum(t.weekly_salary for t in state.trainers) + sum(v.weekly_salary for v in state.vets)
    cost = A.STABLE_WEEKLY_COST + training_sessions * A.TRAINING_COST_PER_SESSION + salary_cost
    state.money -= cost
    msg = (
        f"本週固定支出：馬房費 {A.STABLE_WEEKLY_COST:.0f} + "
        f"訓練費 {training_sessions}x{A.TRAINING_COST_PER_SESSION:.0f}"
    )
    if salary_cost:
        msg += f" + 訓練師/獸醫薪水 {salary_cost:.0f}"
    msg += f" = {cost:.0f}"
    if state.money <= A.BANKRUPTCY_THRESHOLD:
        state.bankrupt = True
    return msg
