"""Tests for sarwatch.s1 (OPERA RTC-S1 reader).

Offline: tiny synthetic GeoTIFFs laid out like the real product (one file per polarization plus a mask, one UTM grid),
read from disk and through a local HTTP server that mimics ASF's redirect chain. Live tests run only on request:
SARWATCH_LIVE=1 for the search (no login), EARTHDATA_TOKEN=<token> for a real window read.
"""
import http.server
import math
import os
import threading
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
pytest.importorskip("requests")
pytest.importorskip("shapely")

from rasterio.transform import from_origin  # noqa: E402
from rasterio.warp import transform as warp_transform, transform_bounds  # noqa: E402

from sarwatch import s1  # noqa: E402

PX = 30.0
EPSG = 32631            # UTM 31N, the zone of the Catalonia pilot
SIZE = 80               # pixels per side of a synthetic burst raster (2.4 km)
BURST = "T999_000001_IW1"
AGROPARC = (1.85, 41.45)
MUHOS = (26.044, 64.843)


def bbox_around(lon, lat, size_m):
    """A lon/lat bbox of about size_m x size_m metres centred on (lon, lat)."""
    dlat = size_m / 2 / 111_320
    dlon = size_m / 2 / (111_320 * math.cos(math.radians(lat)))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


# Global lattice: pixel (row, col) of every synthetic file is counted from this corner, so values can be checked
# against absolute position even when files have different extents.
_cx, _cy = (v[0] for v in warp_transform("EPSG:4326", f"EPSG:{EPSG}", [AGROPARC[0]], [AGROPARC[1]]))
GX0 = math.floor(_cx / PX) * PX - SIZE // 2 * PX
GY0 = math.ceil(_cy / PX) * PX + SIZE // 2 * PX


def pattern(t, row0=0, col0=0, rows=SIZE, cols=SIZE):
    """Linear power that encodes date and absolute position: 0.01 (t + 1) + 1e-4 row + 1e-6 col."""
    r = np.arange(row0, row0 + rows)[:, None]
    c = np.arange(col0, col0 + cols)[None, :]
    return (0.01 * (t + 1) + 1e-4 * r + 1e-6 * c).astype(np.float32)


def write_tif(path, data, dtype, nodata, origin, epsg=EPSG):
    with rasterio.open(path, "w", driver="GTiff", width=data.shape[1], height=data.shape[0], count=1, dtype=dtype,
                       crs=f"EPSG:{epsg}", transform=from_origin(origin[0], origin[1], PX, PX), nodata=nodata,
                       tiled=True, blockxsize=16, blockysize=16, compress="deflate") as ds:
        ds.write(data.astype(dtype), 1)


def make_scene(folder, t, offset=(0, 0), shape=(SIZE, SIZE), shift_m=(0.0, 0.0), epsg=EPSG, edit=None, mask=None):
    """Write VV, VH and mask files for date index t and return the Scene (local paths in urls).

    offset: (row, col) of the file's top-left pixel on the global lattice. shift_m: extra origin shift in metres
    (off-lattice when not a multiple of 30). edit(vv, vh) may change values in place; mask: uint8 array or None.
    """
    day = datetime(2024, 1, 1, 6, 0, tzinfo=timezone.utc) + timedelta(days=12 * t)
    name = f"OPERA_L2_RTC-S1_{BURST.replace('_', '-')}_{day:%Y%m%dT%H%M%SZ}_{day:%Y%m%d}T120000Z_S1A_30_v1.0"
    vv = pattern(t, offset[0], offset[1], *shape)
    vh = vv / 5
    if edit:
        edit(vv, vh)
    m = np.zeros(shape, np.uint8) if mask is None else mask
    origin = (GX0 + offset[1] * PX + shift_m[0], GY0 - offset[0] * PX + shift_m[1])
    urls = {}
    for layer, data, dtype, nodata in (("VV", vv, "float32", float("nan")), ("VH", vh, "float32", float("nan")),
                                       ("mask", m, "uint8", 255)):
        path = os.path.join(folder, f"{name}_{layer}.tif")
        write_tif(path, data, dtype, nodata, origin, epsg)
        urls[layer] = path
    return s1.Scene(name=name, burst_id=BURST, start=day, track=999, direction="DESCENDING", urls=urls,
                    extra={"produced": f"{day:%Y%m%d}T120000Z", "version": "1.0"})


