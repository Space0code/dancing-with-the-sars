"""Find NISAR L2 GCOV granules and read small windows of them straight from NASA's archive (ASF).

Layout, units, auth and gotchas behind this code: kb/data-nisar-gcov.md.

    granules = pick_track(search(bbox))                      # bbox = (west, south, east, north), degrees
    stack, dates, transform, epsg = read_stack(granules, bbox)   # needs EARTHDATA_TOKEN

Only the bytes of the window are fetched (HTTP range requests), never the 1-2 GB file.
`search` and `pick_track` need `requests` only; reading needs `h5py` too.
"""
from __future__ import annotations

import io
import logging
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from urllib.parse import urljoin, urlsplit

import numpy as np

log = logging.getLogger(__name__)

SEARCH_URL = "https://api.daac.asf.alaska.edu/services/search/param"
LOGIN_HOST = "urs.earthdata.nasa.gov"  # the archive redirects here when the token is missing or refused
MATURITY_RANK = {"BETA": 0, "PROVISIONAL": 1, "VALIDATED": 2}
GRIDS = "/science/LSAR/GCOV/grids/frequency{}"
START_TIME = "/science/LSAR/identification/zeroDopplerStartTime"
TERMS = {"HH": "HHHH", "HV": "HVHV", "VH": "VHVH", "VV": "VVVV", "RH": "RHRH", "RV": "RVRV"}
INVALID_MASK = (0, 255)  # mask: 0 = partly focused / invalid, 255 = outside the swath, 1..5 = valid sub-swath
BLOCK_SIZE = 2 * 1024 * 1024  # bytes per range request unit; a NISAR chunk is nominally 512x512 pixels
MAX_PIXELS = 25_000_000  # refuse windows above ~100 km x 100 km at 20 m (likely a lon/lat mix-up)


# ---------------------------------------------------------------- search


@dataclass
class Granule:
    name: str
    url: str
    start: datetime  # UTC, timezone-aware
    track: int
    frame: int
    direction: str  # "ASCENDING" | "DESCENDING"
    maturity: str  # "BETA" | "PROVISIONAL" | "VALIDATED"
    size_mb: float  # 1 MB = 1e6 bytes


def search(bbox, start=None, end=None) -> list[Granule]:
    """All GCOV granules intersecting bbox (west, south, east, north in degrees), oldest first. No login needed."""
    import requests

    w, s, e, n = _check_bbox(bbox)
    params = {
        "dataset": "NISAR",
        "processingLevel": "GCOV",
        "intersectsWith": f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))",
        "output": "jsonlite",
    }
    if start is not None:
        params["start"] = _iso(start)
    if end is not None:
        params["end"] = _iso(end)
    r = requests.get(SEARCH_URL, params=params, timeout=120)
    r.raise_for_status()
    granules = [g for g in map(_granule, r.json()["results"]) if g is not None]
    return sorted(granules, key=lambda g: (g.start, g.name))


def _granule(rec: dict) -> Granule | None:
    url = rec["downloadUrl"]
    maturity = _maturity(url) or _maturity(rec.get("collectionName", ""))
    if maturity is None:
        log.warning("skipping %s: unknown collection", rec.get("granuleName"))
        return None
    size = (rec.get("nisar") or {}).get("sizeMB", {}).get(rec.get("fileName"), {}).get("bytes")
    return Granule(
        name=rec["granuleName"],
        url=url,
        start=_parse_time(rec["startTime"]),
        track=int(rec["path"]),
        frame=int(rec["frame"]),
        direction=rec["flightDirection"].upper(),
        maturity=maturity,
        size_mb=size / 1e6 if size else 0.0,
    )


def _maturity(text: str) -> str | None:
    """Collection name in the URL path: NISAR_L2_GCOV_BETA_V1 / _PROVISIONAL_V1 / NISAR_L2_GCOV_V1 (validated)."""
    m = re.search(r"NISAR_L2_GCOV_(?:(BETA|PROVISIONAL)_)?V\d+(?=/|$)", text)
    if m is None:
        return None
    return m.group(1) or "VALIDATED"


