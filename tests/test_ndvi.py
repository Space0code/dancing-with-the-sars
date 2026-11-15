"""NDVI, snow and water bookkeeping of sarwatch.ndvi (no network)."""
import json
from datetime import date, datetime

import numpy as np

from sarwatch import distalert, ndvi

CLEAR, CLOUD, SNOW = 0, 1 << 1, 1 << 4


def test_ndvi_of_uses_both_bands_and_marks_no_data():
    red = np.array([1000, 3000, -9999], np.int16)
    nir = np.array([5000, 3000, 4000], np.int16)
    out = ndvi.ndvi_of(red, nir)
    assert np.isclose(out[0], 4000 / 6000) and out[1] == 0 and np.isnan(out[2])


def test_ndvi_of_ignores_non_positive_reflectance():
    red = np.array([-50, 0, 1000, 500], np.int16)
    nir = np.array([800, 800, -20, 0], np.int16)
    assert np.isnan(ndvi.ndvi_of(red, nir)).all()


def test_measure_excludes_cloud_and_snow_from_ndvi():
    mask = np.ones((2, 5), bool)
    fm = np.array([[CLEAR] * 5, [CLEAR, CLEAR, CLOUD, SNOW, SNOW]], np.uint8)
    nd = np.full((2, 5), 0.5, np.float32)
    nd[1, 3:] = -0.1  # snow pixels must not drag the mean down
    m = ndvi.measure(mask, fm, nd)
    assert np.isclose(m["clear"], 0.9) and np.isclose(m["ndvi"], 0.5)
    assert np.isclose(m["snow"], 2 / 9) and m["water"] == 0


def test_measure_needs_60_percent_usable_pixels_for_ndvi():
    mask = np.ones((1, 10), bool)
    fm = np.array([[SNOW] * 5 + [CLEAR] * 5], np.uint8)
    assert ndvi.measure(mask, fm, np.full((1, 10), 0.5, np.float32))["ndvi"] is None


def _rows():
    d = date.fromisoformat
    return [{"date": d("2025-06-01"), "clear": 1, "snow": 0.0, "water": 0.0, "ndvi": 0.8},
            {"date": d("2025-07-01"), "clear": 1, "snow": 0.0, "water": 0.0, "ndvi": 0.6},
            {"date": d("2026-01-10"), "clear": 1, "snow": 0.9, "water": 0.0, "ndvi": None},
            {"date": d("2026-01-20"), "clear": 0.3, "snow": 0.0, "water": 0.0, "ndvi": 0.1},
            {"date": d("2026-02-10"), "clear": 1, "snow": 0.0, "water": 0.4, "ndvi": 0.2},
            {"date": d("2026-03-10"), "clear": 1, "snow": 0.0, "water": 0.2, "ndvi": 0.3}]


def test_build_blocks_before_after_snow_water():
    change = {"first_date": "2026-01-15", "last_date": "2026-01-15"}
    block, surface = ndvi.build_blocks(change, _rows())
    assert block["dates"] == ["2025-06-01", "2025-07-01", "2026-02-10", "2026-03-10"]
    assert block["before"] is None and block["after"] is None   # June / July against February / March: not comparable
    assert surface["snow_share"] == 0.9 and surface["water_share"] == 0.3
    assert surface["dates_checked"] == ["2026-01-10", "2026-02-10", "2026-03-10"]


def test_build_blocks_without_usable_dates():
    block, surface = ndvi.build_blocks({"first_date": "2026-01-15", "last_date": "2026-01-15"}, [])
    assert block is None and surface == {"snow_share": None, "water_share": None, "dates_checked": []}


def _granule(day, cloud):
    return distalert.Granule(name=f"g{day}", tile="T", start=datetime.fromisoformat(day + "T10:00:00"),
                             sensor="S30", urls={}, extra={"cloud": cloud})


def test_select_granules_caps_spreads_and_skips_cloudy():
    gs = [_granule(f"2025-{m:02d}-{d:02d}", 10 + d) for m in range(1, 13) for d in (3, 13, 23)]
    gs.append(_granule("2025-06-04", 95))
    chosen = ndvi.select_granules(gs, [date(2025, 12, 1)], 6)
    assert len(chosen) == 6 and all(g.extra["cloud"] <= 60 for g in chosen)
    assert any(abs((g.start.date() - date(2025, 12, 1)).days) <= 16 for g in chosen)