def lattice_bbox(row0, col0, rows, cols, inset=3.0):
    """Lon/lat bbox whose UTM bounds sit just inside the given block of lattice pixels."""
    x = [GX0 + col0 * PX + inset, GX0 + (col0 + cols) * PX - inset]
    y = [GY0 - (row0 + rows) * PX + inset, GY0 - row0 * PX - inset]
    return transform_bounds(f"EPSG:{EPSG}", "EPSG:4326", x[0], y[0], x[1], y[1])


def window_of(transform, shape):
    """(row0, col0) on the global lattice of a returned window."""
    a, b, c, d, e, f = transform
    assert (a, b, d, e) == (PX, 0.0, 0.0, -PX)
    col0, row0 = (c - GX0) / PX, (GY0 - f) / PX
    assert col0 == int(col0) and row0 == int(row0), "window not on the pixel lattice"
    return int(row0), int(col0)


@pytest.fixture
def four_dates(tmp_path):
    return [make_scene(str(tmp_path), t) for t in range(4)]


# ---------------------------------------------------------------- read_stack, local files

def test_window_is_minimal_covers_bbox_and_holds_the_right_pixels(four_dates):
    bbox = lattice_bbox(20, 30, 25, 15)
    stack, dates, transform, epsg = s1.read_stack(four_dates, bbox)

    assert epsg == EPSG
    assert dates == [sc.start.date() for sc in four_dates]
    assert set(stack) == {"VV", "VH"}
    n_t, rows, cols = stack["VV"].shape
    assert n_t == 4 and stack["VH"].shape == stack["VV"].shape
    assert stack["VV"].dtype == np.float32
    row0, col0 = window_of(transform, (rows, cols))
    # covers the bbox projected to UTM, and is minimal: it is not one pixel larger than needed on any side
    xmin, ymin, xmax, ymax = transform_bounds("EPSG:4326", f"EPSG:{EPSG}", *bbox, densify_pts=21)
    wx0, wy1 = GX0 + col0 * PX, GY0 - row0 * PX
    wx1, wy0 = wx0 + cols * PX, wy1 - rows * PX
    assert wx0 <= xmin < wx0 + PX and wx1 - PX < xmax <= wx1
    assert wy0 <= ymin < wy0 + PX and wy1 - PX < ymax <= wy1
    for t in range(4):
        np.testing.assert_allclose(stack["VV"][t], pattern(t, row0, col0, rows, cols), rtol=1e-6)
        np.testing.assert_allclose(stack["VH"][t], pattern(t, row0, col0, rows, cols) / 5, rtol=1e-6)
    assert s1.last_read_stats["dates"] == 4 and s1.last_read_stats["files"] == 12
    assert s1.last_read_stats["shape"] == (rows, cols)
    assert s1.last_read_stats["bytes"] > 0 and s1.last_read_stats["seconds"] >= 0


def test_nodata_nonpositive_and_mask_become_nan_on_that_date_only(tmp_path):
    def holes(vv, vh):
        vv[10, 10] = np.nan  # nodata in one polarization only
        vh[11, 11] = 0.0     # non-positive power is not usable either

    mask = np.zeros((SIZE, SIZE), np.uint8)
    mask[20:24, 20:24] = 1    # shadow
    mask[30:32, 30:32] = 2    # layover
    mask[0:5, :] = 255        # no data (outside the burst footprint)
    scenes = [make_scene(str(tmp_path), 0), make_scene(str(tmp_path), 1, edit=holes, mask=mask),
              make_scene(str(tmp_path), 2)]
    stack, _, transform, _ = s1.read_stack(scenes, lattice_bbox(2, 2, 36, 36))

    row0, col0 = window_of(transform, stack["VV"].shape[1:])
    vv, vh = stack["VV"][1], stack["VH"][1]

    def at(r, c):  # lattice pixel -> window index
        return r - row0, c - col0

    assert np.isnan(vv[at(10, 10)]) and not np.isnan(vh[at(10, 10)])
    assert np.isnan(vh[at(11, 11)]) and not np.isnan(vv[at(11, 11)])
    for pol in (vv, vh):
        assert np.isnan(pol[at(21, 21)]) and np.isnan(pol[at(30, 31)]) and np.isnan(pol[at(2, 15)])
        assert not np.isnan(pol[at(25, 25)]) and not np.isnan(pol[at(6, 15)])
    assert not np.isnan(stack["VV"][[0, 2]]).any() and not np.isnan(stack["VH"][[0, 2]]).any()


