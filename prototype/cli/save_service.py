"""版本化本機 JSON 存檔服務。

只接受本專案明確定義的 dataclass，不使用 pickle。寫入時先產生同目錄暫存檔，再以
Path.replace() 原子替換正式檔；讀取失敗時可由 load_or_backup_corrupt() 保留損毀副本。
"""
from __future__ import annotations

import json
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from .game import GameState, Jockey
from .horses import Horse
from .injuries import Injury
from .trainers import Trainer
from .vets import Vet

SAVE_VERSION = 1


class SaveError(RuntimeError):
    """存檔無法讀取、驗證或寫入。"""


T = TypeVar("T")


def _known_kwargs(cls: type[T], data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SaveError(f"{cls.__name__} 資料格式錯誤")
    names = {item.name for item in fields(cls)}
    return {key: value for key, value in data.items() if key in names}


def _injury_from_dict(data: dict[str, Any] | None) -> Injury | None:
    if data is None:
        return None
    values = _known_kwargs(Injury, data)
    values["affected_stats"] = tuple(values.get("affected_stats", ()))
    return Injury(**values)


def _horse_from_dict(data: dict[str, Any]) -> Horse:
    values = _known_kwargs(Horse, data)
    values["injury"] = _injury_from_dict(values.get("injury"))
    return Horse(**values)


def _list_of(cls: type[T], values: Any) -> list[T]:
    if not isinstance(values, list):
        raise SaveError(f"{cls.__name__} 清單格式錯誤")
    return [cls(**_known_kwargs(cls, item)) for item in values]


def game_state_to_dict(state: GameState) -> dict[str, Any]:
    return asdict(state)


def game_state_from_dict(data: dict[str, Any]) -> GameState:
    values = _known_kwargs(GameState, data)
    values["horses"] = [_horse_from_dict(item) for item in values.get("horses", [])]
    raw_jockeys = values.get("jockeys", {})
    if not isinstance(raw_jockeys, dict):
        raise SaveError("Jockey 資料格式錯誤")
    values["jockeys"] = {
        name: Jockey(**_known_kwargs(Jockey, jockey)) for name, jockey in raw_jockeys.items()
    }
    for key in ("horse_market", "foal_market", "stallion_market", "broodmare_market"):
        values[key] = [_horse_from_dict(item) for item in values.get(key, [])]
    values["trainers"] = _list_of(Trainer, values.get("trainers", []))
    values["trainer_market"] = _list_of(Trainer, values.get("trainer_market", []))
    values["vets"] = _list_of(Vet, values.get("vets", []))
    values["vet_market"] = _list_of(Vet, values.get("vet_market", []))
    return GameState(**values)


def save_game(state: GameState, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "save_version": SAVE_VERSION,
        "saved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "game": game_state_to_dict(state),
    }
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
        temporary.replace(destination)
    except (OSError, TypeError, ValueError) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise SaveError(f"無法寫入存檔：{exc}") from exc
    return destination


def load_game(path: str | Path) -> GameState:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SaveError("存檔根節點不是物件")
        version = payload.get("save_version")
        if version != SAVE_VERSION:
            raise SaveError(f"不支援的存檔版本：{version}（目前支援 {SAVE_VERSION}）")
        game = payload.get("game")
        if not isinstance(game, dict):
            raise SaveError("存檔缺少 game 狀態")
        return game_state_from_dict(game)
    except SaveError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SaveError(f"無法讀取存檔：{exc}") from exc


def backup_corrupt_save(path: str | Path) -> Path | None:
    source = Path(path)
    if not source.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = source.with_name(f"{source.stem}.corrupt-{timestamp}{source.suffix}")
    counter = 1
    while backup.exists():
        backup = source.with_name(f"{source.stem}.corrupt-{timestamp}-{counter}{source.suffix}")
        counter += 1
    source.replace(backup)
    return backup


def delete_save(path: str | Path) -> bool:
    source = Path(path)
    if not source.exists():
        return False
    source.unlink()
    return True
