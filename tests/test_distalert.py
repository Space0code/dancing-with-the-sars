"""Tests for sarwatch.distalert (OPERA DIST-ALERT-HLS reader).

Offline: tiny synthetic GeoTIFFs laid out like the real product (one file per layer on one UTM tile grid), read from
disk and through a local HTTP server that mimics LP DAAC (bearer token -> 303 -> signed CloudFront URL); a recorded
CMR answer (tests/fixtures/distalert/cmr_muhos.json, trimmed). Live test only on request: SARWATCH_LIVE=1 plus an
Earthdata token ($EARTHDATA_TOKEN or the repo's .env).
"""
import http.server
import json
import math
import os
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
pytest.importorskip("requests")
pytest.importorskip("shapely")

from rasterio.transform import from_origin  # noqa: E402
from rasterio.warp import transform as warp_transform, transform_bounds  # noqa: E402

from sarwatch import distalert as da  # noqa: E402
from sarwatch import s1  # noqa: E402

PX = 30.0
EPSG = 32635             # UTM 35N: the zone of Muhos
SIZE = 96                # pixels per side of a synthetic tile (2.9 km)
MUHOS = (26.044, 64.843)
FIXTURE = Path(__file__).parent / "fixtures" / "distalert" / "cmr_muhos.json"
NAME = "OPERA_L3_DIST-ALERT-HLS_T35WMM_20261023T100041Z_20261025T065842Z_S2A_30_v1"

_cx, _cy = (v[0] for v in warp_transform("EPSG:4326", f"EPSG:{EPSG}", [MUHOS[0]], [MUHOS[1]]))
GX0 = math.floor(_cx / PX) * PX - SIZE // 2 * PX   # top-left corner of the synthetic tile
GY0 = math.ceil(_cy / PX) * PX + SIZE // 2 * PX


def status_pattern(rows=SIZE, cols=SIZE):
    """Status 0..8 cycling with absolute position, so a window's values tell where it was cut."""
    r = np.arange(rows)[:, None]
    c = np.arange(cols)[None, :]
    return ((r * 7 + c) % 9).astype(np.uint8)


def date_pattern(status):
    """Day numbers: 0 where status 0, else 1900 + 10 * status + (row % 5)."""
    rows = np.arange(status.shape[0])[:, None] % 5
    return np.where(status > 0, 1900 + 10 * status.astype(np.int16) + rows, 0).astype(np.int16)


def write_tif(path, data, dtype, nodata):
    with rasterio.open(path, "w", driver="GTiff", width=data.shape[1], height=data.shape[0], count=1, dtype=dtype,
                       crs=f"EPSG:{EPSG}", transform=from_origin(GX0, GY0, PX, PX), nodata=nodata,
                       tiled=True, blockxsize=32, blockysize=32, compress="deflate") as ds:
        ds.write(data.astype(dtype), 1)


def make_granule(folder, status=None, days=None, name=NAME, start=datetime(2026, 10, 23, 10, tzinfo=timezone.utc)):
    status = status_pattern() if status is None else status
    days = date_pattern(status) if days is None else days
    urls = {}
    for layer, data, dtype, nodata in ((da.STATUS, status, "uint8", 255), (da.DATE, days, "int16", -1),
                                       ("VEG-ANOM-MAX", np.minimum(status * 10, 100), "uint8", 255)):
        path = os.path.join(folder, f"{name}_{layer}.tif")
        write_tif(path, data, dtype, nodata)
        urls[layer] = path
    return da.Granule(name=name, tile="35WMM", start=start, sensor="S2A", urls=urls,
                      extra={"produced": "20261025T065842Z", "epsg": EPSG})


def lattice_bbox(row0, col0, rows, cols, inset=3.0):
    """Lon/lat bbox whose UTM bounds sit just inside the given block of tile pixels."""
    x = [GX0 + col0 * PX + inset, GX0 + (col0 + cols) * PX - inset]
    y = [GY0 - (row0 + rows) * PX + inset, GY0 - row0 * PX - inset]
    return transform_bounds(f"EPSG:{EPSG}", "EPSG:4326", x[0], y[0], x[1], y[1])


