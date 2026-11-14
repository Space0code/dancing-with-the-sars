"""Synthetic end-to-end tests for sarwatch.export: speckle stacks on UTM grids -> detect_changes -> write_site.

Two runs over the same ground near lon 1.85, lat 41.45: "NISAR" (HH/HV, 20 m, EPSG:32631) with an injected
clearing and an injected structure, and "Sentinel-1" (VV/VH, 30 m, EPSG:25831, a shifted grid that covers the
clearing but not the structure) with the same clearing.
"""
import json
from datetime import date, timedelta

import numpy as np
import pytest
from PIL import Image
from pyproj import Geod, Transformer
from shapely.geometry import shape

from sarwatch import export
from sarwatch.change import detect_changes
from sarwatch.contract import validate
from sarwatch.export import Run, write_site

SITE = "testsite"
GEOD = Geod(ellps="WGS84")

# NISAR-like run
EPSG, PX, NY, NX = 32631, 20.0, 120, 160
DATES = [date(2026, 6, 23) + timedelta(days=12 * i) for i in range(12)]
CLEAR, CLEAR_PASS = (slice(30, 70), slice(30, 80)), 4    # 40 x 50 px = 80 ha, HV -6 dB from pass 4
CLEAR_HA = 80.0
BUILD, BUILD_PASS = (slice(80, 100), slice(120, 145)), 7  # 20 x 25 px = 20 ha, HH +8 dB from pass 7
NO_DATA_COLS = 3                                           # left columns are NaN in every pass

_cx, _cy = Transformer.from_crs(4326, EPSG, always_xy=True).transform(1.85, 41.45)
X0 = round((_cx - NX * PX / 2) / PX) * PX
Y0 = round((_cy + NY * PX / 2) / PX) * PX
TRANSFORM = (PX, 0.0, X0, 0.0, -PX, Y0)

# Sentinel-1-like run: coarser, shifted grid in another (compatible) CRS
S1_EPSG, S1_PX, S1_NY, S1_NX = 25831, 30.0, 80, 70
S1_TRANSFORM = (S1_PX, 0.0, X0 - 7.0, 0.0, -S1_PX, Y0 + 11.0)
S1_DATES = [date(2026, 5, 2) + timedelta(days=12 * i) for i in range(14)]


def gain(db):
    return 10 ** (db / 10)


def speckle(rng, mean, shape, looks=16):
    return rng.gamma(looks, mean / looks, size=shape).astype(np.float32)


def lonlat(x, y, epsg=EPSG):
    return Transformer.from_crs(epsg, 4326, always_xy=True).transform(x, y)


@pytest.fixture(scope="module")
def runs():
    rng = np.random.default_rng(0)
    stack = {"HH": speckle(rng, 0.1, (len(DATES), NY, NX)), "HV": speckle(rng, 0.02, (len(DATES), NY, NX))}
    stack["HV"][CLEAR_PASS:, CLEAR[0], CLEAR[1]] *= gain(-6)
    stack["HH"][BUILD_PASS:, BUILD[0], BUILD[1]] *= gain(8)
    for arr in stack.values():
        arr[:, :, :NO_DATA_COLS] = np.nan
    nisar = Run("NISAR L-band", detect_changes(stack, DATES, (PX, PX)), DATES, stack, TRANSFORM, EPSG)

    # S1 pixels whose centre falls inside the clearing (tested in the NISAR grid's metres)
    a, _, c, _, e, f = S1_TRANSFORM
    cols, rows = np.meshgrid(np.arange(S1_NX) + 0.5, np.arange(S1_NY) + 0.5)
    x, y = Transformer.from_crs(S1_EPSG, EPSG, always_xy=True).transform(a * cols + c, e * rows + f)
    col, row = (x - X0) / PX, (Y0 - y) / PX
    inside = (row >= CLEAR[0].start) & (row < CLEAR[0].stop) & (col >= CLEAR[1].start) & (col < CLEAR[1].stop)
    s1_stack = {"VV": speckle(rng, 0.12, (len(S1_DATES), S1_NY, S1_NX)),
                "VH": speckle(rng, 0.025, (len(S1_DATES), S1_NY, S1_NX))}
    for t, d in enumerate(S1_DATES):
        if d >= DATES[CLEAR_PASS]:
            s1_stack["VH"][t][inside] *= gain(-5)
    s1 = Run("Sentinel-1 C-band", detect_changes(s1_stack, S1_DATES, (S1_PX, S1_PX)), S1_DATES, s1_stack,
             S1_TRANSFORM, S1_EPSG)
    assert [r.type for r in nisar.result.regions] == ["clearing", "structure"]
    assert [r.type for r in s1.result.regions] == ["clearing"]
    return nisar, s1


@pytest.fixture
def site(tmp_path):
    data = tmp_path / "data"
    site_dir = data / SITE
    site_dir.mkdir(parents=True)
    sites = {"version": 1, "sites": [{
        "id": SITE, "name": "Synthetic test site", "country": "ES", "ready": True, "center": [1.85, 41.45],
        "zoom": 13, "bbox": [1.82, 41.43, 1.88, 41.47], "time_range": ["2026-05-01", "2026-11-01"]}]}
    (data / "sites.json").write_text(json.dumps(sites), encoding="utf-8")
    story = {"headline": "Synthetic", "story": ["Test data."], "events": [], "sources": []}
    (site_dir / "story.json").write_text(json.dumps(story), encoding="utf-8")
    return data, site_dir


