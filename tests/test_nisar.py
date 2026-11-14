"""NISAR GCOV reader: offline on tiny synthetic files with the real group layout; live tests opt-in.

Live:  SARWATCH_LIVE=1 python -m pytest tests/test_nisar.py -k live -s      (search, no login)
       EARTHDATA_TOKEN=... also runs the remote read and prints its MB / seconds.
"""
import math
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest

from sarwatch import nisar
from sarwatch.nisar import Granule, pick_track, read_crop, read_stack

UTC = timezone.utc
EPSG = 32631  # UTM 31N, Catalonia
BBOX = (1.845, 41.445, 1.855, 41.452)  # ~0.8 x 0.8 km at Agroparc Penedes
DX = 20.0


# ---------------------------------------------------------------- synthetic GCOV files


def make_gcov(path, *, x0, y0, nx=96, ny=80, dx=DX, epsg=EPSG, start="2026-07-01T05:00:00.123456789",
              terms=("HHHH", "HVHV"), mask=None, edit=None, chunks=(16, 16)):
    """Write a GCOV-shaped HDF5. x0, y0 = top-left pixel corner. Pixel (r, c) of term i holds (i+1)*(r*1000+c+1)."""
    h5py = pytest.importorskip("h5py")
    with h5py.File(path, "w") as f:
        ident = f.create_group("science/LSAR/identification")
        ident["zeroDopplerStartTime"] = np.bytes_(start)
        ident["trackNumber"] = np.uint32(130)
        ident["frameNumber"] = np.uint16(22)
        ident["orbitPassDirection"] = np.bytes_("Ascending")
        g = f.create_group("science/LSAR/GCOV/grids/frequencyA")
        g["xCoordinates"] = x0 + dx * (0.5 + np.arange(nx))  # pixel centres, as in the spec
        g["yCoordinates"] = y0 - dx * (0.5 + np.arange(ny))  # north-up: y decreases down the rows
        g["xCoordinateSpacing"] = dx
        g["yCoordinateSpacing"] = -dx
        g.create_dataset("projection", data=np.uint32(epsg)).attrs["epsg_code"] = np.int32(epsg)
        g["listOfPolarizations"] = np.array([t[:2].encode() for t in terms])
        rows, cols = np.mgrid[0:ny, 0:nx]
        base = (rows * 1000 + cols + 1).astype(np.float32)
        for i, term in enumerate(terms):
            values = base * (i + 1)
            if edit:
                edit(term, values)
            d = g.create_dataset(term, data=values, chunks=chunks, compression="gzip", fillvalue=np.nan)
            d.attrs["_FillValue"] = np.float32(np.nan)
        m = np.ones((ny, nx), np.uint8) if mask is None else mask
        g.create_dataset("mask", data=m, chunks=chunks, compression="gzip").attrs["_FillValue"] = np.uint8(255)
    return path


@pytest.fixture
def grid():
    """A grid whose top-left corner sits 10 pixels left of and above BBOX, on a 20 m lattice."""
    xmin, ymin, xmax, ymax = nisar._project_bbox(BBOX, EPSG)
    x0 = math.floor(xmin / DX) * DX - 10 * DX
    y0 = math.ceil(ymax / DX) * DX + 10 * DX
    return x0, y0


def expected_window(x0, y0, pbox):
    xmin, ymin, xmax, ymax = pbox
    return (math.floor((y0 - ymax) / DX), math.ceil((y0 - ymin) / DX),
            math.floor((xmin - x0) / DX), math.ceil((xmax - x0) / DX))


def test_crop_reads_the_right_window(tmp_path, grid):
    x0, y0 = grid
    path = make_gcov(tmp_path / "g.h5", x0=x0, y0=y0)
    crop = read_crop(path, BBOX)
    r0, r1, c0, c1 = expected_window(x0, y0, nisar._project_bbox(BBOX, EPSG))
    rows, cols = np.mgrid[r0:r1, c0:c1]
    assert set(crop.data) == {"HH", "HV"}
    assert crop.data["HH"].dtype == np.float32
    np.testing.assert_array_equal(crop.data["HH"], rows * 1000 + cols + 1)
    np.testing.assert_array_equal(crop.data["HV"], 2 * (rows * 1000 + cols + 1))
    assert crop.epsg == EPSG
    assert crop.date == datetime(2026, 7, 1, 5, 0, 0, 123456, tzinfo=UTC)
    assert crop.bytes_read > 0 and crop.seconds >= 0


