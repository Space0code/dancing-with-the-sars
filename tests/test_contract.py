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


@pytest.mark.parametrize("dates", [
    {"before_date": "15 Jan 2024"},                             # not YYYY-MM-DD
    {"before_date": "2026-12-01", "after_date": "2026-11-02"},  # later than after_date
])
def test_bad_evidence_before_date_is_rejected(copy, dates):
    path = copy / "fixture" / "changes.geojson"
    evidence = json.loads(path.read_text(encoding="utf-8"))["features"][0]["properties"]["evidence"]
    _edit_first_change(copy, evidence={**evidence, **dates})
    assert any("before_date" in e for e in validate(copy))


def test_a_site_folder_needs_no_story(copy):
    assert not (copy / "fixture" / "story.json").exists()
    assert validate(copy) == []


def _set_notes(data_dir, notes):
    path = data_dir / "sites.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    index["sites"][-1]["notes"] = notes
    path.write_text(json.dumps(index), encoding="utf-8")


def test_notes_are_optional_and_valid_when_present(copy):
    _set_notes(copy, ["Radar pictures are Sentinel-1 until June, NISAR after that.", "x" * 140])
    assert validate(copy) == []
    _set_notes(copy, [])
    assert validate(copy) == []


@pytest.mark.parametrize("notes", [
    "not a list",
    ["a", "b", "c", "d", "e"],  # more than 4
    ["x" * 141],                # too long
    [""],                       # empty
    [3],                        # not text
])
def test_bad_notes_are_rejected(copy, notes):
    _set_notes(copy, notes)
    assert any("notes" in e for e in validate(copy))


def test_series_events_are_optional(copy):
    path = next((copy / "fixture" / "series").glob("*.json"))
    doc = json.loads(path.read_text(encoding="utf-8"))
    del doc["events"]
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert validate(copy) == []


def test_not_ready_site_needs_no_files(copy):
    shutil.rmtree(copy / "fixture")
    index = json.loads((copy / "sites.json").read_text(encoding="utf-8"))
    for site in index["sites"]:
        site["ready"] = False
    (copy / "sites.json").write_text(json.dumps(index), encoding="utf-8")
    assert validate(copy) == []


def _set_snapshots(data_dir, snapshots):
    path = data_dir / "sites.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    next(s for s in index["sites"] if s["id"] == "fixture")["snapshots"] = snapshots
    path.write_text(json.dumps(index), encoding="utf-8")


def test_valid_snapshots_are_accepted(copy):
    _set_snapshots(copy, [{"date": "2024-01-01", "sensor": "NISAR L-band"},
                          {"date": "2025-03-04", "sensor": "NISAR L-band + Sentinel-1 C-band"}])
    assert validate(copy) == []


@pytest.mark.parametrize("snapshots, message", [
    ("2024-01-01", "must be a list"),
    ([{"date": "2024-13-01", "sensor": "x"}], "YYYY-MM-DD"),
    (["2024-01-01"], "YYYY-MM-DD"),
    ([{"date": "2024-02-01", "sensor": ""}], "sensor"),
    ([{"date": "2024-02-01"}], "sensor"),
    ([{"date": "2024-03-01", "sensor": "x"}, {"date": "2024-02-01", "sensor": "x"}], "sorted"),
    ([{"date": "2024-03-01", "sensor": "x"}, {"date": "2024-03-01", "sensor": "y"}], "sorted"),
    ([{"date": "2023-12-31", "sensor": "x"}], "outside time_range"),
    ([{"date": "2030-01-01", "sensor": "x"}], "outside time_range"),
])
def test_bad_snapshots_are_rejected(copy, snapshots, message):
    _set_snapshots(copy, snapshots)
    assert any(message in e for e in validate(copy))


@pytest.mark.parametrize("note", ["", 5])
def test_bad_series_note_is_rejected(copy, note):
    path = next((copy / "fixture").glob("series/*.json"))
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["series"][0]["note"] = note
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert any("note" in e for e in validate(copy))
