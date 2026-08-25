"""比賽引擎 vs 數值平衡試算.xlsx「比賽模擬」分頁 — 逐匹馬、逐階段比對。"""
import pytest

from engine.race import (
    HorseRaceInput,
    external_multiplier,
    simulate_race,
    simulate_stamina,
)

STAGE_KEY = {
    "起跑": "起跑",
    "前段": "前段",
    "中段": "中段",
    "後段": "後段",
    "彎道": "彎道",
    "衝刺": "衝刺",
}


def build_horse(d: dict) -> HorseRaceInput:
    return HorseRaceInput(
        name=d["馬匹名稱"],
        speed=d["速度"],
        stamina=d["耐力"],
        acceleration=d["加速"],
        power=d["力量"],
        guts=d["根性"],
        intelligence=d["智力"],
        start=d["起跑"],
        corner=d["彎道"],
        tactic_stat=d["戰術(屬性)"],
        mental=d["精神"],
        health=d["健康"],
        pace=d["跑法"],
        distance_affinity=d["距離適性等級"],
        terrain_affinity=d["場地適性等級"],
        status_grade=d["狀態等級"],
        weight_diff_kg=d["負磅差(kg)"],
        jockey_correction=d["騎師修正(整體)"],
        jockey_position_judgement=d["騎師-位置判斷"],
        jockey_rhythm_control=d["騎師-節奏控制"],
        jockey_route_choice=d["騎師-路線選擇"],
        trait_bonus_pct=d["特性加成%"],
        tactic_volatility_pct=d["戰術波動%"],
        random_volatility_pct=d["隨機波動%"],
        tactic_stamina_multiplier=d["戰術體力修正"],
    )


@pytest.fixture(scope="module")
def race_setup(reference_data):
    horses = [build_horse(d) for d in reference_data["horses"]]
    meta = reference_data["meta"]
    results = simulate_race(horses, distance_mod=meta["distance_mod"], terrain_mod=meta["terrain_mod"])
    by_name = {r.name: r for r in results}
    expected_by_name = {row["馬匹名稱"]: row for row in reference_data["race_results"]}
    return horses, by_name, expected_by_name


def test_external_multiplier_matches_spreadsheet(reference_data, race_setup):
    horses, _, expected_by_name = race_setup
    for h in horses:
        expected = expected_by_name[h.name]["外部乘數(輔助)"]
        assert external_multiplier(h) == pytest.approx(expected, rel=1e-9)


def test_stamina_remaining_matches_spreadsheet(reference_data, race_setup):
    horses, _, expected_by_name = race_setup
    meta = reference_data["meta"]
    for h in horses:
        remaining = simulate_stamina(h, meta["distance_mod"], meta["terrain_mod"])
        expected = expected_by_name[h.name]
        assert remaining["前段"] == pytest.approx(expected["前段剩餘"], rel=1e-9)
        assert remaining["中段"] == pytest.approx(expected["中段剩餘"], rel=1e-9)
        assert remaining["後段"] == pytest.approx(expected["後段剩餘"], rel=1e-9)


@pytest.mark.parametrize(
    "stage", ["起跑", "前段", "中段", "後段", "彎道", "衝刺"]
)
def test_stage_position_value_matches_spreadsheet(reference_data, race_setup, stage):
    horses, by_name, expected_by_name = race_setup
    for h in horses:
        result = by_name[h.name]
        stage_result = next(s for s in result.stages if s.stage == stage)
        expected_key = f"{stage}_位置值" if stage != "衝刺" else "衝刺_位置值(終點)"
        expected = expected_by_name[h.name][expected_key]
        assert stage_result.position_value == pytest.approx(expected, rel=1e-6), (
            f"{h.name} {stage} 位置值不符：程式={stage_result.position_value} 試算表={expected}"
        )


def test_final_rank_matches_spreadsheet(reference_data, race_setup):
    horses, by_name, expected_by_name = race_setup
    for h in horses:
        result = by_name[h.name]
        expected_rank = expected_by_name[h.name]["最終名次"]
        assert result.rank == expected_rank, (
            f"{h.name} 名次不符：程式={result.rank} 試算表={expected_rank}"
        )


def test_ranks_form_a_permutation_of_1_to_n(race_setup):
    _, by_name, _ = race_setup
    ranks = sorted(r.rank for r in by_name.values())
    assert ranks == list(range(1, len(ranks) + 1))
