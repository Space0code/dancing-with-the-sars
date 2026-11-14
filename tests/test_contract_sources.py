"""Optional multi-sensor fields of the contract (kb/multi-sensor-design.md, kb/data-contract.md)."""
import json
import shutil
from pathlib import Path

import pytest

from sarwatch.contract import validate

DATA = Path(__file__).resolve().parents[1] / "app" / "data"


@pytest.fixture
def copy(tmp_path):
    shutil.copytree(DATA, tmp_path / "data")
    return tmp_path / "data"


def _read_changes(data_dir):
    return json.loads((data_dir / "fixture" / "changes.geojson").read_text(encoding="utf-8"))


def _props(data_dir, num):
    return _read_changes(data_dir)["features"][num]["properties"]


def _set_change(data_dir, num, **props):
    doc = _read_changes(data_dir)
    doc["features"][num]["properties"].update(props)
    (data_dir / "fixture" / "changes.geojson").write_text(json.dumps(doc), encoding="utf-8")


def _multi(data_dir):
    """Index of the fixture change that carries three sources."""
    return next(i for i in range(7) if len(_props(data_dir, i).get("sources", [])) == 3)


def _set_source(data_dir, num, index, **fields):
    sources = _props(data_dir, num)["sources"]
    sources[index].update(fields)
    _set_change(data_dir, num, sources=sources)


def _set_site_source(data_dir, index, **fields):
    path = data_dir / "sites.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    site = next(s for s in doc["sites"] if s["id"] == "fixture")
    site["sources"][index].update(fields)
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_fixture_has_changes_with_and_without_sources():
    props = [f["properties"] for f in _read_changes(DATA)["features"]]
    assert sum("sources" in p for p in props) == 3
    assert sum("sources" not in p for p in props) == 4


def test_data_without_the_new_fields_stays_valid(copy):
    doc = _read_changes(copy)
    for f in doc["features"]:
        f["properties"].pop("sources", None)
        f["properties"].pop("not_before", None)
    (copy / "fixture" / "changes.geojson").write_text(json.dumps(doc), encoding="utf-8")
    index = json.loads((copy / "sites.json").read_text(encoding="utf-8"))
    for site in index["sites"]:
        site.pop("sources", None)
    (copy / "sites.json").write_text(json.dumps(index), encoding="utf-8")
    assert validate(copy) == []


@pytest.mark.parametrize("fields", [
    {"role": "seen"},
    {"kind": "sonar"},
    {"share": 1.2},
    {"share": -0.1},
    {"confidence": "certain"},
    {"area_ha": 0},
    {"first_date": "2025-13-01"},
    {"not_before": "2025-08-01"},   # after first_date
    {"last_date": "2025-07-01"},    # before first_date
    {"note": None},
    {"sensor": ""},
])
def test_bad_change_source_is_rejected(copy, fields):
    _set_source(copy, _multi(copy), 0, **fields)
    assert any("sources[0]" in e for e in validate(copy))


@pytest.mark.parametrize("role", ["not_seen", "not_watching"])
@pytest.mark.parametrize("fields", [
    {"first_date": "2025-07-15"},
    {"last_date": "2025-07-15"},
    {"not_before": "2025-07-01"},
    {"confidence": "low"},
])
def test_dates_and_confidence_must_be_null_without_detection(copy, role, fields):
    num = _multi(copy)
    _set_source(copy, num, 0, role=role, first_date=None, last_date=None, not_before=None, confidence=None)
    assert validate(copy) == []
    _set_source(copy, num, 0, **fields)
    assert any("null for role" in e for e in validate(copy))


def test_valid_source_values_are_accepted(copy):
    num = _multi(copy)
    _set_source(copy, num, 0, role="not_watching", first_date=None, last_date=None, not_before=None,
                confidence=None, area_ha=None, share=None)
    _set_source(copy, num, 1, confidence=None, share=0, not_before=None)
    assert validate(copy) == []


def test_change_sources_must_be_a_list(copy):
    _set_change(copy, 0, sources={"sensor": "x"})
    assert any("sources must be a list" in e for e in validate(copy))


@pytest.mark.parametrize("value", ["2026-01-01", "bad"])
def test_bad_change_not_before_is_rejected(copy, value):
    _set_change(copy, 0, first_date="2025-03-15", last_date="2025-03-15", not_before=value)
    assert any("not_before" in e for e in validate(copy))


@pytest.mark.parametrize("value", [None, "2025-03-15", "2025-03-01"])
def test_good_change_not_before_is_accepted(copy, value):
    _set_change(copy, 0, first_date="2025-03-15", last_date="2025-03-15", not_before=value)
    assert validate(copy) == []


@pytest.mark.parametrize("fields", [
    {"risky_months": [11, 12, 13]},
    {"risky_months": [0]},
    {"risky_months": "winter"},
    {"kind": "lidar"},
    {"start": "2016"},
    {"end": "2015-01-01"},
    {"revisit_days": 0},
    {"revisit_days": "weekly"},
    {"sees": ["volcano"]},
    {"sees": "clearing"},
    {"sensor": ""},
])
def test_bad_site_source_is_rejected(copy, fields):
    _set_site_source(copy, 1, **fields)
    assert any("sources[1]" in e for e in validate(copy))


def test_valid_site_source_is_accepted(copy):
    _set_site_source(copy, 0, end="2030-01-01", sees=[], risky_months=[1, 12])
    assert validate(copy) == []