def test_write_blocks_keeps_the_rest_and_replaces_on_rerun(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"series": [{"name": "a"}], "events": []}, indent=1), encoding="utf-8")
    surface = {"snow_share": None, "water_share": None, "dates_checked": []}
    ndvi.write_blocks(path, {"sensor": "x", "dates": [], "values": [], "before": None, "after": None}, surface)
    ndvi.write_blocks(path, None, surface)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert list(doc) == ["series", "events", "surface"] and doc["series"] == [{"name": "a"}]


def _d(s):
    return date.fromisoformat(s)


def test_same_season_keeps_only_months_near_the_other_side():
    dates = ["2025-06-05", "2025-06-25", "2025-10-01", "2026-06-10", "2026-07-02", "2026-12-01"]
    values = [0.8, 0.7, 0.2, 0.4, 0.5, 0.9]
    r = ndvi.same_season(dates, values, _d("2026-03-01"), _d("2026-03-05"))
    assert r["state"] == "ok"
    assert (r["n_before"], r["n_after"]) == (2, 2)   # October has no partner in June / July, December none either
    assert r["months"] == [6, 7]
    assert r["before"] == 0.75 and abs(r["after"] - 0.45) < 1e-9


def test_same_season_matches_across_the_year_boundary():
    dates = ["2025-12-10", "2025-12-28", "2026-01-30", "2026-02-12", "2026-03-20"]
    values = [0.5, 0.6, 0.3, 0.2, 0.9]
    # before = December (x2); after = January and February: January is next to December, February is not
    r = ndvi.same_season(dates, values, _d("2026-01-05"), _d("2026-01-10"))
    assert r["state"] == "few" and (r["n_before"], r["n_after"]) == (2, 1)
    assert r["before"] is None and r["after"] is None
    assert ndvi.season_summary(dates, values, _d("2026-01-05"), _d("2026-01-10")) == (None, None)


def test_same_season_needs_two_dates_per_side_and_a_date_on_each_side():
    assert ndvi.same_season(["2025-06-01"], [0.5], _d("2026-06-01"), _d("2026-06-02"))["state"] == "nodata"
    assert ndvi.same_season([], [], _d("2026-06-01"), _d("2026-06-02"))["state"] == "nodata"
    assert ndvi.same_season(None, None, _d("2026-06-01"), _d("2026-06-02"))["state"] == "nodata"
    r = ndvi.same_season(["2025-06-01", "2026-07-01"], [0.5, 0.4], _d("2026-06-01"), _d("2026-06-02"))
    assert r["state"] == "few" and r["before"] is None


def test_season_summary_rounds_and_ignores_dates_outside_the_year():
    dates = ["2024-06-01", "2025-06-01", "2025-06-20", "2026-06-10", "2026-06-20", "2027-06-15"]
    values = [0.1, 0.801, 0.8, 0.5, 0.52, 0.0]
    assert ndvi.season_summary(dates, values, _d("2026-06-01"), _d("2026-06-05")) == (0.8, 0.51)


def test_recompute_summary_touches_only_before_and_after(tmp_path):
    site = tmp_path / "app" / "data" / "x"
    (site / "series").mkdir(parents=True)
    (site / "changes.geojson").write_text(json.dumps({"features": [
        {"properties": {"id": "x-1", "first_date": "2026-06-01", "last_date": "2026-06-05"}}]}), encoding="utf-8")
    block = {"sensor": "HLS", "dates": ["2025-06-01", "2025-06-20", "2026-06-10", "2026-06-20"],
             "values": [0.8, 0.7, 0.5, 0.4], "before": 0.1, "after": 0.1}
    path = site / "series" / "x-1.json"
    path.write_bytes(json.dumps({"signal": [1], "ndvi": block}, indent=1).replace("\n", "\r\n").encode())
    assert ndvi.recompute_summary("x", root=tmp_path) == 1
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["ndvi"]["before"] == 0.75 and data["ndvi"]["after"] == 0.45
    assert data["ndvi"]["dates"] == block["dates"] and data["ndvi"]["values"] == block["values"]
    assert b"\r\n" in path.read_bytes()
    assert ndvi.recompute_summary("x", root=tmp_path) == 1   # a second run changes nothing
