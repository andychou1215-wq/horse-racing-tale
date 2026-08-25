"""網頁UI(webapp/app.py)的路由煙霧測試(smoke test)。

不重測遊戲規則本身(engine/cli 已有的41個測試負責那部分)，只確認網頁層的
路由串接正確：能顯示、能送出訓練、比賽週會導向報名頁、報名後會正確推進到
下一週、破產畫面與重新開局都正常運作。

2026/8/23使用者決定「賽事改成每週一次」之後：每週送出訓練都會導向報名頁
(is_race_week恆為True)，不再有「非比賽週」這個分支。
"""
from __future__ import annotations

import pytest

from webapp import app as appmod

HORSE_NAMES = ["全能強馬", "速度型快馬", "耐力追込馬", "平衡中庸馬", "潛力新星"]


@pytest.fixture()
def client():
    appmod.app.config["TESTING"] = True
    appmod.GAME = None
    appmod.PENDING_TRAINING_LOG = []
    appmod.PENDING_TRAINING_SESSIONS = 0
    with appmod.app.test_client() as c:
        c.get("/")  # 觸發建立新遊戲
        yield c


def rest_all(client):
    form = {f"choice_{n}": "休息" for n in HORSE_NAMES}
    return client.post("/submit_week", data=form)


def advance_one_week(client):
    """跟rest_all不同：比賽週(每4週)也會完整跑完報名(空報名)、確實推進到下一週。"""
    r = rest_all(client)
    if r.headers.get("Location", "").endswith("/race_entry"):
        r = client.post("/submit_race", data={})
    return r