def test_transform_maps_window_corner_and_covers_bbox(tmp_path, grid):
    x0, y0 = grid
    path = make_gcov(tmp_path / "g.h5", x0=x0, y0=y0)
    crop = read_crop(path, BBOX)
    a, b, c, d, e, f = crop.transform
    assert (a, b, d, e) == (DX, 0.0, 0.0, -DX)
    r0, _, c0, _ = expected_window(x0, y0, nisar._project_bbox(BBOX, EPSG))
    assert (c, f) == (x0 + c0 * DX, y0 - r0 * DX)  # corner of the window's first pixel
    # the centre of window pixel (i, j) is the file's xCoordinates[c0 + j], yCoordinates[r0 + i]
    i, j = 3, 5
    assert a * (j + 0.5) + c == x0 + DX * (c0 + j + 0.5)
    assert e * (i + 0.5) + f == y0 - DX * (r0 + i + 0.5)
    # the window covers the bbox, and no whole row or column could be dropped
    h, w = crop.data["HH"].shape
    xmin, ymin, xmax, ymax = nisar._project_bbox(BBOX, EPSG)
    assert c <= xmin < c + DX and c + (w - 1) * DX < xmax <= c + w * DX
    assert f - DX < ymax <= f and f - h * DX <= ymin < f - (h - 1) * DX


def test_invalid_pixels_become_nan(tmp_path, grid):
    x0, y0 = grid
    r0, _, c0, _ = expected_window(x0, y0, nisar._project_bbox(BBOX, EPSG))
    mask = np.ones((80, 96), np.uint8)
    mask[r0 + 1, c0 + 1] = 0  # partly focused
    mask[r0 + 2, c0 + 2] = 255  # outside the swath

    def edit(term, values):
        if term == "HHHH":
            values[r0 + 3, c0 + 3] = np.nan  # the product's fill value
            values[r0 + 4, c0 + 4] = 0.0  # no power: no dB

    crop = read_crop(make_gcov(tmp_path / "g.h5", x0=x0, y0=y0, mask=mask, edit=edit), BBOX)
    hh, hv = crop.data["HH"], crop.data["HV"]
    assert all(np.isnan(hh[k, k]) for k in (1, 2, 3, 4))
    assert np.isnan(hv[1, 1]) and np.isnan(hv[2, 2]) and np.isfinite(hv[3, 3])
    assert np.isfinite(hh).sum() == hh.size - 4


def test_bbox_past_the_granule_edge_is_nan_padded(tmp_path, grid):
    x0, y0 = grid
    full = read_crop(make_gcov(tmp_path / "full.h5", x0=x0, y0=y0), BBOX)
    _, _, c0, c1 = expected_window(x0, y0, nisar._project_bbox(BBOX, EPSG))
    cut = c0 + (c1 - c0) // 2  # the granule ends halfway across the bbox
    half = read_crop(make_gcov(tmp_path / "half.h5", x0=x0, y0=y0, nx=cut), BBOX)
    assert half.transform == full.transform
    assert half.data["HH"].shape == full.data["HH"].shape
    k = cut - c0
    np.testing.assert_array_equal(half.data["HH"][:, :k], full.data["HH"][:, :k])
    assert np.isnan(half.data["HH"][:, k:]).all()


def test_bbox_outside_the_granule_raises(tmp_path, grid):
    x0, y0 = grid
    with pytest.raises(ValueError, match="does not overlap"):
        read_crop(make_gcov(tmp_path / "g.h5", x0=x0 + 50_000, y0=y0), BBOX)


def test_bad_bbox_and_missing_pol_raise(tmp_path, grid):
    x0, y0 = grid
    path = make_gcov(tmp_path / "g.h5", x0=x0, y0=y0)
    with pytest.raises(ValueError, match="west, south, east, north"):
        read_crop(path, (1.855, 41.445, 1.845, 41.452))  # east before west
    with pytest.raises(KeyError, match="VVVV"):
        read_crop(path, BBOX, pols=("VV",))
    with pytest.raises(ValueError, match="frequencyB"):
        read_crop(path, BBOX, frequency="B")


