"""網頁UI原型 — 把 cli/game.py 的核心邏輯包一層 Flask 網頁介面。

刻意不重寫任何遊戲規則：所有訓練/比賽/財務計算一律呼叫既有的
`cli.game` / `engine` 函式，這裡只負責「畫面」——把表單輸入轉成
function call，把回傳的文字結果轉成網頁呈現。

單一全域 GameState（單人本機開發伺服器用途，非多人/多分頁安全設計，
見 README「已知限制」）。

執行：
    cd racing-sim
    python3 -m webapp.app
    瀏覽器開啟 http://127.0.0.1:5000
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, flash, redirect, render_template, request, session, url_for

from cli import assumptions as A
from cli import traits as T
from cli.facilities import (
    FACILITY_TYPES,
    MAX_LEVEL as FACILITY_MAX_LEVEL,
    overseas_stable_capacity_for_level as facility_overseas_stable_capacity,
    stable_capacity_for_level as facility_stable_capacity,
    stud_farm_capacity_for_level as facility_stud_farm_capacity,
    upgrade_cost as facility_upgrade_cost,
)
from cli import league as LG
from cli.game import (
    MARKET_REFRESH_INTERVAL_WEEKS,
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
    fire_trainer,
    fire_vet,
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
    upgrade_facility,
    weekly_upkeep,
)
from cli.horse_market import breeding_stock_value as horse_breeding_stock_value
from cli.horse_market import market_value as horse_market_value
from cli.horses import TRAINABLE_STATS

app = Flask(__name__)
app.secret_key = "racing-sim-mvp-webapp-dev-key"  # 僅供本機開發用，非正式部署密鑰

# 全域遊戲狀態（見模組docstring：單人本機原型，非多使用者安全設計）
GAME: GameState | None = None
PENDING_TRAINING_LOG: list[str] = []  # 訓練階段做完、比賽階段還沒做時，暫存本週訓練結果
PENDING_TRAINING_SESSIONS = 0  # 同上，暫存本週訓練次數(供比賽週最終的週結算費用計算用)
# 訓練師/獸醫市場清單改存在 GameState.trainer_market / vet_market 裡(見 cli/game.py)，
# 不再是webapp自己的全域變數——這樣市場才能跟著 state.week 定期刷新(見
# refresh_markets_if_due)，而不是開新局才重生一次。


def get_game() -> GameState:
    global GAME
    if GAME is None:
        GAME = new_game()
    return GAME


@app.route("/")
def dashboard():
    state = get_game()
    if state.bankrupt:
        return render_template("bankrupt.html", state=state)
    return render_template(
        "dashboard.html",
        state=state,
        trainable_stats=TRAINABLE_STATS,
        state_grade=A.state_grade,
        is_race_week_now=is_race_week(state.week),
        trait_defs=T.TRAIT_DEFS,
        league_tier_name=LG.TIER_NAMES[state.league_tier],
        weeks_until_league_season_end=A.WEEKS_PER_YEAR - (state.week % A.WEEKS_PER_YEAR),
    )


@app.route("/new_game", methods=["POST"])
def new_game_route():
    global GAME, PENDING_TRAINING_LOG
    GAME = new_game()
    PENDING_TRAINING_LOG = []
    flash("新的一局開始了！")
    return redirect(url_for("dashboard"))


@app.route("/trainers")
def trainers_page():
    """訓練師市場 + 指定訓練師頁面（訓練師系統.md）。"""
    state = get_game()
    return render_template(
        "trainers.html",
        state=state,
        market=[t for t in state.trainer_market if state.trainer_by_name(t.name) is None],
        next_refresh_week=state.last_market_refresh_week + MARKET_REFRESH_INTERVAL_WEEKS,
    )


@app.route("/hire_trainer", methods=["POST"])
def hire_trainer_route():
    state = get_game()
    trainer_name = request.form.get("trainer_name", "")
    trainer = next((t for t in state.trainer_market if t.name == trainer_name), None)
    if trainer is None:
        flash(f"找不到訓練師「{trainer_name}」")
    else:
        flash(hire_trainer(state, trainer))
    return redirect(url_for("trainers_page"))


@app.route("/assign_trainer", methods=["POST"])
def assign_trainer_route():
    state = get_game()
    for horse in state.horses:
        trainer_name = request.form.get(f"trainer_{horse.name}", "") or None
        if trainer_name == horse.assigned_trainer:
            continue  # 沒有變更就不用重複顯示訊息
        flash(assign_trainer(state, horse, trainer_name))
    return redirect(url_for("trainers_page"))


@app.route("/fire_trainer", methods=["POST"])
def fire_trainer_route():
    state = get_game()
    trainer_name = request.form.get("trainer_name", "")
    flash(fire_trainer(state, trainer_name))
    return redirect(url_for("trainers_page"))


@app.route("/vets")
def vets_page():
    """獸醫市場 + 指定獸醫頁面（員工系統.md「獸醫」+ 狀態與健康.md「養傷」）。"""
    state = get_game()
    return render_template(
        "vets.html",
        state=state,
        market=[v for v in state.vet_market if state.vet_by_name(v.name) is None],
        next_refresh_week=state.last_market_refresh_week + MARKET_REFRESH_INTERVAL_WEEKS,
    )


@app.route("/hire_vet", methods=["POST"])
def hire_vet_route():
    state = get_game()
    vet_name = request.form.get("vet_name", "")
    vet = next((v for v in state.vet_market if v.name == vet_name), None)
    if vet is None:
        flash(f"找不到獸醫「{vet_name}」")
    else:
        flash(hire_vet(state, vet))
    return redirect(url_for("vets_page"))


@app.route("/assign_vet", methods=["POST"])
def assign_vet_route():
    state = get_game()
    for horse in state.horses:
        vet_name = request.form.get(f"vet_{horse.name}", "") or None
        if vet_name == horse.assigned_vet:
            continue  # 沒有變更就不用重複顯示訊息
        flash(assign_vet(state, horse, vet_name))
    return redirect(url_for("vets_page"))


@app.route("/fire_vet", methods=["POST"])
def fire_vet_route():
    state = get_game()
    vet_name = request.form.get("vet_name", "")
    flash(fire_vet(state, vet_name))
    return redirect(url_for("vets_page"))


@app.route("/facilities")
def facilities_page():
    """設施升級頁面（設施系統.md）：一次性資本支出，跟訓練師/獸醫的持續週薪對照。"""
    state = get_game()
    costs = {
        f: (facility_upgrade_cost(state.facility_levels[f]) if state.facility_levels[f] < FACILITY_MAX_LEVEL else None)
        for f in FACILITY_TYPES
    }
    return render_template(
        "facilities.html",
        state=state,
        facility_types=FACILITY_TYPES,
        costs=costs,
        max_level=FACILITY_MAX_LEVEL,
        stable_capacity=facility_stable_capacity(state.facility_levels["馬房"]),
        stud_farm_capacity=facility_stud_farm_capacity(state.facility_levels["育馬場"]),
        stud_farm_occupied=sum(1 for h in state.horses if h.breeding_role is not None),
        overseas_stable_capacity=facility_overseas_stable_capacity(state.facility_levels["海外馬房"]),
    )


@app.route("/upgrade_facility", methods=["POST"])
def upgrade_facility_route():
    state = get_game()
    facility_name = request.form.get("facility_name", "")
    flash(upgrade_facility(state, facility_name))
    return redirect(url_for("facilities_page"))


@app.route("/horse_market")
def horse_market_page():
    """馬匹市場頁面（cli/horse_market.py，2026/8/23使用者決定新增現役馬市場，2026/8/24
    使用者決定補上幼駒/種馬/繁殖母馬市場）：買賣4類市場馬匹。
    """
    state = get_game()
    return render_template(
        "horse_market.html",
        state=state,
        prices={h.name: horse_market_value(h) for h in state.horse_market},
        foal_prices={h.name: horse_market_value(h) for h in state.foal_market},
        stallion_prices={h.name: horse_breeding_stock_value(h) for h in state.stallion_market},
        broodmare_prices={h.name: horse_breeding_stock_value(h) for h in state.broodmare_market},
        sell_prices={h.name: horse_market_value(h) for h in state.horses},
        next_refresh_week=state.last_market_refresh_week + MARKET_REFRESH_INTERVAL_WEEKS,
        state_grade=A.state_grade,
    )


@app.route("/buy_horse", methods=["POST"])
def buy_horse_route():
    state = get_game()
    horse_name = request.form.get("horse_name", "")
    flash(buy_horse(state, horse_name))
    return redirect(url_for("horse_market_page"))


@app.route("/buy_foal", methods=["POST"])
def buy_foal_route():
    state = get_game()
    horse_name = request.form.get("horse_name", "")
    flash(buy_foal(state, horse_name))
    return redirect(url_for("horse_market_page"))


@app.route("/buy_stallion", methods=["POST"])
def buy_stallion_route():
    state = get_game()
    horse_name = request.form.get("horse_name", "")
    flash(buy_stallion(state, horse_name))
    return redirect(url_for("horse_market_page"))


@app.route("/buy_broodmare", methods=["POST"])
def buy_broodmare_route():
    state = get_game()
    horse_name = request.form.get("horse_name", "")
    flash(buy_broodmare(state, horse_name))
    return redirect(url_for("horse_market_page"))


@app.route("/sell_horse", methods=["POST"])
def sell_horse_route():
    state = get_game()
    horse_name = request.form.get("horse_name", "")
    flash(sell_horse(state, horse_name))
    return redirect(url_for("horse_market_page"))


@app.route("/breeding")
def breeding_page():
    """繁殖頁面（cli/breeding.py，2026/8/24使用者決定新增）：退役、登記種馬/繁殖母馬、配種。"""
    state = get_game()
    return render_template(
        "breeding.html",
        state=state,
        stallions=[h for h in state.horses if h.breeding_role == "種馬"],
        mares=[h for h in state.horses if h.breeding_role == "繁殖母馬"],
        unregistered_retired=[h for h in state.horses if h.retired and h.breeding_role is None],
        active=[h for h in state.horses if not h.retired],
        breeding_cost=A.BREEDING_COST,
        gestation_weeks=A.GESTATION_WEEKS,
    )


@app.route("/retire_horse", methods=["POST"])
def retire_horse_route():
    state = get_game()
    horse_name = request.form.get("horse_name", "")
    flash(retire_horse(state, horse_name))
    return redirect(url_for("breeding_page"))


@app.route("/assign_breeding_role", methods=["POST"])
def assign_breeding_role_route():
    state = get_game()
    horse_name = request.form.get("horse_name", "")
    role = request.form.get("role", "") or None
    flash(assign_breeding_role(state, horse_name, role))
    return redirect(url_for("breeding_page"))


@app.route("/breed", methods=["POST"])
def breed_route():
    state = get_game()
    mare_name = request.form.get("mare_name", "")
    stallion_name = request.form.get("stallion_name", "")
    flash(breed(state, mare_name, stallion_name))
    return redirect(url_for("breeding_page"))


@app.route("/submit_week", methods=["POST"])
def submit_week():
    """處理本週訓練/休息表單。若本週是比賽週，先暫存訓練結果、導向報名頁；否則直接結算本週。"""
    global PENDING_TRAINING_LOG, PENDING_TRAINING_SESSIONS
    state = get_game()
    racing_this_week = is_race_week(state.week)

    log: list[str] = []
    training_sessions = 0
    for horse in state.horses:
        if horse.retired:
            log.append(f"{horse.name}：已退役，本週略過")
            continue
        if horse.injury is not None:
            log.append(f"{horse.name}：養傷中（{horse.injury.name}，剩餘{horse.injury.weeks_remaining}週），本週休養")
            continue
        if not horse.can_train():
            log.append(f"{horse.name}：還未滿{A.MIN_TRAINING_AGE}歲，本週略過")
            continue
        choice = request.form.get(f"choice_{horse.name}", "休息")
        event = roll_weekly_event(racing_this_week)
        if choice == "休息":
            log.append(rest_horse(horse, event))
        elif choice in TRAINABLE_STATS:
            log.append(train_horse(state, horse, choice, event))
            training_sessions += 1
        else:
            log.append(f"{horse.name}：未知選項「{choice}」，本週跳過")

    if racing_this_week:
        PENDING_TRAINING_LOG = log
        PENDING_TRAINING_SESSIONS = training_sessions
        return redirect(url_for("race_entry"))

    log.extend(apply_weekly_injury_recovery(state))
    log.extend(roll_weekly_injuries(state))
    upkeep_msg = weekly_upkeep(state, training_sessions)
    log.append(upkeep_msg)
    apply_weekly_race_cooldown_recovery(state)
    log.extend(apply_weekly_age_progression(state))
    log.extend(apply_weekly_league_season_progression(state))
    log.extend(apply_weekly_pregnancy_progression(state))
    log.extend(apply_weekly_stat_decline(state))
    for line in log:
        flash(line)
    state.week += 1
    refresh_msg = refresh_markets_if_due(state)
    if refresh_msg:
        flash(refresh_msg)
    if state.bankrupt:
        flash(f"資金跌破 {A.BANKRUPTCY_THRESHOLD:,.0f}，宣告破產！")
    return redirect(url_for("dashboard"))


@app.route("/race_entry")
def race_entry():
    state = get_game()
    eligible = {h.name: eligible_grades(h) for h in state.horses if h.can_race()}
    return render_template(
        "race_entry.html",
        state=state,
        eligible=eligible,
        state_grade=A.state_grade,
        maiden_race_age=A.MAIDEN_RACE_AGE,
    )


@app.route("/submit_race", methods=["POST"])
def submit_race():
    global PENDING_TRAINING_LOG, PENDING_TRAINING_SESSIONS
    state = get_game()

    entries_by_grade: dict[str, list[RaceEntry]] = {g: [] for g in A.RACE_GRADES}
    for horse in state.horses:
        if not horse.can_race():
            continue
        grade = request.form.get(f"grade_{horse.name}", "")
        if grade in A.RACE_GRADES:
            tactic = request.form.get(f"tactic_{horse.name}", "自由發揮")
            entries_by_grade[grade].append(RaceEntry(horse, grade, tactic))

    log = list(PENDING_TRAINING_LOG)
    training_sessions = PENDING_TRAINING_SESSIONS
    PENDING_TRAINING_LOG = []
    PENDING_TRAINING_SESSIONS = 0

    any_race = False
    for grade, entries in entries_by_grade.items():
        if entries:
            any_race = True
            log.extend(run_race(state, grade, entries))
    if not any_race:
        log.append("（本週無馬匹報名比賽）")

    log.extend(apply_weekly_injury_recovery(state))
    log.extend(roll_weekly_injuries(state))
    upkeep_msg = weekly_upkeep(state, training_sessions)
    log.append(upkeep_msg)
    apply_weekly_race_cooldown_recovery(state)
    log.extend(apply_weekly_age_progression(state))
    log.extend(apply_weekly_league_season_progression(state))
    log.extend(apply_weekly_pregnancy_progression(state))
    log.extend(apply_weekly_stat_decline(state))

    for line in log:
        flash(line)
    state.week += 1
    refresh_msg = refresh_markets_if_due(state)
    if refresh_msg:
        flash(refresh_msg)
    if state.bankrupt:
        flash(f"資金跌破 {A.BANKRUPTCY_THRESHOLD:,.0f}，宣告破產！")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