def window_of(alerts):
    a, b, c, d, e, f = alerts.transform
    assert (a, b, d, e) == (PX, 0.0, 0.0, -PX)
    col0, row0 = (c - GX0) / PX, (GY0 - f) / PX
    assert col0 == int(col0) and row0 == int(row0), "window not on the tile's pixel lattice"
    return int(row0), int(col0)


# ---------------------------------------------------------------- day numbers

def test_days_to_dates_counts_from_2020_12_31():
    out = da.days_to_dates(np.array([[1, 2122], [0, -1]], dtype=np.int16))
    assert out.dtype == np.dtype("datetime64[D]")
    assert out[0, 0] == np.datetime64("2021-01-01") and out[0, 1] == np.datetime64("2026-10-23")
    assert np.isnat(out[1]).all()


# ---------------------------------------------------------------- read_window, local files

def test_read_window_holds_the_right_pixels_and_grid(tmp_path):
    g = make_granule(str(tmp_path))
    bbox = lattice_bbox(20, 30, 25, 15)

    alerts = da.read_window(g, bbox, layers=(da.STATUS, da.DATE, "VEG-ANOM-MAX"))

    assert alerts.epsg == EPSG and alerts.granule == NAME and alerts.acquired == date(2026, 10, 23)
    rows, cols = alerts.status.shape
    row0, col0 = window_of(alerts)
    xmin, ymin, xmax, ymax = transform_bounds("EPSG:4326", f"EPSG:{EPSG}", *bbox, densify_pts=21)
    wx0, wy1 = GX0 + col0 * PX, GY0 - row0 * PX  # covers the bbox and is minimal
    assert wx0 <= xmin < wx0 + PX and wx0 + (cols - 1) * PX < xmax <= wx0 + cols * PX
    assert wy1 - rows * PX <= ymin < wy1 - (rows - 1) * PX and wy1 - PX < ymax <= wy1
    full = status_pattern()
    expected = full[row0:row0 + rows, col0:col0 + cols]
    np.testing.assert_array_equal(alerts.status, expected)
    np.testing.assert_array_equal(alerts.first_date, da.days_to_dates(date_pattern(full)[row0:row0 + rows,
                                                                                     col0:col0 + cols]))
    assert np.isnat(alerts.first_date[expected == 0]).all() and not np.isnat(alerts.first_date[expected > 0]).any()
    assert set(alerts.layers) == {da.STATUS, da.DATE, "VEG-ANOM-MAX"}
    assert alerts.pixel_ha == pytest.approx(0.09)
    assert alerts.cost["files"] == 3 and alerts.cost["bytes"] > 0 and alerts.cost["seconds"] >= 0


def test_window_partly_outside_the_tile_is_nodata(tmp_path):
    g = make_granule(str(tmp_path))
    alerts = da.read_window(g, lattice_bbox(40, SIZE - 10, 20, 20))
    _, col0 = window_of(alerts)
    inside = SIZE - col0
    assert 0 < inside < alerts.status.shape[1]
    assert (alerts.status[:, inside:] == da.STATUS_NODATA).all() and np.isnat(alerts.first_date[:, inside:]).all()
    assert (alerts.status[:, :inside] != da.STATUS_NODATA).all()


def test_bbox_outside_the_tile_missing_layer_and_missing_token_raise(tmp_path, monkeypatch):
    g = make_granule(str(tmp_path))
    with pytest.raises(ValueError, match="outside"):
        da.read_window(g, lattice_bbox(SIZE + 50, SIZE + 50, 10, 10))
    with pytest.raises(ValueError, match="VEG-DIST-CONF"):
        da.read_window(g, lattice_bbox(10, 10, 10, 10), layers=("VEG-DIST-CONF",))
    g.urls[da.DATE] = "https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/x_VEG-DIST-DATE.tif"
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    monkeypatch.setattr("sarwatch.pipeline.load_token", lambda root=None: None)
    with pytest.raises(RuntimeError, match="EARTHDATA_TOKEN"):
        da.read_window(g, lattice_bbox(10, 10, 10, 10))


# ---------------------------------------------------------------- combine, areas

def _alerts(status, days, acquired):
    status = np.asarray(status, dtype=np.uint8)
    return da.Alerts(status=status, first_date=da.days_to_dates(np.asarray(days, dtype=np.int16)),
                     transform=(PX, 0.0, GX0, 0.0, -PX, GY0), epsg=EPSG, granule=f"g{acquired}",
                     acquired=acquired)


