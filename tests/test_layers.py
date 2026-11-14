"""Record map layers (#45), run offline on a small box at Agroparc from the saved responses in tests/fixtures/context/.

The box straddles the edge of the Ordal protected area, so every layer has features. Re-record: run with
``SARWATCH_LIVE=1 SARWATCH_RECORD=1`` (see test_context.py).
"""
import json
import os
from pathlib import Path

import pytest

from sarwatch.context import _common, layers

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "context"
RECORD = os.environ.get("SARWATCH_LIVE") == "1" and os.environ.get("SARWATCH_RECORD") == "1"
BOX = [1.86, 41.43, 1.87, 41.44]  # ~830 m x 1.1 km in the Agroparc box: protected edge + all three zoning classes


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setattr(_common, "CACHE_DIR", FIXTURES)
    mp.setattr(_common, "OFFLINE", not RECORD)
    out = tmp_path_factory.mktemp("context")
    index = layers.build("agroparc", out_dir=out, today="2026-11-14", bbox=BOX)
    mp.undo()
    return out, index


def _load(out, lid):
    return json.loads((out / f"{lid}.geojson").read_text(encoding="utf-8"))


def test_index_lists_every_layer_with_source_and_link(built):
    out, index = built
    assert [l["id"] for l in index["layers"]] == ["protected", "zoning", "buildings"]
    for l in index["layers"]:
        assert l["kind"] == l["id"] and l["file"] == f"{l['id']}.geojson" and (out / l["file"]).exists()
        assert l["source"] and l["url"].startswith("https://") and l["checked"] == "2026-11-14"
        assert len(l["title"]) <= 60 and 0 < len(l["note"]) <= 160
    assert json.loads((out / "index.json").read_text(encoding="utf-8")) == index
    solar = index["notes"][0]
    assert solar["kind"] == "solar" and "PSFV Gelida" in solar["note"] and len(solar["note"]) <= 160


def test_features_follow_the_contract(built):
    out, _ = built
    w, s, e, n = BOX
    for lid in ("protected", "zoning", "buildings"):
        doc = _load(out, lid)
        assert doc["type"] == "FeatureCollection" and doc["features"]
        for f in doc["features"]:
            assert f["geometry"]["type"] in ("Polygon", "MultiPolygon")
            assert f["properties"]["label"]
            rings = f["geometry"]["coordinates"] if f["geometry"]["type"] == "Polygon" else \
                [r for p in f["geometry"]["coordinates"] for r in p]
            for x, y in (pt for r in rings for pt in r):
                assert w - 1e-4 <= x <= e + 1e-4 and s - 1e-4 <= y <= n + 1e-4  # clipped to the box, lon/lat
                assert round(x, 6) == x and round(y, 6) == y
        assert (out / f"{lid}.geojson").stat().st_size <= layers.MAX_FILE


def test_layer_classes(built):
    out, _ = built
    assert {f["properties"]["class"] for f in _load(out, "protected")["features"]} <= {"natura2000", "pein", "other"}
    assert {f["properties"]["class"] for f in _load(out, "protected")["features"]} >= {"natura2000", "pein"}
    zones = {f["properties"]["class"] for f in _load(out, "zoning")["features"]}
    assert zones <= {"buildable", "non_buildable", "planned"} and "non_buildable" in zones
    years = [f["properties"].get("year") for f in _load(out, "buildings")["features"]]
    assert years and all(y is None or (isinstance(y, int) and 1700 <= y <= 2026) for y in years)


def test_a_failing_service_is_left_out(monkeypatch, tmp_path):
    monkeypatch.setattr(_common, "CACHE_DIR", tmp_path / "empty")
    monkeypatch.setattr(_common, "OFFLINE", True)  # every request misses: all services "fail"
    index = layers.build("agroparc", out_dir=tmp_path / "out", today="2026-11-14", bbox=BOX)
    assert index == {"layers": []}
    assert not list((tmp_path / "out").glob("*.geojson"))


def test_cadastre_grid_is_fixed():
    from sarwatch.context import cadastre
    a = cadastre.grid_tiles(400100, 4588100, 402000, 4589000)
    b = cadastre.grid_tiles(400050, 4588050, 402100, 4589050)  # the box grew a little
    assert set(a) <= set(b) and all(t[0] % cadastre.TILE_M == 0 and t[1] % cadastre.TILE_M == 0 for t in b)
    assert all((t[2] - t[0]) * (t[3] - t[1]) <= 1e6 for t in b)