def test_bbox_partly_outside_the_burst_is_padded_with_nan(four_dates):
    bbox = lattice_bbox(30, SIZE - 10, 20, 20)  # half of it east of the raster

    stack, _, transform, _ = s1.read_stack(four_dates, bbox)

    row0, col0 = window_of(transform, stack["VV"].shape[1:])
    inside = SIZE - col0
    assert 0 < inside < stack["VV"].shape[2]
    assert np.isnan(stack["VV"][:, :, inside:]).all()
    np.testing.assert_allclose(stack["VV"][2, :, :inside], pattern(2, row0, col0, stack["VV"].shape[1], inside),
                               rtol=1e-6)


def test_bbox_outside_the_burst_raises(four_dates):
    with pytest.raises(ValueError, match="outside"):
        s1.read_stack(four_dates, lattice_bbox(SIZE + 50, SIZE + 50, 10, 10))


def test_same_lattice_with_a_different_extent_still_aligns(tmp_path):
    scenes = [make_scene(str(tmp_path), 0), make_scene(str(tmp_path), 1, offset=(2, 3), shape=(SIZE - 4, SIZE - 6))]
    stack, _, transform, _ = s1.read_stack(scenes, lattice_bbox(20, 20, 10, 10))
    row0, col0 = window_of(transform, stack["VV"].shape[1:])
    for t in range(2):
        np.testing.assert_allclose(stack["VV"][t], pattern(t, row0, col0, *stack["VV"].shape[1:]), rtol=1e-6)


@pytest.mark.parametrize("kwargs", [{"shift_m": (15.0, 0.0)}, {"shift_m": (0.0, 7.5)}, {"epsg": 32630}])
def test_grid_mismatch_raises(tmp_path, kwargs):
    scenes = [make_scene(str(tmp_path), t) for t in range(3)] + [make_scene(str(tmp_path), 3, **kwargs)]
    with pytest.raises(ValueError, match="grid mismatch"):
        s1.read_stack(scenes, lattice_bbox(20, 20, 10, 10))


def test_missing_polarization_and_missing_token_raise(four_dates, monkeypatch):
    del four_dates[1].urls["VH"]
    with pytest.raises(ValueError, match="VH"):
        s1.read_stack(four_dates, lattice_bbox(20, 20, 10, 10))
    four_dates[1].urls["VH"] = "https://datapool.asf.alaska.edu/RTC/OPERA-S1/x_VH.tif"
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="EARTHDATA_TOKEN"):
        s1.read_stack(four_dates, lattice_bbox(20, 20, 10, 10))


def test_reads_only_the_requested_polarizations(four_dates):
    stack, *_ = s1.read_stack(four_dates, lattice_bbox(20, 20, 10, 10), pols=("VH",))
    assert set(stack) == {"VH"}


# ---------------------------------------------------------------- read_stack over HTTP, mimicking ASF

class _FakeAsf(http.server.BaseHTTPRequestHandler):
    """datapool -> 307 -> cumulus (checks the bearer token) -> 303 -> pre-signed 'S3' URL (refuses tokens and HEAD)."""
    root = ""
    token = "good-token"
    log = None

    def log_message(self, *args):
        pass

    def _redirect(self, code, location):
        self.send_response(code)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        self.send_response(403)  # a URL signed for GET refuses HEAD, like S3
        self.end_headers()

    def do_GET(self):
        port = self.server.server_address[1]
        kind, _, name = self.path.lstrip("/").partition("/")
        auth = self.headers.get("Authorization")
        self.log.append((kind, auth))
        if kind == "datapool":
            return self._redirect(307, f"http://127.0.0.1:{port}/cumulus/{name}")
        if kind == "cumulus":
            if auth != f"Bearer {self.token}":
                return self._redirect(302, "https://urs.earthdata.nasa.gov/oauth/authorize?app_type=401")
            return self._redirect(303, f"http://127.0.0.1:{port}/s3/{name}?X-Amz-Expires=3600&X-Amz-Signature=abc")
        if kind == "s3":
            if auth:
                self.send_response(400)  # S3: "Only one auth mechanism allowed"
                self.end_headers()
                return
            with open(os.path.join(self.root, name.split("?")[0]), "rb") as f:
                data = f.read()
            rng = self.headers.get("Range", "")
            if rng.startswith("bytes=") and "," not in rng:
                lo, _, hi = rng[6:].partition("-")
                lo, hi = int(lo), min(int(hi) if hi else len(data) - 1, len(data) - 1)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {lo}-{hi}/{len(data)}")
                body = data[lo:hi + 1]
            else:
                self.send_response(200)
                body = data
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                for i in range(0, len(body), 65536):  # count what really went out: GDAL may hang up early
                    self.wfile.write(body[i:i + 65536])
                    self.server.served += len(body[i:i + 65536])
            except OSError:
                pass
            return
        self.send_response(404)
        self.end_headers()


