#!/usr/bin/env python3
"""互動式 CLI 原型 — 依 docs/MVP範圍.md「MVP遊戲流程(精簡版)」跑核心迴圈。

執行：
    python3 -m cli.play              # 互動模式，預設玩16週
    python3 -m cli.play --weeks 12   # 指定週數
    python3 -m cli.play --auto       # 自動demo模式(不需輸入，AI亂數代打，用來快速看流程/除錯)
"""
from __future__ import annotations

import argparse
import random

from . import assumptions as A
from .league import TIER_NAMES as LEAGUE_TIER_NAMES
from .game import (
    GameState,
    RaceEntry,
    apply_weekly_age_progression,
    apply_weekly_injury_recovery,
    apply_weekly_league_season_progression,
    apply_weekly_pregnancy_progression,
    apply_weekly_race_cooldown_recovery,
    apply_weekly_stat_decline,
    assign_breeding_role,
    assign_trainer,
    assign_vet,
    breed,
    buy_broodmare,
    buy_foal,
    buy_horse,
    buy_stallion,
    eligible_grades,
    hire_trainer,
    hire_vet,
    is_race_week,
    new_game,
    refresh_markets_if_due,
    rest_horse,
    retire_horse,
    roll_weekly_event,
    roll_weekly_injuries,
    run_race,
    sell_horse,
    train_horse,
    weekly_upkeep,
)
from .horse_market import breeding_stock_value as horse_breeding_stock_value
from .horse_market import market_value as horse_market_value
from .horses import TRAINABLE_STATS
from .trainers import generate_trainer_market
from .vets import generate_vet_market


def print_status(state: GameState) -> None:
    print(f"\n===== 第 {state.week} 週 ｜ 資金 {state.money:,.0f} =====")
    weeks_left = A.WEEKS_PER_YEAR - (state.week % A.WEEKS_PER_YEAR)
    print(f"馬主聯盟：{LEAGUE_TIER_NAMES[state.league_tier]} ｜ 本季積分 {state.league_points:.0f} ｜ 距賽季結算還有{weeks_left}週")
    for h in state.horses:
        grade = A.state_grade(h.stats["健康"], h.fatigue)
        trainer_note = f" 訓練師:{h.assigned_trainer}" if h.assigned_trainer else ""
        vet_note = f" 獸醫:{h.assigned_vet}" if h.assigned_vet else ""
        if h.retired:
            role_note = f"，登記為{h.breeding_role}" if h.breeding_role else ""
            status_note = f" 【已退役{role_note}】"
        elif h.injury is not None:
            status_note = f" 【養傷中:{h.injury.name}，剩{h.injury.weeks_remaining}週】"
        elif h.race_cooldown_weeks_remaining > 0:
            status_note = f" 【出賽冷卻中，還要{h.race_cooldown_weeks_remaining}週才能再出賽】"
        elif not h.can_train():
            status_note = f" 【幼駒，還未滿{A.MIN_TRAINING_AGE}歲不能訓練】"
        else:
            status_note = ""
        if h.pregnant_weeks_remaining > 0:
            status_note += f" 【懷孕中，還要{h.pregnant_weeks_remaining}週生產】"
        trait_note = f" 特性:{'/'.join(h.traits)}" if h.traits else ""
        personality_note = f" 個性:{h.personality}" if h.personality else ""
        print(
            f"  {h.name:<8}({h.sex}) {h.age}歲[{h.growth_curve}/{h.growth_stage()}] "
            f"評級{h.overall_rating():5.1f}/潛力{h.potential_cap:.0f} "
            f"疲勞{h.fatigue:5.1f} 狀態{grade} 名氣{h.fame:5.1f} 累積獎金{h.money_earned:,.0f}"
            f"{trainer_note}{vet_note}{status_note}{trait_note}{personality_note}"
        )


