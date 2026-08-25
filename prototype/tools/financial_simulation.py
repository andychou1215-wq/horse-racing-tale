#!/usr/bin/env python3
"""財務長週期驗證 — 比照 數值平衡試算.xlsx「財務系統進階」分頁的驗證方法，
但用 prototype/cli 實際的訓練/比賽/財務邏輯跑，而非另外重算一份數字。

跑 N 個模擬賽季(每季52週)、每季用固定策略(疲勞>70就休息，否則練目前最弱的
可訓練屬性；有資格就報名可報的最高分級比賽)，記錄資金曲線，回報：
- 每季最終資金、最低點資金
- 是否曾經觸發破產
- 用 M 次獨立試驗(比賽/事件都有亂數)取平均與範圍，而非只看單一次結果

2026/8/22 補上訓練師系統後更新：策略會在開局聘用 --trainer-count 名訓練師
(訓練師系統.md後補上，見 cli/trainers.py)、輪流指定給5匹馬，這樣財務驗證才會
把訓練師薪水這個新支出項目算進去。優先聘用市場裡週薪最低的幾位(量入為出的
理性玩家策略，而非「市場開幾位就聘幾位」)。--trainer-count 0 等同這個系統
補回前的行為，可以當對照組。

2026/8/22 補上獸醫/傷病系統後再次更新：同樣方式加了 --vet-count(預設1)，策略
也要處理「馬受傷/退役時不能訓練」——原本簡化策略是「疲勞>70就休息，否則練最弱
屬性」，現在多一條「有傷病或已退役就整週跳過訓練，也不能報名比賽」，並在每週
結算時呼叫傷病判定/恢復，否則會在 train_horse() 直接丟例外。

2026/8/22 補上設施升級系統後再次更新：跟訓練師/獸醫不同，設施是「一次性資本
支出、開局Lv2、不升級也完全不影響現有行為」，所以不像訓練師/獸醫那樣預設要聘
（沒有薪水這種持續性支出風險），預設 --facility-invest-threshold=0（不投資，
等同這個系統補回前的行為，向下相容）。加這個旗標是為了讓財務驗證也能模擬
「量入為出、有閒錢就投資設施」的玩家策略：資金超過門檻時，把超過門檻的部分
拿去升級目前費用最低的未滿級設施（越級便宜、CP值越高，優先升級）。

2026/8/23 賽事改成每週一次(出賽後接下來2週不可再參賽)後再次更新：策略本身完全
沒有改——「有資格就報名可報的最高分級比賽」這句話現在自然變成「只要沒在出賽
冷卻中、有資格就報」，因為 `can_race()` 已經把冷卻中的馬排除在外，程式面完全
不用特別處理。但這個規則調整讓每匹馬出賽的頻率從「最多每4週一次(全馬房共用
賽曆)」變成「大約每3週一次(出賽後鎖2週，各自獨立倒數)」，等於出賽機會變密、
出賽相關的報名費/獎金/傷病風險在整季裡出現的次數也變多，財務曲線的變化需要
重新驗證(見README「賽事頻率調整」)。

用法：
    python3 tools/financial_simulation.py [--weeks 52] [--trials 20]
    python3 tools/financial_simulation.py --trainer-count 0 --vet-count 0   # 兩個系統都補回前的對照組
    python3 tools/financial_simulation.py --trainer-count 4                # 訓練師全部聘滿的壓力測試
    python3 tools/financial_simulation.py --facility-invest-threshold 20000  # 閒錢超過2萬就投資設施
"""
from __future__ import annotations

import argparse
import random
import statistics
import sys

sys.path.insert(0, ".")

