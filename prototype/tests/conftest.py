import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA_PATH = ROOT / "data" / "reference_horses.json"


@pytest.fixture(scope="session")
def reference_data():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)