def setup_trainers(state: GameState, auto: bool) -> None:
    """開局前的訓練師市場：聘用0~N名訓練師，並指定給馬匹（可跳過，見訓練師系統.md）。"""
    market = generate_trainer_market(count=4)
    if auto:
        # --auto demo模式：固定聘用市場第一位，指定給第一匹馬，其餘跳過，方便快速看流程。
        if state.money >= market[0].hire_fee:
            print(hire_trainer(state, market[0]))
            print(assign_trainer(state, state.horses[0], market[0].name))
        return

    print("\n===== 訓練師市場 =====")
    for i, t in enumerate(market, 1):
        print(f"  {i}. {t.name}｜專長:{t.specialty} Lv{t.skill_level}｜聘用費{t.hire_fee:,.0f}｜週薪{t.weekly_salary:,.0f}")
    print("  0. 不聘用，直接開始")

    hired: list = []
    while True:
        raw = input("聘用編號（可重複輸入多個，Enter結束選擇）> ").strip()
        if not raw or raw == "0":
            break
        if raw.isdigit() and 1 <= int(raw) <= len(market):
            trainer = market[int(raw) - 1]
            print("  " + hire_trainer(state, trainer))
            hired.append(trainer)
        else:
            print("  請輸入有效編號。")

    if not hired:
        return

    print("\n將已聘用的訓練師指定給馬匹（可跳過某匹）：")
    for horse in state.horses:
        print(f"\n{horse.name} 可指定：" + "、".join(f"{i + 1}={t.name}" for i, t in enumerate(hired)))
        raw = input("  選擇編號，或直接按 Enter 跳過 > ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(hired):
            print("  " + assign_trainer(state, horse, hired[int(raw) - 1].name))


def setup_vets(state: GameState, auto: bool) -> None:
    """開局前的獸醫市場：聘用0~N名獸醫，並指定給馬匹（可跳過，見 員工系統.md「獸醫」）。"""
    market = generate_vet_market(count=3)
    if auto:
        # --auto demo模式：固定聘用市場第一位，指定給第一匹馬，其餘跳過，方便快速看流程。
        if state.money >= market[0].hire_fee:
            print(hire_vet(state, market[0]))
            print(assign_vet(state, state.horses[0], market[0].name))
        return

    print("\n===== 獸醫市場 =====")
    for i, v in enumerate(market, 1):
        print(f"  {i}. {v.name}｜Lv{v.skill_level}｜聘用費{v.hire_fee:,.0f}｜週薪{v.weekly_salary:,.0f}")
    print("  0. 不聘用，直接開始")

    hired: list = []
    while True:
        raw = input("聘用編號（可重複輸入多個，Enter結束選擇）> ").strip()
        if not raw or raw == "0":
            break
        if raw.isdigit() and 1 <= int(raw) <= len(market):
            vet = market[int(raw) - 1]
            print("  " + hire_vet(state, vet))
            hired.append(vet)
        else:
            print("  請輸入有效編號。")

    if not hired:
        return

    print("\n將已聘用的獸醫指定給馬匹（可跳過某匹）：")
    for horse in state.horses:
        print(f"\n{horse.name} 可指定：" + "、".join(f"{i + 1}={v.name}" for i, v in enumerate(hired)))
        raw = input("  選擇編號，或直接按 Enter 跳過 > ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(hired):
            print("  " + assign_vet(state, horse, hired[int(raw) - 1].name))


def choose_training(horse_name: str, auto: bool) -> str:
    options = list(TRAINABLE_STATS) + ["休息"]
    if auto:
        return random.choice(options)
    print(f"\n{horse_name} 本週訓練選項：")
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        raw = input("  選擇編號 > ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("  請輸入有效編號。")


def choose_race_entries(state: GameState, auto: bool) -> dict[str, list[RaceEntry]]:
    """回傳 {賽事分級: [RaceEntry, ...]}。"""
    entries_by_grade: dict[str, list[RaceEntry]] = {g: [] for g in A.RACE_GRADES}
    already_entered: set[str] = set()

    for horse in state.horses:
        if not horse.can_race():
            continue
        grades = eligible_grades(horse)
        if not grades:
            continue
        if auto:
            if random.random() < 0.5:
                grade = random.choice(grades)
                tactic = random.choice(("自由發揮", "保存體力"))
                entries_by_grade[grade].append(RaceEntry(horse, grade, tactic))
                already_entered.add(horse.name)
            continue

        print(f"\n{horse.name}（評級{horse.overall_rating():.1f}）符合資格：{', '.join(grades)}")
        raw = input("  要報名嗎？輸入分級名稱，或直接按 Enter 跳過 > ").strip()
        if raw in grades:
            tactic_raw = input("  選擇戰術（1=自由發揮 2=保存體力，預設1）> ").strip()
            tactic = "保存體力" if tactic_raw == "2" else "自由發揮"
            entries_by_grade[raw].append(RaceEntry(horse, raw, tactic))
            already_entered.add(horse.name)

    return {g: es for g, es in entries_by_grade.items() if es}


def handle_horse_market(state: GameState, auto: bool) -> None:
    """馬匹市場的CLI互動(cli/horse_market.py，2026/8/23使用者決定新增現役馬市場，
    2026/8/24補上幼駒/種馬/繁殖母馬市場)：可選是否要買賣這4類市場馬匹。

    --auto demo模式完全跳過，不做隨機經濟決策(比照訓練師/獸醫市場只在開局setup_trainers/
    setup_vets做一次性互動的精神，避免demo模式變得不可預期)。互動模式下每週都會問一次，
    不想理會可以直接按Enter跳過，不強迫玩家每週都要處理市場。
    """
    if auto:
        return

    if state.horse_market:
        print("\n----- 現役馬市場 -----")
        for h in state.horse_market:
            career_note = "已畢業" if h.graduated else ("未出賽新馬" if h.career_starts == 0 else "未畢業")
            print(
                f"  {h.name}｜{h.age}歲｜評級{h.overall_rating():.1f}/潛力{h.potential_cap:.0f}｜"
                f"{career_note}｜價格{horse_market_value(h):,.0f}"
            )
        raw = input("要購買嗎？輸入馬名，或直接按 Enter 跳過 > ").strip()
        if raw:
            print("  " + buy_horse(state, raw))

    if state.foal_market:
        print("\n----- 幼駒市場 -----")
        for h in state.foal_market:
            print(f"  {h.name}｜{h.sex}｜{h.age}歲｜父:{h.sire_name} 母:{h.dam_name}｜潛力{h.potential_cap:.0f}｜價格{horse_market_value(h):,.0f}")
        raw = input("要購買幼駒嗎？輸入馬名，或直接按 Enter 跳過 > ").strip()
        if raw:
            print("  " + buy_foal(state, raw))

    if state.stallion_market:
        print("\n----- 種馬市場 -----")
        for h in state.stallion_market:
            print(f"  {h.name}｜{h.age}歲｜評級{h.overall_rating():.1f}/潛力{h.potential_cap:.0f}｜價格{horse_breeding_stock_value(h):,.0f}")
        raw = input("要購買種馬嗎？輸入馬名，或直接按 Enter 跳過 > ").strip()
        if raw:
            print("  " + buy_stallion(state, raw))

    if state.broodmare_market:
        print("\n----- 繁殖母馬市場 -----")
        for h in state.broodmare_market:
            print(f"  {h.name}｜{h.age}歲｜評級{h.overall_rating():.1f}/潛力{h.potential_cap:.0f}｜價格{horse_breeding_stock_value(h):,.0f}")
        raw = input("要購買繁殖母馬嗎？輸入馬名，或直接按 Enter 跳過 > ").strip()
        if raw:
            print("  " + buy_broodmare(state, raw))

    if state.horses:
        raw = input("要出售馬匹嗎？輸入馬名，或直接按 Enter 跳過 > ").strip()
        if raw:
            print("  " + sell_horse(state, raw))


def handle_breeding(state: GameState, auto: bool) -> None:
    """繁殖系統的CLI互動(cli/breeding.py，2026/8/24使用者決定新增)：退役、登記種馬/繁殖
    母馬角色、配種，三個動作都可以跳過。

    --auto demo模式完全跳過(比照handle_horse_market的精神：這些都是玩家主動的經濟/
    育成決策，跳過才能讓demo模式的資金曲線/馬房組成保持可預期)。
    """
    if auto:
        return

    active = [h for h in state.horses if not h.retired]
    if active:
        raw = input("要讓哪匹馬退役嗎？輸入馬名，或直接按 Enter 跳過 > ").strip()
        if raw:
            print("  " + retire_horse(state, raw))

    unregistered_retired = [h for h in state.horses if h.retired and h.breeding_role is None]
    if unregistered_retired:
        print("\n----- 可登記繁殖角色的退役馬 -----")
        for h in unregistered_retired:
            print(f"  {h.name}｜{h.sex}｜{h.age}歲")
        raw = input("要登記種馬/繁殖母馬嗎？輸入「馬名 種馬」或「馬名 繁殖母馬」，或直接按 Enter 跳過 > ").strip()
        if raw:
            parts = raw.rsplit(" ", 1)
            if len(parts) == 2 and parts[1] in ("種馬", "繁殖母馬"):
                print("  " + assign_breeding_role(state, parts[0], parts[1]))
            else:
                print("  格式錯誤，跳過")

    stallions = [h for h in state.horses if h.breeding_role == "種馬"]
    mares = [h for h in state.horses if h.breeding_role == "繁殖母馬"]
    if stallions and mares:
        print("\n----- 配種 -----")
        print("  種馬：" + "、".join(h.name for h in stallions))
        print("  繁殖母馬：" + "、".join(h.name for h in mares))
        raw = input("要配種嗎？輸入「母馬名 種馬名」，或直接按 Enter 跳過 > ").strip()
        if raw:
            parts = raw.split(" ", 1)
            if len(parts) == 2:
                print("  " + breed(state, parts[0], parts[1]))
            else:
                print("  格式錯誤，跳過")


def play(weeks: int, auto: bool) -> GameState:
    state = new_game()
    print("===== 賽馬模擬遊戲 MVP 原型 =====")
    print(f"開局：{len(state.horses)} 匹測試馬，資金 {state.money:,.0f}\n")

    setup_trainers(state, auto)
    setup_vets(state, auto)

    for week in range(1, weeks + 1):
        state.week = week
        # 2026/8/24使用者回報的落差修正：訓練師/獸醫/馬匹市場的定期刷新(refresh_markets_
        # if_due，每MARKET_REFRESH_INTERVAL_WEEKS(4)週換一批候選人/待售馬)原本只有webapp
        # 每週會呼叫，CLI從補回這個系統開始就沒接上，導致CLI裡的市場永遠停在開局那批、
        # 不會刷新——這是純粹的落差，不是刻意的行為差異，這裡補上跟webapp一致的呼叫時機
        # (每週一開始、state.week更新之後立刻呼叫)。
        refresh_msg = refresh_markets_if_due(state)
        if refresh_msg:
            print(f"\n{refresh_msg}")
        racing_this_week = is_race_week(week)
        print_status(state)
        handle_horse_market(state, auto)
        handle_breeding(state, auto)

        # 平日：逐匹馬訓練/休息（受傷/退役/還未滿1歲的幼駒本週自動略過，見狀態與健康.md、
        # 馬匹成長.md「1歲可以開始訓練」）
        training_sessions = 0
        for horse in state.horses:
            if horse.retired:
                print(f"  {horse.name}：已退役，本週略過")
                continue
            if horse.injury is not None:
                print(f"  {horse.name}：養傷中（{horse.injury.name}，剩餘{horse.injury.weeks_remaining}週），本週休養")
                continue
            if not horse.can_train():
                print(f"  {horse.name}：還未滿{A.MIN_TRAINING_AGE}歲，本週略過")
                continue
            event = roll_weekly_event(racing_this_week)
            choice = choose_training(horse.name, auto)
            if choice == "休息":
                print("  " + rest_horse(horse, event))
            else:
                print("  " + train_horse(state, horse, choice, event))
                training_sessions += 1

        # 假日：比賽日（2026/8/23使用者決定改成每週開放，出賽後接下來2週不可再參賽，
        # 冷卻中的馬會被 choose_race_entries()/can_race() 自動排除，不會出現在報名選項裡）
        if racing_this_week:
            entries_by_grade = choose_race_entries(state, auto)
            if not entries_by_grade:
                print("\n（本週無馬匹報名比賽）")
            for grade, entries in entries_by_grade.items():
                for line in run_race(state, grade, entries):
                    print(line)

        for line in apply_weekly_injury_recovery(state):
            print("  " + line)
        for line in roll_weekly_injuries(state):
            print("  " + line)

        print("\n" + weekly_upkeep(state, training_sessions))
        apply_weekly_race_cooldown_recovery(state)
        for line in apply_weekly_age_progression(state):
            print("  " + line)
        for line in apply_weekly_league_season_progression(state):
            print("  " + line)
        for line in apply_weekly_pregnancy_progression(state):
            print("  " + line)
        for line in apply_weekly_stat_decline(state):
            print("  " + line)

        if state.bankrupt:
            print(f"\n!!! 資金跌破 {A.BANKRUPTCY_THRESHOLD:,.0f}，宣告破產，遊戲結束於第{week}週 !!!")
            break

    print("\n===== 遊戲結束（或達到指定週數）=====")
    print_status(state)
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="賽馬模擬遊戲 MVP CLI 原型")
    parser.add_argument("--weeks", type=int, default=16, help="遊玩週數（預設16，對應MVP範圍建議的12~16週）")
    parser.add_argument("--auto", action="store_true", help="自動demo模式，不需輸入，用亂數選擇代打")
    args = parser.parse_args()
    play(args.weeks, args.auto)


if __name__ == "__main__":
    main()