def _granule(path, day, maturity="PROVISIONAL"):
    return Granule(name=path.stem, url=str(path), start=datetime(2026, 7, day, 5, tzinfo=UTC),
                   track=130, frame=22, direction="ASCENDING", maturity=maturity, size_mb=1.0)


def test_read_stack_sorts_by_time_on_one_grid(tmp_path, grid):
    x0, y0 = grid
    granules = []
    for day in (13, 1, 25):
        path = make_gcov(tmp_path / f"d{day}.h5", x0=x0, y0=y0, start=f"2026-07-{day:02d}T05:00:00.0")
        granules.append(_granule(path, day))
    stack, dates, transform, epsg = read_stack(granules, BBOX)
    assert [d.day for d in dates] == [1, 13, 25]
    single = read_crop(granules[0].url, BBOX)
    assert stack["HH"].shape == (3, *single.data["HH"].shape)
    assert stack["HV"].dtype == np.float32
    assert transform == single.transform and epsg == EPSG
    np.testing.assert_array_equal(stack["HH"][2], single.data["HH"])


@pytest.mark.parametrize("shift, spacing", [(10.0, DX), (0.0, 10.0)])
def test_read_stack_rejects_a_different_grid(tmp_path, grid, shift, spacing):
    x0, y0 = grid
    a = make_gcov(tmp_path / "a.h5", x0=x0, y0=y0)
    b = make_gcov(tmp_path / "b.h5", x0=x0 + shift, y0=y0, dx=spacing, nx=200, ny=200)
    with pytest.raises(ValueError, match="different grid"):
        read_stack([_granule(a, 1), _granule(b, 13)], BBOX)


# ---------------------------------------------------------------- remote reads (local fake archive)