def load(site_dir, rel):
    return json.loads((site_dir / rel).read_text(encoding="utf-8"))


def by_sensor_type(features, sensor, kind):
    (hit,) = [f for f in features if f["properties"]["sensor"] == sensor and f["properties"]["type"] == kind]
    return hit


def test_two_runs_give_a_valid_site_in_the_right_place(runs, site):
    data, site_dir = site
    summary = write_site(site_dir, SITE, list(runs))

    assert validate(data) == []
    feats = load(site_dir, "changes.geojson")["features"]
    assert summary["changes"] == len(feats) == 3
    assert summary["by_type"] == {"clearing": 2, "structure": 1}
    assert summary["area_ha"] == pytest.approx(sum(f["properties"]["area_ha"] for f in feats), abs=0.01)

    props = [f["properties"] for f in feats]
    assert [p["id"] for p in props] == [f"{SITE}-{n:04d}" for n in range(1, 4)]
    keys = [(p["first_date"], -p["area_ha"]) for p in props]
    assert keys == sorted(keys)

    # the NISAR clearing: placed within one pixel, right size, plain-language evidence
    clearing = by_sensor_type(feats, "NISAR L-band", "clearing")
    p = clearing["properties"]
    poly = shape(clearing["geometry"])
    assert poly.is_valid and clearing["geometry"]["type"] == "Polygon"
    exp_lon, exp_lat = lonlat(X0 + PX * (CLEAR[1].start + CLEAR[1].stop) / 2,
                              Y0 - PX * (CLEAR[0].start + CLEAR[0].stop) / 2)
    _, _, dist_m = GEOD.inv(poly.centroid.x, poly.centroid.y, exp_lon, exp_lat)
    assert dist_m <= PX
    area_m2, _ = GEOD.geometry_area_perimeter(poly)
    assert abs(area_m2) / 1e4 == pytest.approx(CLEAR_HA, rel=0.2)
    assert area_m2 > 0  # counter-clockwise exterior (RFC 7946)
    assert p["area_ha"] == pytest.approx(CLEAR_HA, rel=0.2)
    assert p["signal"]["metric"] == "HV_dB" and p["signal"]["delta"] == pytest.approx(-6, abs=0.5)
    assert p["signal"]["delta"] == round(p["signal"]["delta"], 1)
    assert p["verdict"] is None and p["reasons"] == []
    assert "vegetation echo drop by 6 dB" in p["explain"] and "trees" in p["explain"]
    assert "Aug 2026" in p["explain"]
    for ring in clearing["geometry"]["coordinates"]:
        assert ring[0] == ring[-1]
        assert all(v == round(v, 6) for pt in ring for v in pt)

    structure = by_sensor_type(feats, "NISAR L-band", "structure")["properties"]
    assert structure["signal"]["metric"] == "HH_dB"
    assert "surface echo rise by" in structure["explain"]
    assert by_sensor_type(feats, "Sentinel-1 C-band", "clearing")["properties"]["signal"]["metric"] == "VH_dB"


def test_site_pictures_have_corners_in_contract_order(runs, site):
    _, site_dir = site
    write_site(site_dir, SITE, list(runs))
    layers = load(site_dir, "layers.json")["layers"]

    assert [l["id"] for l in layers] == ["nisar_l_band_before", "nisar_l_band_after",
                                         "sentinel_1_c_band_before", "sentinel_1_c_band_after"]
    for layer in layers:
        tl, tr, br, bl = layer["coordinates"]
        assert tl[1] > bl[1] and tr[1] > br[1]  # top is north
        assert tl[0] < tr[0] and bl[0] < br[0]  # left is west
        img = Image.open(site_dir / layer["url"])
        assert max(img.size) <= export.MAX_LAYER_PX
        assert "NISAR" in layer["title"] or "Sentinel-1" in layer["title"]
        assert "Red = surface echo" in layer["caption"] and "Green = vegetation echo" in layer["caption"]

    before, after = layers[0], layers[1]
    assert before["date"] == DATES[1].isoformat() and after["date"] == DATES[-2].isoformat()
    expected = [lonlat(X0 + PX * c, Y0 - PX * r) for c, r in ((0, 0), (NX, 0), (NX, NY), (0, NY))]
    assert np.allclose(before["coordinates"], expected, atol=2e-6)
    rgba = np.array(Image.open(site_dir / before["url"]))
    assert rgba.shape == (NY, NX, 4)
    assert (rgba[:, :NO_DATA_COLS, 3] == 0).all() and (rgba[:, NO_DATA_COLS:, 3] == 255).all()
    # the clearing turns from green-yellow (canopy) towards purple-blue (bare): green falls, blue rises
    after_rgba = np.array(Image.open(site_dir / after["url"]))
    inner = (slice(CLEAR[0].start + 5, CLEAR[0].stop - 5), slice(CLEAR[1].start + 5, CLEAR[1].stop - 5))
    assert after_rgba[inner][..., 1].mean() < rgba[inner][..., 1].mean() - 40
    assert after_rgba[inner][..., 2].mean() > rgba[inner][..., 2].mean() + 40