def pick_track(granules, min_maturity="PROVISIONAL") -> list[Granule]:
    """The track + frame + direction with the most distinct dates at or above min_maturity, one granule per date.

    Ties go to the stack whose last date is most recent. Per date: higher maturity, then full frame, then the
    newer processing (CRID, product counter). Sorted by time.
    """
    floor = MATURITY_RANK[min_maturity.upper()]
    groups: dict[tuple, dict[date, Granule]] = {}
    for g in granules:
        if MATURITY_RANK[g.maturity] < floor:
            continue
        per_date = groups.setdefault((g.track, g.frame, g.direction), {})
        day = g.start.date()
        if day not in per_date or _preference(g) > _preference(per_date[day]):
            per_date[day] = g
    if not groups:
        return []
    stacks = [sorted(d.values(), key=lambda g: g.start) for d in groups.values()]
    return max(stacks, key=lambda s: (len(s), s[-1].start, -s[0].start.timestamp(), -s[0].track, -s[0].frame))


def _preference(g: Granule) -> tuple:
    # NISAR_L2_PR_GCOV_<cycle>_<track>_<A|D>_<frame>_<mode>_<pol>_<src>_<start>_<end>_<CRID>_<acc>_<F|P>_<loc>_<ctr>
    parts = g.name.split("_")
    full, crid, counter = (parts[15] == "F", parts[13], parts[17]) if len(parts) == 18 else (False, "", "")
    return MATURITY_RANK[g.maturity], full, crid, counter, g.size_mb


# ---------------------------------------------------------------- reading


@dataclass
class Crop:
    data: dict  # polarization -> 2D float32, linear power (gamma0), NaN where invalid
    transform: tuple  # (a, b, c, d, e, f): x = a*col + b*row + c ; y = d*col + e*row + f (pixel corners)
    epsg: int
    date: datetime  # zero-Doppler start time, UTC
    bytes_read: int  # bytes fetched (remote: network bytes; local: file bytes)
    seconds: float


def read_crop(url, bbox, pols=("HH", "HV"), token=None, frequency="A") -> Crop:
    """Read the window covering bbox (degrees) from a GCOV file: an https URL on ASF, or a local path.

    The window is the smallest set of the file's own pixels covering bbox; parts outside the granule are NaN.
    token defaults to $EARTHDATA_TOKEN (only needed for URLs).
    """
    import h5py

    t0 = time.perf_counter()
    raw = _open(url, token)
    try:
        with h5py.File(raw, "r", rdcc_nbytes=32 * 1024 * 1024) as h5:
            data, transform, epsg = _read_window(h5, bbox, pols, frequency)
            when = _parse_time(h5[START_TIME][()])
    finally:
        raw.close()
    seconds = time.perf_counter() - t0
    name = str(url).rsplit("/", 1)[-1]
    log.info("%s: %.1f MB in %d requests, %.1f s", name, raw.bytes_read / 1e6, raw.requests, seconds)
    return Crop(data, transform, epsg, when, raw.bytes_read, seconds)


def read_stack(granules, bbox, pols=("HH", "HV"), token=None) -> tuple[dict, list, tuple, int]:
    """Read the same window from every granule: (pol -> (time, y, x) float32, dates, transform, epsg).

    All granules must share one pixel grid (same track/frame normally do); raises ValueError otherwise.
    """
    granules = sorted(granules, key=lambda g: g.start)
    if not granules:
        raise ValueError("read_stack needs at least one granule")
    crops = []
    for g in granules:
        crop = read_crop(g.url, bbox, pols, token)
        if crops:
            _check_same_grid(crops[0], crop, granules[0].name, g.name)
        crops.append(crop)
    stack = {p: np.stack([c.data[p] for c in crops]) for p in pols}
    return stack, [c.date for c in crops], crops[0].transform, crops[0].epsg


def _check_same_grid(ref: Crop, crop: Crop, ref_name: str, name: str) -> None:
    shape, ref_shape = next(iter(crop.data.values())).shape, next(iter(ref.data.values())).shape
    tol = 1e-6 * abs(ref.transform[0])
    if crop.epsg != ref.epsg or shape != ref_shape or not np.allclose(crop.transform, ref.transform, rtol=0, atol=tol):
        raise ValueError(
            f"{name} is on a different grid than {ref_name}: EPSG {crop.epsg} vs {ref.epsg}, "
            f"shape {shape} vs {ref_shape}, transform {crop.transform} vs {ref.transform}. "
            "Use granules from one track and frame (pick_track)."
        )


