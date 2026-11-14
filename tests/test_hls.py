"""HLS colour windows: parsing, the Fmask rule and local-file reads offline; one live read behind SARWATCH_LIVE=1."""
import os
from datetime import date, datetime, timezone

import numpy as np
import pytest

from sarwatch import distalert, hls

BBOX = (26.02, 64.795, 26.20, 64.875)


def _umm(name="HLS.S30.T35WMM.2026182T100549.v2.0", product="HLSS30"):
    base = f"https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/{product}.020/{name}/{name}"
    bands = ["B02", "B03", "B04", "B8A", "Fmask"]
    return {"umm": {"GranuleUR": name,
                    "TemporalExtent": {"RangeDateTime": {"BeginningDateTime": "2026-07-01T10:05:49.000Z"}},
                    "RelatedUrls": [{"URL": f"{base}.{b}.tif", "Type": "GET DATA"} for b in bands]
                    + [{"URL": f"{base}.jpg", "Type": "GET DATA"}, {"URL": "https://x/browse.png", "Type": "GET RELATED VISUALIZATION"}]}}


def test_granule_from_umm():
    g = hls.granule_from_umm(_umm())
    assert g.tile == "35WMM" and g.sensor == "S30"
    assert g.start == datetime(2026, 7, 1, 10, 5, 49, tzinfo=timezone.utc)
    assert set(g.urls) == {"B02", "B03", "B04", "B8A", "Fmask"}
    assert g.urls["B04"].endswith("v2.0.B04.tif")


def test_fmask_bits():
    fm = np.array([0, 1, 2, 4, 8, 16, 32, 64 + 128, 255], np.uint8)
    #               clear, cirrus only, cloud, adjacent, shadow, snow, water, aerosol only, no data
    assert hls.clear_mask(fm).tolist() == [True, True, False, False, False, False, True, True, False]
    assert hls.clear_fraction(fm) == pytest.approx(4 / 9)
    assert hls.clear_fraction(np.zeros((0, 0), np.uint8)) == 0.0


def _local_granule(tmp_path, fmask_value):
    import rasterio
    from rasterio.transform import from_origin

    urls = {}
    for band, arr in {"B02": 500, "B03": 1000, "B04": 2000, "Fmask": fmask_value}.items():
        path = tmp_path / f"{fmask_value}_{band}.tif"
        data = np.full((100, 60), arr, np.uint8 if band == "Fmask" else np.int16)
        if band != "Fmask":
            data[0, 0] = hls.NODATA
        with rasterio.open(path, "w", driver="GTiff", height=100, width=60, count=1, dtype=data.dtype,
                           crs="EPSG:32635", transform=from_origin(453000, 7195000, 30, 30)) as ds:
            ds.write(data, 1)
        urls[band] = str(path)
    return distalert.Granule(name=f"g{fmask_value}", tile="35WMM", start=datetime(2026, 7, 1, tzinfo=timezone.utc),
                             sensor="S30", urls=urls)


def test_read_rgb_and_clear_selection_from_local_files(tmp_path):
    clear, cloudy = _local_granule(tmp_path, 0), _local_granule(tmp_path, 2)
    bbox = (26.021, 64.86, 26.03, 64.87)
    rgb, grid = hls.read_rgb(clear, bbox)
    assert rgb.shape[2] == 3 and grid["epsg"] == 32635
    assert np.nanmax(rgb[..., 0]) == pytest.approx(0.2)    # B04 is red
    assert np.nanmax(rgb[..., 2]) == pytest.approx(0.05)   # B02 is blue
    kept = hls.clear_granules([clear, cloudy], bbox, 0.9)
    assert [g.name for g, _ in kept] == ["g0"]


@pytest.mark.skipif(os.environ.get("SARWATCH_LIVE") != "1", reason="live NASA access; set SARWATCH_LIVE=1")
def test_live_muhos_window():
    gs = hls.search(BBOX, date(2025, 7, 10), date(2025, 7, 15))
    gs = [g for g in gs if g.tile == "35WMM"]
    assert gs
    best = max(gs, key=lambda g: hls.clear_fraction(hls.read_fmask(g, BBOX)[0]))
    rgb, grid = hls.read_rgb(best, BBOX)
    assert rgb.shape[:2] == (grid["rows"], grid["cols"]) and np.isfinite(rgb).mean() > 0.9
    assert 0.0 < np.nanmedian(rgb) < 0.5