class _FakeArchive(BaseHTTPRequestHandler):
    """Mimics ASF: bearer token -> 307 to a signed URL on another host; bad token -> login page."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _reply(self, status, headers=(), body=b""):
        self.send_response(status)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        auth = self.headers.get("Authorization")
        self.server.seen.append((self.path, auth))
        if self.path.startswith("/NISAR/"):
            if auth != "Bearer good-token":
                return self._reply(302, [("Location", "https://urs.earthdata.nasa.gov/oauth/authorize?client_id=x")])
            signed = f"http://localhost:{self.server.server_port}/signed/g.h5?Expires=1&Signature=abc"
            return self._reply(307, [("Location", signed)])
        if auth is not None:  # S3 refuses a signed URL that also carries an Authorization header
            return self._reply(400, body=b"Only one auth mechanism allowed")
        m = re.fullmatch(r"bytes=(\d+)-(\d+)", self.headers.get("Range", ""))
        data = self.server.payload
        a, b = int(m[1]), min(int(m[2]), len(data) - 1)
        self._reply(206, [("Content-Range", f"bytes {a}-{b}/{len(data)}")], data[a:b + 1])


@pytest.fixture
def archive(tmp_path, grid):
    pytest.importorskip("requests")
    x0, y0 = grid
    path = make_gcov(tmp_path / "g.h5", x0=x0, y0=y0, nx=512, ny=512, chunks=(32, 32))
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeArchive)
    server.payload, server.seen = path.read_bytes(), []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server, path, f"http://127.0.0.1:{server.server_port}/NISAR/NISAR_L2_GCOV_V1/g/g.h5"
    server.shutdown()
    server.server_close()


def test_remote_read_matches_local_and_sends_token_only_to_archive(archive, monkeypatch):
    server, path, url = archive
    monkeypatch.setattr(nisar, "BLOCK_SIZE", 8192)
    remote = read_crop(url, BBOX, token="good-token")
    local = read_crop(path, BBOX)
    np.testing.assert_array_equal(remote.data["HH"], local.data["HH"])
    assert remote.transform == local.transform and remote.date == local.date
    assert 0 < remote.bytes_read < len(server.payload) / 4  # only the window's chunks and metadata
    archive_hits = [auth for p, auth in server.seen if p.startswith("/NISAR/")]
    signed_hits = [auth for p, auth in server.seen if p.startswith("/signed/")]
    assert archive_hits == ["Bearer good-token"]  # redirect resolved once
    assert signed_hits and all(auth is None for auth in signed_hits)


def test_remote_read_with_token_from_environment(archive, monkeypatch):
    _, _, url = archive
    monkeypatch.setenv("EARTHDATA_TOKEN", "good-token")
    assert read_crop(url, BBOX, pols=("HV",)).data["HV"].size > 0


def test_rejected_or_missing_token_raises(archive, monkeypatch):
    _, _, url = archive
    with pytest.raises(PermissionError, match="did not accept"):
        read_crop(url, BBOX, token="expired")
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    with pytest.raises(PermissionError, match="EARTHDATA_TOKEN"):
        read_crop(url, BBOX)


# ---------------------------------------------------------------- pick_track and search parsing


def G(track, day, maturity="PROVISIONAL", coverage="F", counter="001", frame=35, direction="ASCENDING", month=7):
    start = datetime(2026, month, day, 2, 3, 20, tzinfo=UTC)
    crid = "P05036" if maturity == "VALIDATED" else "P05023"
    name = (f"NISAR_L2_PR_GCOV_010_{track:03d}_{direction[0]}_{frame:03d}_2005_DHDH_A_{start:%Y%m%dT%H%M%S}_"
            f"{start + timedelta(seconds=37):%Y%m%dT%H%M%S}_{crid}_N_{coverage}_J_{counter}")
    return Granule(name, f"https://example/{name}.h5", start, track, frame, direction, maturity, 2000.0)


def test_pick_track_takes_most_dates_one_per_date_sorted():
    granules = [G(157, d) for d in (25, 7, 19)] + [G(13, d, frame=34) for d in (7, 19)]
    granules += [G(157, 19, coverage="P"), G(157, 7, counter="002")]
    picked = pick_track(granules)
    assert [(g.track, g.start.day) for g in picked] == [(157, 7), (157, 19), (157, 25)]
    assert picked[0].name.endswith("_002")  # newer product counter wins
    assert picked[1].name.endswith("_F_J_001")  # full frame beats partial


def test_pick_track_maturity_floor_and_preference():
    granules = [G(66, d, "BETA", frame=68, direction="DESCENDING") for d in range(1, 10)]
    granules += [G(157, 5), G(157, 17, "VALIDATED"), G(157, 17)]
    picked = pick_track(granules)
    assert [g.track for g in picked] == [157, 157]
    assert picked[1].maturity == "VALIDATED"
    assert len(pick_track(granules, min_maturity="BETA")) == 9
    assert pick_track(granules, min_maturity="VALIDATED") == [granules[-2]]
    assert pick_track([G(157, 5, "BETA")]) == []


def test_pick_track_tie_goes_to_most_recent_stack():
    a = [G(130, d, frame=22, coverage="P") for d in (2, 14)]
    b = [G(66, d, frame=68, direction="DESCENDING") for d in (1, 13)]
    assert pick_track(a + b)[0].track == 130


ASF_RECORD = {
    "collectionName": "NISAR_L2_GCOV_V1",
    "downloadUrl": "https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_V1/X/X.h5",
    "fileName": "X.h5",
    "flightDirection": "ASCENDING",
    "frame": 35,
    "granuleName": "X",
    "path": 157,
    "startTime": "2026-11-04T02:03:20Z",
    "nisar": {"sizeMB": {"X.h5": {"bytes": 2051014656, "format": "HDF5"}}},
}


def test_search_parses_asf_records(monkeypatch):
    requests = pytest.importorskip("requests")
    sent = {}

    class Reply:
        def raise_for_status(self):
            pass

        def json(self):
            provisional = dict(ASF_RECORD, granuleName="Y", startTime="2026-06-25T02:03:20Z",
                               downloadUrl=ASF_RECORD["downloadUrl"].replace("GCOV_V1", "GCOV_PROVISIONAL_V1"))
            return {"results": [ASF_RECORD, provisional]}

    def fake_get(url, params, timeout):
        sent.update(params)
        return Reply()

    monkeypatch.setattr(requests, "get", fake_get)
    found = nisar.search((26.0, 64.8, 26.1, 64.9), start=datetime(2026, 6, 1))
    assert sent["intersectsWith"] == "POLYGON((26.0 64.8,26.1 64.8,26.1 64.9,26.0 64.9,26.0 64.8))"
    assert sent["start"] == "2026-06-01T00:00:00Z" and "end" not in sent
    assert [g.name for g in found] == ["Y", "X"]  # oldest first
    x = found[1]
    assert (x.track, x.frame, x.direction, x.maturity) == (157, 35, "ASCENDING", "VALIDATED")
    assert x.start == datetime(2026, 11, 4, 2, 3, 20, tzinfo=UTC)
    assert x.size_mb == pytest.approx(2051.014656)
    assert found[0].maturity == "PROVISIONAL"


# ---------------------------------------------------------------- projections


def _local_scales(project, lon, lat, d=1e-5):
    """Scale along the parallel, scale along the meridian, cos(angle between them), by central differences."""
    def p(lo, la):
        x, y = project(np.array([lo]), np.array([la]))
        return np.array([float(np.asarray(x)[0]), float(np.asarray(y)[0])])

    rad = math.radians(d)
    d_lam = (p(lon + d, lat) - p(lon - d, lat)) / (2 * rad)
    d_phi = (p(lon, lat + d) - p(lon, lat - d)) / (2 * rad)
    e2, s = nisar._E**2, math.sin(math.radians(lat))
    nu = nisar._A / math.sqrt(1 - e2 * s * s)  # prime-vertical radius
    rho = nisar._A * (1 - e2) / (1 - e2 * s * s) ** 1.5  # meridian radius
    k = np.linalg.norm(d_lam) / (nu * math.cos(math.radians(lat)))
    h = np.linalg.norm(d_phi) / rho
    return k, h, d_lam @ d_phi / (np.linalg.norm(d_lam) * np.linalg.norm(d_phi))


def test_utm_central_meridian_is_the_scaled_meridian_arc():
    from scipy.integrate import quad

    e2 = nisar._E**2
    arc, _ = quad(lambda p: nisar._A * (1 - e2) / (1 - e2 * math.sin(p) ** 2) ** 1.5, 0, math.radians(45))
    x, y = nisar._utm(np.array([3.0]), np.array([45.0]), zone=31)
    assert x[0] == pytest.approx(500_000, abs=1e-6)
    assert y[0] == pytest.approx(0.9996 * arc, abs=1e-3)  # ~4,982,950 m
    _, y_south = nisar._utm(np.array([3.0]), np.array([-45.0]), zone=31, south=True)
    assert y_south[0] == pytest.approx(10_000_000 - 0.9996 * arc, abs=1e-3)


@pytest.mark.parametrize("epsg, lon, lat", [(32631, 1.85, 41.45), (32635, 26.044, 64.843), (32631, 5.9, 60.0)])
def test_utm_is_conformal_off_the_central_meridian(epsg, lon, lat):
    k, h, cos_angle = _local_scales(nisar._projector(epsg), lon, lat)
    assert k == pytest.approx(h, rel=1e-7) and abs(cos_angle) < 1e-7
    assert 0.9996 < k < 1.001  # inside a zone the scale stays within the UTM design range


@pytest.mark.parametrize("epsg, lat_ts", [(3413, 70.0), (3031, -71.0)])
def test_polar_stereographic_scale_and_orientation(epsg, lat_ts):
    project = nisar._projector(epsg)
    k, h, cos_angle = _local_scales(project, 26.044, lat_ts)
    assert k == pytest.approx(1.0, rel=1e-7) and h == pytest.approx(1.0, rel=1e-7) and abs(cos_angle) < 1e-7
    k, h, cos_angle = _local_scales(project, 26.044, math.copysign(64.843, lat_ts))
    assert k == pytest.approx(h, rel=1e-7) and abs(cos_angle) < 1e-7
    pole = project(np.array([10.0]), np.array([math.copysign(90.0, lat_ts)]))
    assert np.allclose(np.ravel(pole), 0.0, atol=1e-6)
    if epsg == 3413:  # lon -45 points down the y axis, lon 45 along +x
        x, y = project(np.array([-45.0, 45.0]), np.array([70.0, 70.0]))
        assert abs(x[0]) < 1e-6 and y[0] < 0 and x[1] > 0 and abs(y[1]) < 1e-6
    else:  # lon 0 points up the y axis, lon 90 along +x
        x, y = project(np.array([0.0, 90.0]), np.array([-71.0, -71.0]))
        assert abs(x[0]) < 1e-6 and y[0] > 0 and x[1] > 0 and abs(y[1]) < 1e-6


@pytest.mark.parametrize("epsg, lon, lat", [(32631, 1.85, 41.45), (32635, 26.044, 64.843), (32735, 26.0, -30.0),
                                            (3413, 26.044, 64.843), (3031, 140.0, -75.0)])
def test_projections_match_pyproj(epsg, lon, lat):
    pyproj = pytest.importorskip("pyproj")
    want = pyproj.Transformer.from_crs(4326, epsg, always_xy=True).transform(lon, lat)
    got = nisar._projector(epsg)(np.array([lon]), np.array([lat]))
    assert np.allclose(np.ravel(got), want, atol=1e-3)


# ---------------------------------------------------------------- live (opt-in)

MUHOS = (26.034, 64.838, 26.054, 64.848)  # ~1 x 1 km around the Muhos clear-cut test point (26.044, 64.843)
AGROPARC = (1.84, 41.44, 1.86, 41.46)
live_search = pytest.mark.skipif(os.environ.get("SARWATCH_LIVE") != "1", reason="set SARWATCH_LIVE=1")
live_read = pytest.mark.skipif(not os.environ.get("EARTHDATA_TOKEN"), reason="set EARTHDATA_TOKEN")


@live_search
@pytest.mark.parametrize("bbox, track, frame, n_dates, first, last", [
    (MUHOS, 157, 35, 11, "2026-06-25", "2026-11-04"),  # 12 granules: 2026-09-05 has two (counters 001, 002)
    (AGROPARC, 130, 22, 11, "2026-06-23", "2026-11-02"),
])
def test_live_search_and_pick_track(bbox, track, frame, n_dates, first, last):
    picked = pick_track(nisar.search(bbox, end="2026-11-10T00:00:00Z"))
    print(f"\n{bbox}: track {picked[0].track} frame {picked[0].frame} {picked[0].direction}, {len(picked)} dates, "
          f"{picked[0].start:%Y-%m-%d} -> {picked[-1].start:%Y-%m-%d}, "
          f"{sorted({g.maturity for g in picked})}, {sum(g.size_mb for g in picked) / 1000:.1f} GB")
    assert (picked[0].track, picked[0].frame, picked[0].direction) == (track, frame, "ASCENDING")
    assert len(picked) == n_dates
    assert (str(picked[0].start.date()), str(picked[-1].start.date())) == (first, last)


@live_read
def test_live_read_one_crop():
    granule = pick_track(nisar.search(MUHOS, end="2026-11-10T00:00:00Z"))[-1]
    crop = read_crop(granule.url, MUHOS)
    hh, hv = crop.data["HH"], crop.data["HV"]
    print(f"\n{granule.name}\n  EPSG {crop.epsg}, {hh.shape} px, transform {crop.transform}\n"
          f"  {crop.bytes_read / 1e6:.2f} MB in {crop.seconds:.1f} s, valid {np.isfinite(hh).mean():.0%}, "
          f"median HH {10 * np.log10(np.nanmedian(hh)):.1f} dB, HV {10 * np.log10(np.nanmedian(hv)):.1f} dB")
    assert crop.epsg in (32635, 3413)
    assert hh.shape == hv.shape and np.isfinite(hh).mean() > 0.5
    assert 1e-4 < np.nanmedian(hh) < 1 and 1e-5 < np.nanmedian(hv) < np.nanmedian(hh)  # dB in [-40, 0], HV < HH
    assert crop.date.date() == granule.start.date()