def _read_window(h5, bbox, pols, frequency):
    path = GRIDS.format(frequency)
    if path not in h5:
        raise ValueError(f"no {path} in this granule (its radar mode has no frequency {frequency})")
    grid = h5[path]
    epsg = _epsg(grid["projection"])
    xs, ys = grid["xCoordinates"], grid["yCoordinates"]
    nx, ny = xs.shape[0], ys.shape[0]
    xa, ya = xs[:2], ys[:2]  # two values give origin and spacing; no need to fetch the whole vectors
    dx, dy = float(xa[1] - xa[0]), float(ya[1] - ya[0])
    x0, y0 = float(xa[0]) - dx / 2, float(ya[0]) - dy / 2  # coordinates are pixel centres; we want corners
    r0, r1, c0, c1 = _window(x0, dx, nx, y0, dy, ny, _project_bbox(bbox, epsg))
    rr0, rr1, cc0, cc1 = max(r0, 0), min(r1, ny), max(c0, 0), min(c1, nx)
    inside = (slice(rr0 - r0, rr1 - r0), slice(cc0 - c0, cc1 - c0))

    invalid = np.zeros((rr1 - rr0, cc1 - cc0), bool)
    if "mask" in grid:
        invalid |= np.isin(grid["mask"][rr0:rr1, cc0:cc1], INVALID_MASK)
    data = {}
    for pol in pols:
        term = TERMS.get(pol.upper(), pol.upper())
        if term not in grid:
            have = sorted(k for k in grid if k in TERMS.values())
            raise KeyError(f"{term} not in {path}; this granule has {have}")
        ds = grid[term]
        if ds.dtype.kind == "c":
            raise ValueError(f"{term} is a complex cross-term; read_crop returns power terms only")
        values = ds[rr0:rr1, cc0:cc1].astype(np.float32)
        bad = invalid | ~np.isfinite(values) | (values <= 0)
        fill = ds.attrs.get("_FillValue")
        if fill is not None and np.isfinite(np.asarray(fill).ravel()[0]):
            bad |= values == np.float32(np.asarray(fill).ravel()[0])
        values[bad] = np.nan
        out = np.full((r1 - r0, c1 - c0), np.nan, np.float32)
        out[inside] = values
        data[pol] = out
    return data, (dx, 0.0, x0 + c0 * dx, 0.0, dy, y0 + r0 * dy), epsg


def _window(x0, dx, nx, y0, dy, ny, pbox):
    """Rows r0:r1 and columns c0:c1 of the file's lattice covering pbox (may reach past the grid)."""
    xmin, ymin, xmax, ymax = pbox
    cols = sorted(((xmin - x0) / dx, (xmax - x0) / dx))
    rows = sorted(((ymin - y0) / dy, (ymax - y0) / dy))
    c0, c1 = math.floor(cols[0] + 1e-9), math.ceil(cols[1] - 1e-9)
    r0, r1 = math.floor(rows[0] + 1e-9), math.ceil(rows[1] - 1e-9)
    if c1 <= 0 or c0 >= nx or r1 <= 0 or r0 >= ny:
        raise ValueError("bbox does not overlap this granule")
    if (r1 - r0) * (c1 - c0) > MAX_PIXELS:
        raise ValueError(f"window of {r1 - r0}x{c1 - c0} pixels is too large; is bbox (west, south, east, north)?")
    return r0, r1, c0, c1


def _epsg(ds) -> int:
    code = int(np.asarray(ds[()]).ravel()[0])  # spec: the "projection" dataset's value is the EPSG code
    return code or int(np.asarray(ds.attrs["epsg_code"]).ravel()[0])


# ---------------------------------------------------------------- range-request file


def _open(url, token=None) -> "_BlockFile":
    if str(url).startswith(("http://", "https://")):
        token = token or os.environ.get("EARTHDATA_TOKEN")
        if not token:
            raise PermissionError("reading NISAR from ASF needs an Earthdata Login token: set EARTHDATA_TOKEN")
        src = _HttpSource(url, token)
        return _BlockFile(src.fetch, src.size, BLOCK_SIZE)
    f = open(url, "rb")

    def fetch(start, stop):
        f.seek(start)
        return f.read(stop - start)

    return _BlockFile(fetch, os.fstat(f.fileno()).st_size, BLOCK_SIZE, on_close=f.close)