APR, JUN, SEP = 1945, 2006, 2099  # day numbers: 2026-04-29, 2026-06-29, 2026-09-30 (from 2020-12-31)


def test_combine_keeps_the_earliest_confirmed_date_and_the_newest_open_alerts():
    # pixels: 0 confirmed in April, finished, then overwritten by a new alert in September
    #         1 a first detection in April that was dropped
    #         2 provisional only in the newest snapshot
    #         3 confirmed in June and still ongoing
    #         4 no alert ever
    apr = _alerts([[3, 1, 0, 0, 0]], [[APR, APR, 0, 0, 0]], date(2026, 4, 30))
    jun = _alerts([[7, 0, 0, 6, 0]], [[APR, 0, 0, JUN, 0]], date(2026, 6, 30))
    sep = _alerts([[1, 0, 5, 6, 0]], [[SEP, 0, SEP, JUN, 0]], date(2026, 9, 30))

    out = da.combine([sep, apr, jun])  # any order

    assert out.acquired == date(2026, 9, 30) and out.granule.startswith("combined:")
    np.testing.assert_array_equal(out.status, [[3, 0, 5, 6, 0]])
    assert out.first_date[0, 0] == np.datetime64("2026-04-29") and out.first_date[0, 3] == np.datetime64("2026-06-29")
    assert out.first_date[0, 2] == np.datetime64("2026-09-30") and np.isnat(out.first_date[0, [1, 4]]).all()
    assert sep.status[0, 0] == 1  # the inputs are not changed

    by = da.hectares_by_month(out)
    assert list(by) == ["2026-04", "2026-06", "2026-09"]
    assert by["2026-04"] == {"confirmed": pytest.approx(0.09), "provisional": 0.0, "first": 0.0}
    assert by["2026-09"] == {"confirmed": 0.0, "provisional": pytest.approx(0.09), "first": 0.0}
    assert list(da.hectares_by_month(out, strong_only=True)) == ["2026-06", "2026-09"]  # 6 and 5 are >= 50%


def test_combine_refuses_mixed_grids_and_empty_input():
    a = _alerts([[3]], [[APR]], date(2026, 4, 30))
    b = _alerts([[3, 0]], [[APR, 0]], date(2026, 5, 30))
    with pytest.raises(ValueError, match="grid mismatch"):
        da.combine([a, b])
    with pytest.raises(ValueError, match="no snapshots"):
        da.combine([])


def test_circle_mask_and_hectares_inside_it():
    status = np.full((SIZE, SIZE), 6, np.uint8)
    alerts = _alerts(status, np.full((SIZE, SIZE), JUN), date(2026, 7, 1))
    lon, lat = (v[0] for v in warp_transform(f"EPSG:{EPSG}", "EPSG:4326", [GX0 + 48 * PX], [GY0 - 48 * PX]))

    circle = da.circle_mask(alerts, lon, lat, 600)

    assert circle[48, 48] and circle[48, 28] and not circle[48, 27] and not circle[0, 0]  # 20 px = 600 m
    expected = math.pi * 600 ** 2 / 10_000
    assert circle.sum() * 0.09 == pytest.approx(expected, rel=0.03)
    by = da.hectares_by_month(alerts, region=circle)
    assert by == {"2026-06": {"confirmed": pytest.approx(circle.sum() * 0.09), "provisional": 0.0, "first": 0.0}}


# ---------------------------------------------------------------- search parsing, tile and granule choice

def test_granule_from_a_recorded_cmr_item():
    item = json.loads(FIXTURE.read_text())["items"][0]
    g = da.granule_from_umm(item)
    assert g.name == NAME and g.tile == "35WMM" and g.sensor == "S2A"
    assert g.start == datetime(2026, 10, 23, 10, 2, 43, 794750, tzinfo=timezone.utc)
    assert set(g.urls) == {da.STATUS, da.DATE}  # https data links only: no s3://, no browse PNG
    assert g.urls[da.STATUS].startswith("https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/")
    assert g.extra == {"produced": "20261025T065842Z", "epsg": 32635, "coverage": 99, "cloud": 68}
    from shapely import wkt
    from shapely.geometry import Point
    assert wkt.loads(g.footprint).contains(Point(*MUHOS))


