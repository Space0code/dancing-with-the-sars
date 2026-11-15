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


# The outline goes through GEOS (union, simplify, buffer). Another GEOS release (it comes inside the shapely wheel) can write the same
# outline with the last digit of some coordinates different (about 1e-14 degrees) and the parts of a MultiPolygon in another order.
# 1e-9 degrees is about 0.1 mm: far below anything the app draws, far above that noise, and a real change (a moved vertex, a
# different simplification, another property) still fails. Properties are compared exactly.
GEOMETRY_TOLERANCE_DEG = 1e-9


def same_stages(written: dict, committed: dict) -> bool:
    """True when two stage files hold the same outlines: same properties, same shapes up to GEOMETRY_TOLERANCE_DEG, whatever
    the order of the parts inside a shape."""
    import shapely

    if {k: v for k, v in written.items() if k != "features"} != {k: v for k, v in committed.items() if k != "features"}:
        return False
    a, b = written["features"], committed["features"]
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x["properties"] != y["properties"] or x["geometry"]["type"] != y["geometry"]["type"]:
            return False
        if not shapely.normalize(shape(x["geometry"])).equals_exact(shapely.normalize(shape(y["geometry"])), GEOMETRY_TOLERANCE_DEG):
            return False
    return True


def test_muhos_file_on_main_is_what_the_pipeline_writes(tmp_path):
    site_dir = tmp_path / "muhos"
    site_dir.mkdir()
    shutil.copy(DATA / "muhos" / "changes.geojson", site_dir)
    assert pipeline.write_stages(site_dir, pipeline.SITES["muhos"]) == 7
    written = (site_dir / "stages.geojson").read_bytes()
    committed = (DATA / "muhos" / "stages.geojson").read_bytes()
    assert written == committed or same_stages(json.loads(written), json.loads(committed))


def test_stage_comparison_still_catches_real_changes():
    committed = json.loads((DATA / "muhos" / "stages.geojson").read_text(encoding="utf-8"))
    assert same_stages(committed, json.loads(json.dumps(committed)))

    def first_vertex(doc):  # [lon, lat] of the second vertex of the first ring (not the closing one, so the ring stays closed)
        c = doc["features"][0]["geometry"]["coordinates"]
        while isinstance(c[0][0], list):
            c = c[0]
        return c[1]

    for change_it in (
        lambda d: first_vertex(d).__setitem__(1, first_vertex(d)[1] + 1e-6),      # one vertex moved by about 10 cm
        lambda d: d["features"][0]["properties"].__setitem__("area_ha", 0.0),     # another property
        lambda d: d["features"].pop(),                                            # a stage missing
    ):
        other = json.loads(json.dumps(committed))
        change_it(other)
        assert not same_stages(other, committed)
    noise = json.loads(json.dumps(committed))
    first_vertex(noise)[1] += 1e-13  # last-digit noise is accepted
    assert same_stages(noise, committed)


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
