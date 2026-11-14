"""The fake fixture site must satisfy the contract; broken copies must not."""
import json
import shutil
from pathlib import Path

import pytest

from sarwatch.contract import validate

DATA = Path(__file__).resolve().parents[1] / "app" / "data"


def test_committed_data_is_valid():
    assert validate(DATA) == []


@pytest.fixture
def copy(tmp_path):
    shutil.copytree(DATA, tmp_path / "data")
    return tmp_path / "data"


def _edit_first_change(data_dir, **props):
    path = data_dir / "fixture" / "changes.geojson"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["features"][0]["properties"].update(props)
    path.write_text(json.dumps(doc), encoding="utf-8")


@pytest.mark.parametrize("props", [
    {"verdict": "illegal"},
    {"type": "volcano"},
    {"first_date": "2026-13-01"},
    {"area_ha": 0},
    {"reasons": []},
    {"evidence": {"before": "evidence/nope.png", "after": None, "series": None}},
])
def test_bad_change_is_rejected(copy, props):
    _edit_first_change(copy, **props)
    assert validate(copy) != []


def test_missing_story_is_rejected(copy):
    (copy / "fixture" / "story.json").unlink()
    assert any("story.json" in e for e in validate(copy))


def test_not_ready_site_needs_no_files(copy):
    shutil.rmtree(copy / "fixture")
    index = json.loads((copy / "sites.json").read_text(encoding="utf-8"))
    for site in index["sites"]:
        site["ready"] = False
    (copy / "sites.json").write_text(json.dumps(index), encoding="utf-8")
    assert validate(copy) == []