def test_evidence_pictures_are_sized_and_outlined(runs, site):
    _, site_dir = site
    write_site(site_dir, SITE, list(runs))
    for feature in load(site_dir, "changes.geojson")["features"]:
        for key in ("before", "after"):
            img = Image.open(site_dir / feature["properties"]["evidence"][key])
            assert min(img.size) >= export.EVIDENCE_SHORT_MIN and max(img.size) <= export.EVIDENCE_LONG_MAX
            rgba = np.array(img.convert("RGBA"))
            assert (rgba.reshape(-1, 4) == export.OUTLINE_RGBA).all(axis=1).sum() > 100


def test_series_include_other_sensors_over_the_same_ground(runs, site):
    _, site_dir = site
    write_site(site_dir, SITE, list(runs))
    feats = load(site_dir, "changes.geojson")["features"]

    def series_of(sensor, kind):
        return load(site_dir, by_sensor_type(feats, sensor, kind)["properties"]["evidence"]["series"])

    doc = series_of("NISAR L-band", "clearing")
    names = [(s["name"], s["sensor"]) for s in doc["series"]]
    assert names == [("Vegetation echo (HV)", "NISAR L-band"), ("Surface echo (HH)", "NISAR L-band"),
                     ("Vegetation echo (VH)", "Sentinel-1 C-band"), ("Surface echo (VV)", "Sentinel-1 C-band")]
    s1_vh = doc["series"][2]
    assert s1_vh["dates"] == [d.isoformat() for d in S1_DATES]
    assert np.median(s1_vh["values"][-3:]) - np.median(s1_vh["values"][:3]) < -3  # S1 saw the same clearing
    hv = doc["series"][0]["values"]
    assert np.median(hv[-3:]) - np.median(hv[:3]) == pytest.approx(-6, abs=0.5)
    assert all(v == round(v, 2) for s in doc["series"] for v in s["values"])
    assert doc["events"] == [{"date": by_sensor_type(feats, "NISAR L-band", "clearing")["properties"]["first_date"],
                              "label": "Change first seen"}]

    # the S1 change gets NISAR's history; the structure lies outside the S1 grid, so it gets none
    assert {s["sensor"] for s in series_of("Sentinel-1 C-band", "clearing")["series"]} == {
        "Sentinel-1 C-band", "NISAR L-band"}
    assert {s["sensor"] for s in series_of("NISAR L-band", "structure")["series"]} == {"NISAR L-band"}


def test_rerun_with_fewer_changes_leaves_no_stale_files(runs, site):
    data, site_dir = site
    write_site(site_dir, SITE, list(runs))
    story = (site_dir / "story.json").read_bytes()
    (site_dir / "notes.txt").write_text("not the exporter's", encoding="utf-8")

    summary = write_site(site_dir, SITE, [runs[0]])

    assert summary["changes"] == 2 and validate(data) == []
    feats = load(site_dir, "changes.geojson")["features"]
    ids = [f["properties"]["id"] for f in feats]
    assert sorted(p.name for p in (site_dir / "evidence").iterdir()) == sorted(
        f"{i}_{k}.png" for i in ids for k in ("before", "after"))
    assert sorted(p.name for p in (site_dir / "series").iterdir()) == sorted(f"{i}.json" for i in ids)
    urls = sorted(l["url"] for l in load(site_dir, "layers.json")["layers"])
    assert sorted(f"layers/{p.name}" for p in (site_dir / "layers").iterdir()) == urls
    assert (site_dir / "story.json").read_bytes() == story
    assert (site_dir / "notes.txt").read_text(encoding="utf-8") == "not the exporter's"
    for i in ids:
        assert {s["sensor"] for s in load(site_dir, f"series/{i}.json")["series"]} == {"NISAR L-band"}


def test_large_grids_are_block_averaged_and_kept_small(runs, site, monkeypatch):
    data, site_dir = site
    monkeypatch.setattr(export, "MAX_LAYER_PX", 70)   # 160 px wide -> 3 x 3 blocks, padded to 162 x 120
    monkeypatch.setattr(export, "MAX_PNG_BYTES", 1)   # force the palette fallback
    write_site(site_dir, SITE, [runs[0]])

    assert validate(data) == []
    layer = load(site_dir, "layers.json")["layers"][0]
    img = Image.open(site_dir / layer["url"])
    assert img.size == (54, 40) and img.mode == "P"
    alpha = np.array(img.convert("RGBA"))[..., 3]
    assert (alpha[:, 0] == 0).all() and (alpha[:, 1:] == 255).all()
    expected = [lonlat(X0 + PX * c, Y0 - PX * r) for c, r in ((0, 0), (162, 0), (162, 120), (0, 120))]
    assert np.allclose(layer["coordinates"], expected, atol=2e-6)