def test_dashboard_shows_week_1(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "第 1 週" in r.get_data(as_text=True)


def test_submit_week_always_redirects_to_race_entry(client):
    """2026/8/23：賽事改成每週一次，is_race_week恆為True，送出訓練後永遠導向報名頁。"""
    r = rest_all(client)
    assert r.status_code == 302
    assert "/race_entry" in r.headers["Location"]


def test_race_week_flow_reaches_next_week(client):
    body = client.get("/").get_data(as_text=True)
    assert "第 1 週" in body
    assert "比賽週" in body

    r = rest_all(client)
    assert "/race_entry" in r.headers["Location"]

    race_page = client.get("/race_entry").get_data(as_text=True)
    assert "報名分級" in race_page

    r2 = client.post("/submit_race", data={"grade_全能強馬": "新馬賽", "tactic_全能強馬": "自由發揮"})
    assert r2.status_code == 302

    body2 = client.get("/").get_data(as_text=True)
    assert "第 2 週" in body2


def test_horse_cannot_race_again_within_two_weeks_after_racing(client):
    """2026/8/23使用者決定：出賽後接下來2週不可再參賽，第3週才能再出賽。"""
    client.post("/submit_week", data={f"choice_{n}": "休息" for n in HORSE_NAMES})
    client.post("/submit_race", data={"grade_全能強馬": "新馬賽", "tactic_全能強馬": "自由發揮"})
    game = appmod.get_game()
    assert game.week == 2
    assert game.horse_by_name("全能強馬").race_cooldown_weeks_remaining > 0

    # 第2、3週：冷卻中，報名頁不該再出現這匹馬的分級選項
    for _ in range(2):
        body = client.get("/race_entry").get_data(as_text=True)
        assert 'name="grade_全能強馬"' not in body
        advance_one_week(client)

    # 第4週(出賽後第3週)：冷卻結束，應該重新出現在報名選項裡
    assert game.horse_by_name("全能強馬").race_cooldown_weeks_remaining == 0
    body = client.get("/race_entry").get_data(as_text=True)
    assert 'name="grade_全能強馬"' in body


def test_trainers_page_shows_market(client):
    body = client.get("/trainers").get_data(as_text=True)
    assert "訓練師市場" in body


def test_trainers_and_vets_pages_link_back_to_dashboard(client):
    """使用者回報：進入訓練師/獸醫市場後無法返回馬房總覽頁，修正後每頁都要有回總覽的連結。"""
    for path in ("/trainers", "/vets"):
        body = client.get(path).get_data(as_text=True)
        assert 'href="/"' in body


def test_facilities_page_shows_all_facility_types_and_links_back_to_dashboard(client):
    body = client.get("/facilities").get_data(as_text=True)
    assert "速度訓練場" in body
    assert "恢復中心" in body
    assert "醫療中心" in body
    assert 'href="/"' in body


def test_upgrade_facility_route_increments_level_and_deducts_money(client):
    game = appmod.get_game()
    game.money = 100000.0
    level_before = game.facility_levels["速度訓練場"]

    r = client.post("/upgrade_facility", data={"facility_name": "速度訓練場"})
    assert r.status_code == 302
    assert game.facility_levels["速度訓練場"] == level_before + 1
    assert game.money < 100000.0


def test_horse_market_page_shows_listings_and_links_back_to_dashboard(client):
    body = client.get("/horse_market").get_data(as_text=True)
    assert "現役馬市場" in body
    assert 'href="/"' in body
    game = appmod.get_game()
    for h in game.horse_market:
        assert h.name in body
    assert "比較已選" in body
    assert "最低價格" in body
    assert "有正面特性" in body
    assert "可立即出賽／繁殖" in body
    assert "最近交易" in body


def test_buy_horse_route_adds_to_stable_and_removes_from_market(client):
    game = appmod.get_game()
    game.money = 200000.0
    target = game.horse_market[0].name

    r = client.post("/buy_horse", data={"horse_name": target})
    assert r.status_code == 302
    assert any(h.name == target for h in game.horses)
    assert not any(h.name == target for h in game.horse_market)
    assert target in game.jockeys
    assert target in game.transaction_history[0]
    assert "購入現役馬" in game.transaction_history[0]


def test_sell_horse_route_removes_from_stable_and_adds_money(client):
    game = appmod.get_game()
    money_before = game.money

    r = client.post("/sell_horse", data={"horse_name": "全能強馬"})
    assert r.status_code == 302
    assert not any(h.name == "全能強馬" for h in game.horses)
    assert "全能強馬" not in game.jockeys
    assert game.money > money_before


def test_horse_market_refreshes_after_four_weeks_pass(client):
    from cli.game import MARKET_REFRESH_INTERVAL_WEEKS

    game = appmod.get_game()
    original_names = {h.name for h in game.horse_market}

    for _ in range(MARKET_REFRESH_INTERVAL_WEEKS):
        advance_one_week(client)

    assert {h.name for h in game.horse_market} != original_names


def test_fire_trainer_route_removes_trainer_and_stops_salary(client):
    trainer_name = appmod.get_game().trainer_market[0].name
    client.post("/hire_trainer", data={"trainer_name": trainer_name})
    client.post("/assign_trainer", data={f"trainer_全能強馬": trainer_name})

    game = appmod.get_game()
    assert any(t.name == trainer_name for t in game.trainers)

    r = client.post("/fire_trainer", data={"trainer_name": trainer_name})
    assert r.status_code == 302
    assert not any(t.name == trainer_name for t in game.trainers)
    assert game.horse_by_name("全能強馬").assigned_trainer is None

    # 解雇後應該重新出現在市場清單裡，可以再聘一次
    market_body = client.get("/trainers").get_data(as_text=True)
    assert trainer_name in market_body


def test_fire_vet_route_removes_vet_and_stops_salary(client):
    vet_name = appmod.get_game().vet_market[0].name
    client.post("/hire_vet", data={"vet_name": vet_name})
    client.post("/assign_vet", data={f"vet_全能強馬": vet_name})

    game = appmod.get_game()
    assert any(v.name == vet_name for v in game.vets)

    r = client.post("/fire_vet", data={"vet_name": vet_name})
    assert r.status_code == 302
    assert not any(v.name == vet_name for v in game.vets)
    assert game.horse_by_name("全能強馬").assigned_vet is None

    market_body = client.get("/vets").get_data(as_text=True)
    assert vet_name in market_body


def test_hire_and_assign_trainer_flow(client):
    market_body = client.get("/trainers").get_data(as_text=True)
    assert "尚未聘用" in market_body

    trainer_name = appmod.get_game().trainer_market[0].name
    r = client.post("/hire_trainer", data={"trainer_name": trainer_name})
    assert r.status_code == 302

    game = appmod.get_game()
    assert any(t.name == trainer_name for t in game.trainers)

    r2 = client.post("/assign_trainer", data={f"trainer_全能強馬": trainer_name})
    assert r2.status_code == 302
    assert game.horse_by_name("全能強馬").assigned_trainer == trainer_name


def test_vets_page_shows_market(client):
    body = client.get("/vets").get_data(as_text=True)
    assert "獸醫市場" in body


def test_hire_and_assign_vet_flow(client):
    market_body = client.get("/vets").get_data(as_text=True)
    assert "尚未聘用" in market_body

    vet_name = appmod.get_game().vet_market[0].name
    r = client.post("/hire_vet", data={"vet_name": vet_name})
    assert r.status_code == 302

    game = appmod.get_game()
    assert any(v.name == vet_name for v in game.vets)

    r2 = client.post("/assign_vet", data={f"vet_全能強馬": vet_name})
    assert r2.status_code == 302
    assert game.horse_by_name("全能強馬").assigned_vet == vet_name


def test_injured_horse_is_excluded_from_training_and_race_entry(client):
    from cli.injuries import Injury

    game = appmod.get_game()
    horse = game.horse_by_name("速度型快馬")
    horse.injury = Injury(name="測試傷", severity="中傷", weeks_remaining=3, affected_stats=("速度",))

    dashboard_body = client.get("/").get_data(as_text=True)
    assert "養傷中" in dashboard_body
    assert f'name="choice_速度型快馬"' not in dashboard_body

    # 送出本週選擇，不應該因為受傷的馬沒有 choice_ 欄位而出錯
    form = {f"choice_{n}": "休息" for n in HORSE_NAMES if n != "速度型快馬"}
    r = client.post("/submit_week", data=form)
    assert r.status_code == 302


def test_trainers_and_vets_pages_show_next_refresh_week(client):
    for path in ("/trainers", "/vets"):
        body = client.get(path).get_data(as_text=True)
        assert "下次刷新" in body
        assert "第5週" in body  # 開局第1週+4週間隔=第5週


def test_trainer_market_refreshes_after_four_weeks_pass(client):
    from cli.game import MARKET_REFRESH_INTERVAL_WEEKS

    game = appmod.get_game()
    original_names = {t.name for t in game.trainer_market}

    for _ in range(MARKET_REFRESH_INTERVAL_WEEKS):
        advance_one_week(client)

    assert game.week == 1 + MARKET_REFRESH_INTERVAL_WEEKS
    assert {t.name for t in game.trainer_market} != original_names


def test_market_refresh_does_not_remove_hired_trainer_from_dashboard(client):
    from cli.game import MARKET_REFRESH_INTERVAL_WEEKS

    trainer_name = appmod.get_game().trainer_market[0].name
    client.post("/hire_trainer", data={"trainer_name": trainer_name})
    client.post("/assign_trainer", data={f"trainer_全能強馬": trainer_name})

    for _ in range(MARKET_REFRESH_INTERVAL_WEEKS):
        advance_one_week(client)

    game = appmod.get_game()
    assert any(t.name == trainer_name for t in game.trainers)
    assert game.horse_by_name("全能強馬").assigned_trainer == trainer_name


def test_bankrupt_page_and_new_game_reset(client):
    game = appmod.get_game()
    game.bankrupt = True
    body = client.get("/").get_data(as_text=True)
    assert "破產" in body

    client.post("/new_game")
    body2 = client.get("/").get_data(as_text=True)
    assert "第 1 週" in body2
    assert "破產" not in body2


# ------------------------------------------------------------------- 繁殖(cli/breeding.py)

def test_breeding_page_shows_sections(client):
    body = client.get("/breeding").get_data(as_text=True)
    assert "登記繁殖角色" in body
    assert "配種" in body


def test_retire_horse_route_marks_retired(client):
    r = client.post("/retire_horse", data={"horse_name": "全能強馬"})
    assert r.status_code == 302
    assert appmod.get_game().horse_by_name("全能強馬").retired is True


def test_assign_breeding_role_route_requires_retirement_and_age(client):
    game = appmod.get_game()
    stallion = next(h for h in game.horses if h.sex == "公")

    # 還沒退役，應該失敗
    client.post("/assign_breeding_role", data={"horse_name": stallion.name, "role": "種馬"})
    assert stallion.breeding_role is None

    client.post("/retire_horse", data={"horse_name": stallion.name})
    stallion.age = 5
    client.post("/assign_breeding_role", data={"horse_name": stallion.name, "role": "種馬"})
    assert stallion.breeding_role == "種馬"


def test_breed_route_full_flow_produces_pregnancy(client, monkeypatch):
    import random

    game = appmod.get_game()
    stallion = next(h for h in game.horses if h.sex == "公")
    mare = next(h for h in game.horses if h.sex == "母")
    for h in (stallion, mare):
        client.post("/retire_horse", data={"horse_name": h.name})
        h.age = 5

    client.post("/assign_breeding_role", data={"horse_name": stallion.name, "role": "種馬"})
    client.post("/assign_breeding_role", data={"horse_name": mare.name, "role": "繁殖母馬"})

    monkeypatch.setattr(random, "random", lambda: 0.0)  # 強制配種成功
    r = client.post("/breed", data={"mare_name": mare.name, "stallion_name": stallion.name})
    assert r.status_code == 302
    assert mare.pregnant_weeks_remaining > 0

    body = client.get("/breeding").get_data(as_text=True)
    assert "懷孕中" in body


# ------------------------------------------------- 幼駒/種馬/繁殖母馬市場(cli/horse_market.py)

def test_horse_market_page_shows_all_four_market_sections(client):
    body = client.get("/horse_market").get_data(as_text=True)
    assert "現役馬市場" in body
    assert "幼駒市場" in body
    assert "種馬市場" in body
    assert "繁殖母馬市場" in body


def test_buy_foal_route_adds_to_stable_and_removes_from_market(client):
    game = appmod.get_game()
    game.money = 200000.0
    target = game.foal_market[0].name

    r = client.post("/buy_foal", data={"horse_name": target})
    assert r.status_code == 302
    assert any(h.name == target for h in game.horses)
    assert not any(h.name == target for h in game.foal_market)


def test_buy_stallion_route_registers_ready_to_breed(client):
    game = appmod.get_game()
    game.money = 500000.0
    target = game.stallion_market[0].name

    r = client.post("/buy_stallion", data={"horse_name": target})
    assert r.status_code == 302
    horse = game.horse_by_name(target)
    assert horse.breeding_role == "種馬"
    assert horse.retired is True


def test_buy_broodmare_route_registers_ready_to_breed(client):
    game = appmod.get_game()
    game.money = 500000.0
    target = game.broodmare_market[0].name

    r = client.post("/buy_broodmare", data={"horse_name": target})
    assert r.status_code == 302
    horse = game.horse_by_name(target)
    assert horse.breeding_role == "繁殖母馬"
    assert horse.retired is True