@pytest.fixture
def fake_asf(tmp_path, monkeypatch):
    handler = type("Handler", (_FakeAsf,), {"root": str(tmp_path), "log": []})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.served = 0
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # one local host plays both ASF (gets the token) and S3 (must not): tell them apart by path
    monkeypatch.setattr(s1, "_token_host", lambda url: not urlparse(url).path.startswith("/s3/"))
    yield server, handler
    server.shutdown()


def _as_remote(scenes, port):
    for sc in scenes:
        sc.urls = {k: f"http://127.0.0.1:{port}/datapool/{os.path.basename(v)}" for k, v in sc.urls.items()}
    return scenes


def test_http_read_follows_redirects_and_keeps_the_token_away_from_s3(tmp_path, fake_asf):
    server, handler = fake_asf
    local = [make_scene(str(tmp_path), t) for t in range(3)]
    bbox = lattice_bbox(20, 30, 12, 12)
    expected, dates, transform, epsg = s1.read_stack(local, bbox)

    remote = _as_remote([make_scene(str(tmp_path), t) for t in range(3)], server.server_address[1])
    stack, rdates, rtransform, repsg = s1.read_stack(remote, bbox, token="good-token", workers=4)

    assert (rdates, rtransform, repsg) == (dates, transform, epsg)
    for pol in ("VV", "VH"):
        np.testing.assert_array_equal(stack[pol], expected[pol])
    assert {auth for kind, auth in handler.log if kind == "s3"} == {None}
    assert all(auth == "Bearer good-token" for kind, auth in handler.log if kind != "s3")
    assert server.served > 0 and s1.last_read_stats["bytes"] > 0


def test_http_read_with_a_refused_token_says_so(tmp_path, fake_asf):
    server, _ = fake_asf
    remote = _as_remote([make_scene(str(tmp_path), t) for t in range(2)], server.server_address[1])
    with pytest.raises(PermissionError, match="refused"):
        s1.read_stack(remote, lattice_bbox(20, 30, 12, 12), token="wrong")


# ---------------------------------------------------------------- pick_burst, thin, search parsing

def _box_wkt(w, s, e, n):
    return f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"


def _scenes(burst, days, footprint, produced="20250101T000000Z", version="1.0", start=date(2024, 1, 1)):
    out = []
    for d in days:
        t = datetime.combine(start + timedelta(days=d), datetime.min.time(), timezone.utc) + timedelta(hours=6)
        out.append(s1.Scene(name=f"{burst}-{d}-{produced}", burst_id=burst, start=t, track=int(burst[1:4]),
                            direction="ASCENDING", urls={}, footprint=footprint,
                            extra={"produced": produced, "version": version}))
    return out


BBOX = (1.0, 41.0, 1.1, 41.1)
COVERS = _box_wkt(0.5, 40.5, 1.5, 41.5)
PARTIAL = _box_wkt(1.05, 40.5, 1.5, 41.5)    # half of BBOX
SLIVER = _box_wkt(1.09, 40.5, 1.5, 41.5)     # a tenth of BBOX


def test_pick_burst_prefers_full_cover_then_most_dates_one_scene_per_date():
    few = _scenes("T001_000001_IW1", range(0, 36, 12), COVERS)
    many = _scenes("T002_000002_IW2", range(0, 60, 12), COVERS)
    newer = _scenes("T002_000002_IW2", [24], COVERS, produced="20250601T000000Z")  # a reprocessed copy
    partial = _scenes("T003_000003_IW3", range(0, 240, 6), PARTIAL)
    shuffled = partial + newer + few + many[::-1]

    picked = s1.pick_burst(shuffled, BBOX)

    assert {sc.burst_id for sc in picked} == {"T002_000002_IW2"}
    assert len(picked) == 5
    assert [sc.start for sc in picked] == sorted(sc.start for sc in picked)
    assert len({sc.start.date() for sc in picked}) == 5
    assert [sc for sc in picked if sc.start.date() == date(2024, 1, 25)][0].extra["produced"] == "20250601T000000Z"


def test_pick_burst_without_full_cover_prefers_the_larger_cover():
    picked = s1.pick_burst(_scenes("T003_000003_IW3", range(0, 24, 12), PARTIAL)
                           + _scenes("T004_000004_IW1", range(0, 240, 6), SLIVER), BBOX)
    assert {sc.burst_id for sc in picked} == {"T003_000003_IW3"}
    assert s1.pick_burst([], BBOX) == []


