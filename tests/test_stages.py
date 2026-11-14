"""The growing outline (stages.geojson): built from the changes inside the primary scope, checked by the contract."""
import json
import shutil
from pathlib import Path

import pytest
from shapely.geometry import box, mapping, shape

from sarwatch import pipeline
from sarwatch.contract import validate
from sarwatch.verdict import _refresh_stages

DATA = Path(__file__).resolve().parents[1] / "app" / "data"
SCOPE = box(26.0, 64.8, 26.1, 64.9)


def change(i, day, west, verdict="review", south=64.82, size=0.008):
    g = box(west, south, west + size, south + size)
    return {"type": "Feature", "geometry": mapping(g), "properties": {"id": f"c-{i}", "first_date": day, "verdict": verdict}}


def features():
    return [
        change(1, "2026-04-29", 26.02, "high_concern"),
        change(2, "2026-06-30", 26.03, "review"),
        change(3, "2026-06-30", 26.04, "expected"),
        change(4, "2026-04-29", 26.50, "high_concern"),  # outside the scope: never a member
    ]


def test_stages_grow_and_only_scope_members_count():
    stages = pipeline.clearing_stages(features(), SCOPE)
    assert [s["properties"]["date"] for s in stages] == ["2026-04-29", "2026-06-30"]
    first, second = (s["properties"] for s in stages)
    assert first["members"] == ["c-1"] and second["members"] == ["c-1", "c-2", "c-3"]
    assert first["group"] == "clearing" and first["title"] == "Cleared area"
    assert second["area_ha"] > first["area_ha"] > 0
    assert first["verdict"] == second["verdict"] == "high_concern"
    assert all(s["geometry"]["type"] in ("Polygon", "MultiPolygon") for s in stages)


def test_each_stage_covers_the_earlier_one():
    a, b = (shape(s["geometry"]) for s in pipeline.clearing_stages(features(), SCOPE))
    assert a.difference(b).area < 0.02 * a.area


def test_strongest_verdict_wins_and_none_is_weakest():
    fs = [change(1, "2026-04-29", 26.02, None), change(2, "2026-05-31", 26.03, "expected"),
          change(3, "2026-06-30", 26.04, "review")]
    assert [s["properties"]["verdict"] for s in pipeline.clearing_stages(fs, SCOPE)] == [None, "expected", "review"]


def test_no_member_no_stages():
    assert pipeline.clearing_stages([change(1, "2026-04-29", 26.5)], SCOPE) == []


def test_muhos_file_on_main_is_what_the_pipeline_writes(tmp_path):
    site_dir = tmp_path / "muhos"
    site_dir.mkdir()
    shutil.copy(DATA / "muhos" / "changes.geojson", site_dir)
    assert pipeline.write_stages(site_dir, pipeline.SITES["muhos"]) == 7
    assert (site_dir / "stages.geojson").read_bytes() == (DATA / "muhos" / "stages.geojson").read_bytes()


def test_verdict_step_refreshes_the_stage_colour(tmp_path):
    path = tmp_path / "stages.geojson"
    shutil.copy(DATA / "muhos" / "stages.geojson", path)
    changes = json.loads((DATA / "muhos" / "changes.geojson").read_text(encoding="utf-8"))
    for f in changes["features"]:
        f["properties"]["verdict"] = "expected"
    _refresh_stages(path, changes)
    assert {s["properties"]["verdict"] for s in json.loads(path.read_text(encoding="utf-8"))["features"]} == {"expected"}


@pytest.fixture
def copy(tmp_path):
    shutil.copytree(DATA, tmp_path / "data")
    return tmp_path / "data"


def _edit(data_dir, fn):
    path = data_dir / "muhos" / "stages.geojson"
    doc = json.loads(path.read_text(encoding="utf-8"))
    fn(doc["features"])
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_committed_stages_are_valid(copy):
    assert validate(copy) == []


@pytest.mark.parametrize("fn", [
    lambda fs: fs.reverse(),                                          # dates out of order
    lambda fs: fs[1]["properties"].update(area_ha=1.0),               # area shrinks
    lambda fs: fs[0]["properties"].update(members=["muhos-9999"]),    # unknown change
    lambda fs: fs[0]["properties"].update(date="2026-13-01"),
    lambda fs: fs[0]["properties"].update(verdict="fine"),
])
def test_bad_stages_are_rejected(copy, fn):
    _edit(copy, fn)
    assert validate(copy) != []