class _FakeCmr:
    """Stands in for CMR: serves the recorded items PAGE_SIZE at a time, with a CMR-Search-After cursor."""

    def __init__(self, items):
        self.items, self.calls = items, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params, headers, timeout):
        self.calls.append((params, dict(headers)))
        start = int(headers.get("CMR-Search-After", 0))
        page = self.items[start:start + params["page_size"]]
        r = type("Response", (), {})()
        r.status_code = 200
        r.json = lambda: {"items": page}
        r.headers = {"CMR-Search-After": str(start + len(page))} if page else {}
        return r


def test_search_pages_through_cmr_and_sorts(monkeypatch):
    items = json.loads(FIXTURE.read_text())["items"]
    fake = _FakeCmr(items + items[:1])  # the last page repeats an item: kept once
    monkeypatch.setattr(s1, "_session", lambda: fake)
    monkeypatch.setattr(da, "PAGE_SIZE", 2)

    granules = da.search((25.94, 64.80, 26.15, 64.89), "2026-10-01", date(2026, 11, 1))

    assert len(granules) == 3 and [g.start for g in granules] == sorted(g.start for g in granules)
    assert {g.tile for g in granules} == {"35WMM", "35WMN"}
    params = fake.calls[0][0]
    assert params["short_name"] == da.ALERT and params["bounding_box"] == "25.94,64.8,26.15,64.89"
    assert params["temporal"] == "2026-10-01T00:00:00Z,2026-11-01T00:00:00Z"
    assert len(fake.calls) == 3 and fake.calls[1][1] == {"CMR-Search-After": "2"}  # pages of 2, 2, 0


def _g(tile, day, produced="20260101T000000Z", footprint="POLYGON ((0 0,2 0,2 2,0 2,0 0))"):
    return da.Granule(name=f"{tile}-{day}-{produced}", tile=tile,
                      start=datetime(2026, 1, 1, 10, tzinfo=timezone.utc) + timedelta(days=day), sensor="S2A",
                      urls={}, footprint=footprint, extra={"produced": produced})


def test_pick_tile_latest_and_month_ends():
    bbox = (0.5, 0.5, 1.5, 1.5)
    half = "POLYGON ((1 0,2 0,2 2,1 2,1 0))"
    granules = [_g("AAA", d, footprint=half) for d in range(0, 200, 3)] + [_g("BBB", d) for d in range(0, 200, 10)]
    assert da.pick_tile(granules, bbox) == "BBB"  # covers all of bbox, though with fewer granules
    assert da.pick_tile([], bbox) == ""

    newest = _g("BBB", 190, produced="20260801T000000Z")  # a reprocessed copy of the last scene
    granules.append(newest)
    assert da.latest(granules, "BBB") is newest
    assert da.latest(granules, "BBB", before=datetime(2026, 2, 1, tzinfo=timezone.utc)).start.date() == \
        date(2026, 1, 31)
    assert da.latest(granules, "CCC") is None

    ends = da.month_ends(granules, "BBB")
    assert [g.start.month for g in ends] == [1, 2, 3, 4, 5, 6, 7]
    assert ends[-1] is newest and all(g.tile == "BBB" for g in ends)
    assert ends[0].start.date() == date(2026, 1, 31)


# ---------------------------------------------------------------- read_window over HTTP, mimicking LP DAAC