def test_pick_burst_prefers_newer_version_over_newer_production():
    old = _scenes("T001_000001_IW1", [0], COVERS, produced="20990101T000000Z", version="0.9")
    new = _scenes("T001_000001_IW1", [0], COVERS, produced="20240101T000000Z", version="1.0")
    assert s1.pick_burst(old + new, BBOX)[0].extra["version"] == "1.0"


def test_thin_by_gap_and_by_count():
    series = _scenes("T001_000001_IW1", range(0, 6 * 100, 6), COVERS)  # every 6 days, 100 dates

    by_gap = s1.thin(series, min_gap_days=30)
    gaps = [(b.start - a.start).days for a, b in zip(by_gap, by_gap[1:])]
    assert by_gap[0] is series[0] and min(gaps) >= 30 and max(gaps) < 36

    by_count = s1.thin(series, max_dates=10)
    assert len(by_count) == 10 and by_count[0] is series[0] and by_count[-1] is series[-1]
    spacing = [(b.start - a.start).days for a, b in zip(by_count, by_count[1:])]
    assert max(spacing) - min(spacing) <= 6  # even in time, up to one revisit

    both = s1.thin(series, max_dates=5, min_gap_days=30)
    assert len(both) == 5
    assert s1.thin(series[:3], max_dates=10) == series[:3]
    assert s1.thin(series[::-1]) == series  # always time-sorted


API_ITEM = {  # one real result of the ASF search API (output=jsonlite), trimmed to the fields the reader uses
    "flightDirection": "ASCENDING", "path": 132, "polarization": ["VV", "VH"],
    "granuleName": "OPERA_L2_RTC-S1_T132-281622-IW2_20240611T174720Z_20240614T193701Z_S1A_30_v1.0",
    "startTime": "2024-06-11T17:47:20Z",
    "downloadUrl": "https://datapool.asf.alaska.edu/RTC/OPERA-S1/"
                   "OPERA_L2_RTC-S1_T132-281622-IW2_20240611T174720Z_20240614T193701Z_S1A_30_v1.0_VH.tif",
    "wkt": "POLYGON ((1.76082 41.32491, 2.33993 41.40223, 2.88771 41.47253, 2.85029 41.63853, 2.24594 41.56106, "
           "1.72249 41.49123, 1.76082 41.32491))",
    "opera": {
        "operaBurstID": "T132_281622_IW2", "productVersion": "1.0",
        "additionalUrls": [
            "https://datapool.asf.alaska.edu/RTC/OPERA-S1/"
            "OPERA_L2_RTC-S1_T132-281622-IW2_20240611T174720Z_20240614T193701Z_S1A_30_v1.0.h5",
            "https://datapool.asf.alaska.edu/RTC/OPERA-S1/"
            "OPERA_L2_RTC-S1_T132-281622-IW2_20240611T174720Z_20240614T193701Z_S1A_30_v1.0_VV.tif",
            "https://datapool.asf.alaska.edu/RTC/OPERA-S1/"
            "OPERA_L2_RTC-S1_T132-281622-IW2_20240611T174720Z_20240614T193701Z_S1A_30_v1.0_mask.tif",
        ],
    },
}


def test_scene_from_api_item():
    sc = s1.scene_from_api(API_ITEM)
    assert sc.burst_id == "T132_281622_IW2" and sc.track == 132 and sc.direction == "ASCENDING"
    assert sc.start == datetime(2024, 6, 11, 17, 47, 20, tzinfo=timezone.utc)
    assert set(sc.urls) == {"VV", "VH", "mask"}
    assert sc.urls["mask"].endswith("_v1.0_mask.tif") and sc.urls["VV"].endswith("_v1.0_VV.tif")
    assert sc.extra == {"produced": "20240614T193701Z", "version": "1.0"}
    assert s1.pick_burst([sc], bbox_around(*AGROPARC, 3000)) == [sc]  # its footprint covers Agroparc


class _FakeSearch:
    """Stands in for the search API: answers from a list of items, at most maxResults per query, like the real one."""

    def __init__(self, items):
        self.items, self.queries = items, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params, timeout):
        t0, t1 = (datetime.fromisoformat(params[k].replace("Z", "+00:00")) for k in ("start", "end"))
        self.queries.append((t0, t1))
        hits = [it for it in self.items
                if t0 <= datetime.fromisoformat(it["startTime"].replace("Z", "+00:00")) <= t1]
        response = type("Response", (), {})()
        response.status_code = 200
        response.json = lambda: {"results": hits[:params["maxResults"]]}
        return response


