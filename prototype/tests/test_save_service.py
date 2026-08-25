"""版本化JSON存檔的完整狀態往返、原子寫入與損毀備份測試。"""
from __future__ import annotations

import json

import pytest

from cli.game import game_state_with_test_horses
from cli.injuries import Injury
from cli.save_service import (
    SAVE_VERSION,
    SaveError,
    backup_corrupt_save,
    delete_save,
    load_game,
    save_game,
)
from cli.trainers import Trainer
from cli.vets import Vet


def test_save_round_trip_preserves_complete_nested_state(tmp_path):
    state = game_state_with_test_horses()
    state.week = 37
    state.money = 54321.5
    state.horses[0].injury = Injury("測試傷病", "中傷", 3, ("速度", "力量"))
    state.horses[0].assigned_trainer = "測試教練"
    state.horses[0].assigned_vet = "測試獸醫"
    state.trainers = [Trainer("測試教練", "速度訓練", 4, 3200, 800)]
    state.vets = [Vet("測試獸醫", 3, 3000, 750)]
    state.transaction_history = ["第36週｜購入現役馬 測試馬｜-10,000"]
    path = tmp_path / "savegame.json"

    save_game(state, path)
    restored = load_game(path)

    assert restored.week == 37
    assert restored.money == pytest.approx(54321.5)
    assert restored.horses[0].injury == state.horses[0].injury
    assert restored.horses[0].assigned_trainer == "測試教練"
    assert restored.trainers == state.trainers
    assert restored.vets == state.vets
    assert restored.horse_market[0].name == state.horse_market[0].name
    assert restored.transaction_history == state.transaction_history
    assert not path.with_suffix(".json.tmp").exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["save_version"] == SAVE_VERSION
    assert payload["saved_at"]


def test_load_rejects_unknown_save_version(tmp_path):
    path = tmp_path / "savegame.json"
    path.write_text('{"save_version": 999, "game": {}}', encoding="utf-8")

    with pytest.raises(SaveError, match="不支援的存檔版本"):
        load_game(path)


def test_corrupt_save_is_backed_up_without_data_loss(tmp_path):
    path = tmp_path / "savegame.json"
    path.write_text("{broken-json", encoding="utf-8")

    with pytest.raises(SaveError):
        load_game(path)
    backup = backup_corrupt_save(path)

    assert backup is not None
    assert backup.read_text(encoding="utf-8") == "{broken-json"
    assert not path.exists()
    assert ".corrupt-" in backup.name


def test_delete_save_reports_if_file_existed(tmp_path):
    path = tmp_path / "savegame.json"
    assert delete_save(path) is False
    path.write_text("{}", encoding="utf-8")
    assert delete_save(path) is True
    assert not path.exists()