class _FakeLpDaac(http.server.BaseHTTPRequestHandler):
    """/lpdaac/<file> checks the bearer token -> 303 -> /cdn/<file>?Signature=... (refuses any Authorization)."""
    root = ""
    log = None

    def log_message(self, *args):
        pass

    def _send(self, code, body=b"", headers=()):
        self.send_response(code)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        port = self.server.server_address[1]
        kind, _, name = self.path.lstrip("/").partition("/")
        auth = self.headers.get("Authorization")
        self.log.append((kind, auth))
        if kind == "lpdaac":
            if auth == "Bearer good-token":
                return self._send(303, headers=[("Location", f"http://127.0.0.1:{port}/cdn/{name}?Signature=x")])
            if auth is None:
                return self._send(302, headers=[("Location", "https://urs.earthdata.nasa.gov/oauth/authorize")])
            body = json.dumps({"error": "invalid_token", "error_description": "Token is not valid"}).encode()
            return self._send(401, body, [("Content-Type", "application/json")])
        if kind == "cdn":
            if auth:
                return self._send(400, b"too many auth mechanisms")
            data = open(os.path.join(self.root, name.split("?")[0]), "rb").read()
            rng = self.headers.get("Range", "")
            if rng.startswith("bytes=") and "," not in rng:
                lo, _, hi = rng[6:].partition("-")
                lo, hi = int(lo), min(int(hi) if hi else len(data) - 1, len(data) - 1)
                return self._send(206, data[lo:hi + 1], [("Content-Range", f"bytes {lo}-{hi}/{len(data)}")])
            return self._send(200, data)
        self._send(404)


@pytest.fixture
def fake_lpdaac(tmp_path, monkeypatch):
    handler = type("Handler", (_FakeLpDaac,), {"root": str(tmp_path), "log": []})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(s1, "_token_host", lambda url: urlparse(url).path.startswith("/lpdaac/"))
    yield server, handler
    server.shutdown()


def test_http_read_keeps_the_token_away_from_the_signed_url(tmp_path, fake_lpdaac):
    server, handler = fake_lpdaac
    g = make_granule(str(tmp_path))
    bbox = lattice_bbox(20, 30, 12, 12)
    expected = da.read_window(g, bbox)
    g.urls = {k: f"http://127.0.0.1:{server.server_address[1]}/lpdaac/{os.path.basename(v)}"
              for k, v in g.urls.items()}

    got = da.read_window(g, bbox, token="good-token")

    np.testing.assert_array_equal(got.status, expected.status)
    np.testing.assert_array_equal(got.first_date, expected.first_date)
    assert got.transform == expected.transform and got.epsg == expected.epsg
    assert {auth for kind, auth in handler.log if kind == "cdn"} == {None}
    assert {auth for kind, auth in handler.log if kind == "lpdaac"} == {"Bearer good-token"}


def test_http_read_with_a_refused_token_says_so(tmp_path, fake_lpdaac):
    server, _ = fake_lpdaac
    g = make_granule(str(tmp_path))
    g.urls = {k: f"http://127.0.0.1:{server.server_address[1]}/lpdaac/{os.path.basename(v)}"
              for k, v in g.urls.items()}
    with pytest.raises(PermissionError) as err:
        da.read_window(g, lattice_bbox(20, 30, 12, 12), token="expired-token")
    assert "Token is not valid" in str(err.value) and "expired-token" not in str(err.value)


# ---------------------------------------------------------------- live (opt-in)

def _live_token():
    from sarwatch.pipeline import load_token
    return load_token()


@pytest.mark.skipif(os.environ.get("SARWATCH_LIVE") != "1", reason="live CMR + LP DAAC: set SARWATCH_LIVE=1")
def test_live_muhos_latest_alert_state():
    if not _live_token():
        pytest.skip("live read needs an Earthdata token ($EARTHDATA_TOKEN or the repo's .env)")
    bbox = (25.94, 64.80, 26.15, 64.89)  # the Muhos site window
    granules = da.search(bbox, "2026-10-01", "2026-11-01")
    tile = da.pick_tile(granules, bbox)
    g = da.latest(granules, tile)

    alerts = da.read_window(g, bbox)

    assert tile == "35WMM" and alerts.epsg == 32635
    assert alerts.transform[0] == 30.0 and alerts.transform[4] == -30.0
    assert 330 <= alerts.status.shape[0] <= 350 and 330 <= alerts.status.shape[1] <= 350
    assert set(np.unique(alerts.status)) <= set(range(9))
    dated = alerts.first_date[~np.isnat(alerts.first_date)]
    assert np.isin(alerts.status, da.CONFIRMED).sum() * alerts.pixel_ha > 100  # the clearing is in the window
    assert dated.max() <= np.datetime64(alerts.acquired) and dated.min() > np.datetime64(alerts.acquired) - np.timedelta64(400, "D")
    print(f"\nlive read: {g.name}, shape {alerts.status.shape}, cost {alerts.cost}")