from cli import assumptions as A
from cli.game import (
    GameState,
    RaceEntry,
    apply_weekly_age_progression,
    apply_weekly_injury_recovery,
    apply_weekly_league_season_progression,
    apply_weekly_pregnancy_progression,
    apply_weekly_race_cooldown_recovery,
    apply_weekly_stat_decline,
    assign_trainer,
    assign_vet,
    eligible_grades,
    hire_trainer,
    hire_vet,
    is_race_week,
    game_state_with_test_horses,
    rest_horse,
    roll_weekly_injuries,
    run_race,
    train_horse,
    upgrade_facility,
    weekly_upkeep,
)
from cli.facilities import MAX_LEVEL as FACILITY_MAX_LEVEL
from cli.facilities import upgrade_cost as facility_upgrade_cost
from cli.horses import TRAINABLE_STATS
from cli.trainers import generate_trainer_market
from cli.vets import generate_vet_market


def maybe_invest_in_facilities(state: GameState, threshold: float) -> None:
    """有閒錢(資金超過threshold)時，把超過門檻的部分拿去升級目前費用最低的未滿級設施。

    每週最多升一級，避免一次把整季的錢都砸在設施上、跟賽馬/訓練支出搶資金。
    """
    if threshold <= 0:
        return
    if state.money <= threshold:
        return
    upgradeable = {
        f: lvl for f, lvl in state.facility_levels.items() if lvl < FACILITY_MAX_LEVEL
    }
    if not upgradeable:
        return
    cheapest_facility = min(upgradeable, key=lambda f: facility_upgrade_cost(upgradeable[f]))
    cost = facility_upgrade_cost(upgradeable[cheapest_facility])
    if state.money - cost >= threshold:
        upgrade_facility(state, cheapest_facility)