class _BlockFile(io.RawIOBase):
    """Read-only, seekable file over fetch(start, stop) -> bytes, cached in aligned blocks.

    HDF5 issues many small reads; caching whole blocks turns them into a few large range requests.
    Missing neighbouring blocks are fetched in one request.
    """

    def __init__(self, fetch, size, block_size, on_close=None):
        super().__init__()
        self._fetch, self._size, self._bs, self._on_close = fetch, size, block_size, on_close
        self._blocks: dict[int, bytes] = {}
        self._pos = 0
        self.bytes_read = 0
        self.requests = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self._pos

    def seek(self, offset, whence=io.SEEK_SET):
        self._pos = offset + (0, self._pos, self._size)[whence]
        return self._pos

    def readinto(self, buf):
        view = memoryview(buf).cast("B")
        stop = min(self._pos + len(view), self._size)
        if stop <= self._pos:
            return 0
        first, last = self._pos // self._bs, (stop - 1) // self._bs
        self._load(first, last)
        done = 0
        for i in range(first, last + 1):
            a = max(self._pos, i * self._bs) - i * self._bs
            b = min(stop, (i + 1) * self._bs) - i * self._bs
            view[done:done + b - a] = self._blocks[i][a:b]
            done += b - a
        self._pos = stop
        return done

    def _load(self, first, last):
        i = first
        while i <= last:
            if i in self._blocks:
                i += 1
                continue
            j = i
            while j < last and j + 1 not in self._blocks:
                j += 1
            data = self._fetch(i * self._bs, min((j + 1) * self._bs, self._size))
            self.bytes_read += len(data)
            self.requests += 1
            for k in range(i, j + 1):
                self._blocks[k] = data[(k - i) * self._bs:(k - i + 1) * self._bs]
            i = j + 1

    def close(self):
        if not self.closed and self._on_close is not None:
            self._on_close()
        super().close()


class _HttpSource:
    """Byte ranges of one file on the ASF archive, authenticated with an Earthdata Login bearer token.

    The archive answers a GET with a redirect to a short-lived signed CloudFront URL. We follow the redirects
    by hand once: the token goes only to the archive host, never to the signed URL (it needs none, and a second
    auth mechanism can make S3 refuse it). Later range requests go straight to the signed URL; if it expires we
    resolve again.
    """

    MAX_REDIRECTS = 5

    def __init__(self, url, token, timeout=60):
        import requests

        self.session = requests.Session()
        self.session.trust_env = False  # with trust_env, a ~/.netrc entry would replace our bearer header
        self.url, self.token, self.timeout = url, token, timeout
        self._resolve()

    def _resolve(self):
        url, headers = self.url, {"Authorization": f"Bearer {self.token}"}
        origin = urlsplit(url).hostname
        for _ in range(self.MAX_REDIRECTS):
            r = self.session.get(
                url, headers={**headers, "Range": "bytes=0-0"}, allow_redirects=False, stream=True, timeout=self.timeout
            )
            if r.is_redirect or r.status_code == 206:
                r.content  # empty or 1 byte: consuming it lets the connection be reused
            r.close()
            if r.is_redirect:
                url = urljoin(url, r.headers["Location"])
                host = urlsplit(url).hostname
                if host == LOGIN_HOST:
                    raise PermissionError(
                        "Earthdata Login did not accept the token (redirected to the login page): "
                        "check EARTHDATA_TOKEN is a current user token (they expire after 60 days)"
                    )
                if host != origin:
                    headers = {}
                continue
            if r.status_code in (401, 403):
                raise PermissionError(f"HTTP {r.status_code} from {urlsplit(url).hostname}: access refused")
            if r.status_code != 206:
                raise OSError(f"expected 206 to a range request, got HTTP {r.status_code} from {urlsplit(url).hostname}")
            self.size = int(r.headers["Content-Range"].rsplit("/", 1)[1])
            self.data_url, self.headers = url, headers
            return
        raise OSError(f"more than {self.MAX_REDIRECTS} redirects for {self.url}")

    def fetch(self, start, stop):
        import requests

        for attempt in range(3):
            try:
                r = self.session.get(
                    self.data_url, headers={**self.headers, "Range": f"bytes={start}-{stop - 1}"}, timeout=self.timeout
                )
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
                continue
            if r.status_code == 206 and len(r.content) == stop - start:
                return r.content
            if r.status_code in (401, 403) and attempt == 0:  # signed URL expired: get a fresh one
                self._resolve()
                continue
            if r.status_code >= 500 and attempt < 2:
                time.sleep(2**attempt)
                continue
            raise OSError(f"range {start}-{stop - 1}: HTTP {r.status_code}, {len(r.content)} bytes")
        raise OSError(f"range {start}-{stop - 1}: giving up")


# ---------------------------------------------------------------- projections (WGS84, pure Python)

_A = 6378137.0
_F = 1 / 298.257223563
_E = math.sqrt(_F * (2 - _F))


