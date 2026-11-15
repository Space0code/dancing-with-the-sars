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
    assert block["before"] == 0.7 and block["after"] == 0.25
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