def play_one_season(
    weeks: int, trainer_count: int = 2, vet_count: int = 1, facility_invest_threshold: float = 0.0
) -> dict:
    state = game_state_with_test_horses()
    money_history = [state.money]

    if trainer_count > 0:
        market = generate_trainer_market(count=4)
        cheapest = sorted(market, key=lambda t: t.weekly_salary)[:trainer_count]
        for trainer in cheapest:
            hire_trainer(state, trainer)  # 資金不足時 hire_trainer 內部會自己跳過，不丟例外
        for i, horse in enumerate(state.horses):
            if state.trainers:
                assign_trainer(state, horse, state.trainers[i % len(state.trainers)].name)

    if vet_count > 0:
        market = generate_vet_market(count=3)
        cheapest = sorted(market, key=lambda v: v.weekly_salary)[:vet_count]
        for vet in cheapest:
            hire_vet(state, vet)
        for i, horse in enumerate(state.horses):
            if state.vets:
                assign_vet(state, horse, state.vets[i % len(state.vets)].name)

    for week in range(1, weeks + 1):
        state.week = week
        racing_this_week = is_race_week(week)
        training_sessions = 0

        for horse in state.horses:
            if horse.retired or horse.injury is not None or not horse.can_train():
                continue  # 受傷/退役/還未滿1歲的幼駒，本週無法訓練（見 game.py train_horse 的防呆）
            if horse.fatigue > 70:
                rest_horse(horse)
            else:
                stat = min(TRAINABLE_STATS, key=lambda s: horse.stats[s])
                train_horse(state, horse, stat)
                training_sessions += 1

        if racing_this_week:
            entries_by_grade: dict[str, list[RaceEntry]] = {g: [] for g in A.RACE_GRADES}
            for horse in state.horses:
                if not horse.can_race():
                    continue
                grades = eligible_grades(horse)
                if not grades:
                    continue
                grade = grades[-1]  # 報名可報的最高分級，賺最多獎金/經驗
                entries_by_grade[grade].append(RaceEntry(horse, grade, "自由發揮"))
            for grade, entries in entries_by_grade.items():
                if entries:
                    run_race(state, grade, entries)

        apply_weekly_injury_recovery(state)
        roll_weekly_injuries(state)
        weekly_upkeep(state, training_sessions)
        apply_weekly_race_cooldown_recovery(state)
        apply_weekly_age_progression(state)
        apply_weekly_league_season_progression(state)
        # 2026/8/25新增馬主聯盟系統後補上：這裡的簡化策略確實會出賽賺積分(run_race()
        # 內建計分)，長期模擬需要接上賽季結算才不會讓league_points無限累積不清零。
        apply_weekly_pregnancy_progression(state)
        # 2026/8/24新增繁殖系統後補上這個呼叫(比照age_progression/cooldown_recovery的一致
        # 呼叫時機)：這裡的簡化策略從不呼叫breed()，所以實際上不會有母馬懷孕/生產，這行
        # 只是保持跟webapp/cli一致的每週結算順序，避免之後策略真的加了繁殖行為卻忘記接上。
        apply_weekly_stat_decline(state)
        # 2026/8/24新增成長曲線系統後補上：開局5匹測試馬固定成長曲線類型，長期模擬(數百週)
        # 一定會有馬進入衰退期，這裡如果漏接會讓長期財務模擬失真(退化的馬應該賺得比較少)。
        maybe_invest_in_facilities(state, facility_invest_threshold)
        money_history.append(state.money)

        if state.bankrupt:
            break

    return {
        "final_money": state.money,
        "min_money": min(money_history),
        "bankrupt": state.bankrupt,
        "bankrupt_week": state.week if state.bankrupt else None,
        "total_fame": sum(h.fame for h in state.horses),
        "total_prize": sum(h.money_earned for h in state.horses),
        "retired_count": sum(1 for h in state.horses if h.retired),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="財務長週期驗證")
    parser.add_argument("--weeks", type=int, default=52)
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--trainer-count", type=int, default=2, help="開局聘用幾名訓練師（0=不聘，對照組；最多4）")
    parser.add_argument("--vet-count", type=int, default=1, help="開局聘用幾名獸醫（0=不聘，對照組；最多3）")
    parser.add_argument(
        "--facility-invest-threshold", type=float, default=0.0,
        help="資金超過這個門檻時，把閒錢拿去升級設施（0=不投資，對照組；例如20000）",
    )
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    results = [
        play_one_season(
            args.weeks,
            trainer_count=args.trainer_count,
            vet_count=args.vet_count,
            facility_invest_threshold=args.facility_invest_threshold,
        )
        for _ in range(args.trials)
    ]

    finals = [r["final_money"] for r in results]
    mins = [r["min_money"] for r in results]
    bankrupt_count = sum(1 for r in results if r["bankrupt"])

    trainer_label = f"{args.trainer_count}名訓練師" if args.trainer_count else "不聘訓練師"
    vet_label = f"{args.vet_count}名獸醫" if args.vet_count else "不聘獸醫"
    facility_label = (
        f"閒錢門檻{args.facility_invest_threshold:,.0f}就投資設施"
        if args.facility_invest_threshold > 0
        else "不投資設施"
    )
    print(
        f"===== 財務長週期驗證：{args.trials}次獨立試驗，每次{args.weeks}週｜"
        f"{trainer_label}｜{vet_label}｜{facility_label} ====="
    )
    print(f"起始資金：{A.STARTING_MONEY:,.0f}")
    print()
    print(f"最終資金：平均 {statistics.mean(finals):,.0f}｜中位數 {statistics.median(finals):,.0f}｜"
          f"最低 {min(finals):,.0f}｜最高 {max(finals):,.0f}")
    print(f"過程中最低點資金：平均 {statistics.mean(mins):,.0f}｜最低 {min(mins):,.0f}")
    print(f"破產次數：{bankrupt_count}/{args.trials}")
    retired_total = sum(r["retired_count"] for r in results)
    if retired_total:
        print(f"退役馬匹數：合計 {retired_total} 匹（{args.trials}次試驗、每次最多5匹）")
    if bankrupt_count:
        weeks_to_bankrupt = [r["bankrupt_week"] for r in results if r["bankrupt"]]
        print(f"  破產發生週次：{weeks_to_bankrupt}")
    print()
    print("-- 逐次結果 --")
    for i, r in enumerate(results, 1):
        status = f"破產於第{r['bankrupt_week']}週" if r["bankrupt"] else "存活"
        print(f"  第{i:>2}次：最終資金 {r['final_money']:>10,.0f}｜最低點 {r['min_money']:>10,.0f}｜{status}")


if __name__ == "__main__":
    main()