def test_search_asks_year_by_year_splits_full_answers_and_drops_repeats(monkeypatch):
    items = []
    for i, day in enumerate([date(2016, 5, 1), date(2017, 1, 1)] + [date(2020, 3, 1) + timedelta(days=6 * k)
                                                                     for k in range(9)]):
        item = dict(API_ITEM, startTime=f"{day:%Y-%m-%d}T00:00:00Z")
        item["granuleName"] = API_ITEM["granuleName"].replace("20240611T174720Z", f"{day:%Y%m%d}T000000Z")
        items.append(item)
    fake = _FakeSearch(items)
    monkeypatch.setattr(s1, "_session", lambda: fake)
    monkeypatch.setattr(s1, "MAX_RESULTS", 4)

    scenes = s1.search(BBOX, start="2016-01-01", end=date(2021, 1, 1))

    assert len(scenes) == len(items)  # 2017-01-01 sits on a year edge and comes back twice: kept once
    assert [sc.start for sc in scenes] == sorted(sc.start for sc in scenes)
    assert len(fake.queries) > 5  # one per year, plus splits of 2020, which holds more than MAX_RESULTS


# ---------------------------------------------------------------- live (opt-in)

def _summary(label, scenes, picked):
    bursts = Counter(sc.burst_id for sc in scenes)
    dates_per_burst = {b: len(s1._one_per_date([sc for sc in scenes if sc.burst_id == b])) for b in bursts}
    per_year = Counter(sc.start.year for sc in picked)
    first = picked[0]
    print(f"\n{label}: {len(scenes)} products, {len(bursts)} bursts, distinct dates per burst {dates_per_burst}")
    print(f"  picked {first.burst_id} (track {first.track} {first.direction}): {len(picked)} dates, "
          f"{picked[0].start.date()} -> {picked[-1].start.date()}, per year {dict(sorted(per_year.items()))}")


@pytest.mark.skipif(os.environ.get("SARWATCH_LIVE") != "1", reason="live ASF search: set SARWATCH_LIVE=1")
@pytest.mark.parametrize("label, point", [("Muhos", MUHOS), ("Agroparc", AGROPARC)])
def test_live_search_and_pick(label, point):
    bbox = bbox_around(*point, 3000)
    scenes = s1.search(bbox)
    assert scenes and all(sc.urls.get("VV") and sc.urls.get("VH") and sc.urls.get("mask") for sc in scenes)

    picked = s1.pick_burst(scenes, bbox)

    assert len({sc.burst_id for sc in picked}) == 1
    assert len({sc.start.date() for sc in picked}) == len(picked) >= 50
    assert [sc.start for sc in picked] == sorted(sc.start for sc in picked)
    from shapely import wkt
    from shapely.geometry import box
    assert wkt.loads(picked[0].footprint).covers(box(*bbox))
    _summary(label, scenes, picked)


@pytest.mark.skipif(not os.environ.get("EARTHDATA_TOKEN"), reason="live read: set EARTHDATA_TOKEN")
def test_live_read_agroparc_3km_3_dates():
    bbox = bbox_around(*AGROPARC, 3000)
    picked = s1.pick_burst(s1.search(bbox, start="2025-01-01", end="2025-04-01"), bbox)
    scenes = s1.thin(picked, max_dates=3)

    stack, dates, transform, epsg = s1.read_stack(scenes, bbox)

    assert epsg == 32631 and len(dates) == 3
    assert transform[0] == 30.0 and transform[4] == -30.0
    for pol in ("VV", "VH"):
        assert stack[pol].shape[0] == 3 and 95 <= stack[pol].shape[1] <= 120 and 95 <= stack[pol].shape[2] <= 120
        assert np.isfinite(stack[pol]).mean() > 0.8
    vv, vh = np.nanmedian(stack["VV"]), np.nanmedian(stack["VH"])
    assert 1e-3 < vv < 1 and 1e-4 < vh < vv  # roughly -30..0 dB, cross-pol weaker than co-pol
    print(f"\nlive read: {scenes[0].burst_id}, dates {dates}, shape {stack['VV'].shape}, "
          f"VV {10 * np.log10(vv):.1f} dB, VH {10 * np.log10(vh):.1f} dB, stats {s1.last_read_stats}")