def _projector(epsg: int):
    """lon, lat (degrees, arrays) -> x, y in metres for the projections NISAR L2 products use."""
    if 32601 <= epsg <= 32660 or 32701 <= epsg <= 32760:
        return lambda lon, lat: _utm(lon, lat, epsg % 100, south=epsg > 32700)
    if epsg == 3413:  # NSIDC Sea Ice Polar Stereographic North
        return lambda lon, lat: _polar_stereographic(lon, lat, lat_ts=70.0, lon0=-45.0)
    if epsg == 3031:  # Antarctic Polar Stereographic
        return lambda lon, lat: _polar_stereographic(lon, lat, lat_ts=-71.0, lon0=0.0)
    try:
        from pyproj import Transformer
    except ImportError as exc:
        raise ValueError(f"EPSG:{epsg} is not built in; install pyproj to read it") from exc
    return Transformer.from_crs(4326, epsg, always_xy=True).transform


def _utm(lon, lat, zone, south=False):
    """Transverse Mercator by the Kruger series (Karney 2011), sub-millimetre within a zone."""
    n = _F / (2 - _F)
    big_a = _A / (1 + n) * (1 + n**2 / 4 + n**4 / 64)
    alpha = (n / 2 - 2 * n**2 / 3 + 5 * n**3 / 16, 13 * n**2 / 48 - 3 * n**3 / 5, 61 * n**3 / 240)
    phi = np.radians(lat)
    dlam = np.radians(np.asarray(lon, float) - (6 * zone - 183))
    t = np.sinh(np.arctanh(np.sin(phi)) - _E * np.arctanh(_E * np.sin(phi)))
    xi = np.arctan2(t, np.cos(dlam))
    eta = np.arctanh(np.sin(dlam) / np.sqrt(1 + t * t))
    x = eta + sum(a * np.cos(2 * j * xi) * np.sinh(2 * j * eta) for j, a in enumerate(alpha, 1))
    y = xi + sum(a * np.sin(2 * j * xi) * np.cosh(2 * j * eta) for j, a in enumerate(alpha, 1))
    k0 = 0.9996
    return 500_000 + k0 * big_a * x, (10_000_000 if south else 0) + k0 * big_a * y


def _polar_stereographic(lon, lat, lat_ts, lon0):
    """Ellipsoidal polar stereographic with a latitude of true scale (Snyder 1987, eqs. 21-33, 21-34)."""
    sign = -1.0 if lat_ts < 0 else 1.0
    phi, phi_c = np.radians(sign * np.asarray(lat, float)), math.radians(sign * lat_ts)

    def t(p):
        return np.tan(np.pi / 4 - p / 2) / ((1 - _E * np.sin(p)) / (1 + _E * np.sin(p))) ** (_E / 2)

    m_c = math.cos(phi_c) / math.sqrt(1 - (_E * math.sin(phi_c)) ** 2)
    rho = _A * m_c * t(phi) / t(phi_c)
    dlam = np.radians(np.asarray(lon, float) - lon0)
    return rho * np.sin(dlam), -sign * rho * np.cos(dlam)


def _project_bbox(bbox, epsg, samples=33):
    """Projected (xmin, ymin, xmax, ymax) enclosing a lon/lat bbox; edges are sampled since they curve."""
    w, s, e, n = _check_bbox(bbox)
    t = np.linspace(0.0, 1.0, samples)
    lon = np.concatenate([w + (e - w) * t, np.full(samples, e), e - (e - w) * t, np.full(samples, w)])
    lat = np.concatenate([np.full(samples, s), s + (n - s) * t, np.full(samples, n), n - (n - s) * t])
    x, y = (np.asarray(v, float) for v in _projector(epsg)(lon, lat))
    return float(x.min()), float(y.min()), float(x.max()), float(y.max())


# ---------------------------------------------------------------- small helpers


def _check_bbox(bbox):
    w, s, e, n = (float(v) for v in bbox)
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise ValueError(f"bbox must be (west, south, east, north) in degrees, got {bbox}")
    return w, s, e, n


def _parse_time(value) -> datetime:
    """'2026-11-04T02:03:20Z' (ASF) or '2026-11-04T02:03:20.123456789' (HDF5, nanoseconds) -> aware UTC."""
    text = value.decode() if isinstance(value, bytes) else str(value)
    m = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.(\d+))?", text.strip())
    if m is None:
        raise ValueError(f"not a timestamp: {text!r}")
    micro = (m.group(3) or "0")[:6].ljust(6, "0")
    return datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}.{micro}").replace(tzinfo=timezone.utc)


def _iso(value) -> str:
    if isinstance(value, datetime):
        value = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, date):
        return f"{value.isoformat()}T00:00:00Z"
    return str(value)
