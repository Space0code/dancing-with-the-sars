"""Sentinel-1 history: small windows of NASA's OPERA RTC-S1 product, as a stack for sarwatch.change.

The product (verified facts and sources: kb/data-sources.md, section "OPERA RTC-S1: how to read it"): one product is
one Sentinel-1 burst on one date. Each has one Cloud-Optimized GeoTIFF per polarization (VV, VH: float32 gamma0
backscatter, linear power) and a uint8 mask (0 valid, 1 shadow, 2 layover, 3 both, 255 no data), 30 m pixels on a
UTM grid that is fixed per burst ID. So all dates of one burst stack without resampling.

Flow: search(bbox) lists products (ASF search API, no login) -> pick_burst() keeps one burst and one product per date
-> thin() spaces the dates out -> read_stack() reads only the window around bbox from each file (HTTP range
requests with an Earthdata token) into {pol: (time, y, x)}, the input of change.detect_changes.

Remote reads: ASF answers a file URL with redirects, [datapool.asf.alaska.edu ->] cumulus.asf.alaska.edu or
cumulus.asf.earthdatacloud.nasa.gov (checks the Earthdata token) -> a signed URL on AWS, valid about an hour. The
redirects are followed here by hand, sending the token only to ASF and Earthdata hosts (requests and curl drop it on
a host change anyway), and GDAL then range-reads the signed URL with no token: S3 refuses a second auth mechanism.
"""
from __future__ import annotations

import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import numpy as np

SEARCH_URL = "https://api.daac.asf.alaska.edu/services/search/param"
MAX_RESULTS = 2000      # the search API's cap per query
FIRST_ACQUISITION = datetime(2014, 4, 1, tzinfo=timezone.utc)  # Sentinel-1A launch; OPERA RTC-S1 starts April 2016
TOKEN_HOSTS = ("asf.alaska.edu", "earthdata.nasa.gov", "earthdatacloud.nasa.gov")  # the token goes only here
LOGIN_HOST = "urs.earthdata.nasa.gov"  # a redirect here means the token was missing or refused
MASK_VALID = 0          # mask value of a usable pixel; 1-3 (shadow / layover) and 255 (no data) become NaN
MASK_FILL = 255
HEADER_BYTES = 16384    # GDAL's first read of a remote file (header + tile index); counted in the byte estimate
GDAL_HTTP_OPTIONS = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",  # no directory listing next to the file
    "CPL_VSIL_CURL_USE_HEAD": "NO",              # S3 URLs are signed for GET only: a HEAD would be refused
    "GDAL_HTTP_MAX_RETRY": "4",
    "GDAL_HTTP_RETRY_DELAY": "2",
}

# Cost of the last read_stack call: files, dates, window shape, bytes (estimate: compressed tiles the window touches,
# plus HEADER_BYTES per remote file) and wall-clock seconds.
last_read_stats: dict = {}


@dataclass
class Scene:
    name: str          # product name without layer suffix, e.g. OPERA_L2_RTC-S1_T132-281622-IW2_<start>_<made>_S1A_30_v1.0
    burst_id: str      # e.g. "T132_281622_IW2": fixed footprint and grid
    start: datetime    # acquisition start, UTC
    track: int         # relative orbit
    direction: str     # "ASCENDING" | "DESCENDING" when the API gives it, else ""
    urls: dict         # "VV", "VH", "mask" (and "HH", "HV" where present) -> https URL or local path
    footprint: str = ""  # WKT polygon in lon/lat degrees, from the search API
    extra: dict = field(default_factory=dict)  # "produced" (YYYYMMDDTHHMMSSZ), "version" (e.g. "1.0")


def _ranked(scene: Scene) -> tuple:
    """Order among reprocessed copies of one burst and date: newest product version, then newest production."""
    version = tuple(int(p) for p in scene.extra.get("version", "0").split(".") if p.isdigit())
    return version, scene.extra.get("produced", "")


def _name_parts(name: str) -> dict:
    """Fields of OPERA_L2_RTC-S1_[BurstID]_[Start]_[Produced]_[Sensor]_[Spacing]_v[Version]."""
    parts = name.split("_")
    if len(parts) < 9 or parts[0] != "OPERA":
        return {}
    return {"burst_id": parts[3].replace("-", "_"), "start": parts[4], "produced": parts[5], "sensor": parts[6],
            "version": parts[8].lstrip("v")}


def scene_from_api(item: dict) -> Scene:
    """One result of the ASF search API (output=jsonlite) as a Scene."""
    name = item["granuleName"]
    opera = item.get("opera") or {}
    parts = _name_parts(name)
    urls = {}
    for url in [item.get("downloadUrl")] + list(opera.get("additionalUrls") or []):
        if url and url.startswith("http") and url.endswith(".tif"):
            stem = url.rsplit("/", 1)[-1][:-4]
            if stem.startswith(name + "_"):
                urls[stem[len(name) + 1:]] = url
    burst_id = opera.get("operaBurstID") or parts.get("burst_id", "")
    track = item.get("path")
    if track is None:
        track = int(burst_id[1:4]) if burst_id[1:4].isdigit() else 0  # "T132_..." -> 132
    return Scene(
        name=name, burst_id=burst_id,
        start=datetime.fromisoformat(item["startTime"].replace("Z", "+00:00")),
        track=int(track), direction=(item.get("flightDirection") or "").upper(), urls=urls,
        footprint=item.get("wkt") or "",
        extra={"produced": parts.get("produced", ""), "version": opera.get("productVersion") or parts.get("version", "")},
    )


def _bbox_wkt(bbox) -> str:
    w, s, e, n = bbox
    if w == e and s == n:
        return f"POINT({w} {s})"
    return f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"


def _utc(t) -> datetime:
    """date, datetime or ISO string -> aware UTC datetime (naive input is taken as UTC)."""
    if isinstance(t, str):
        t = datetime.fromisoformat(t.replace("Z", "+00:00"))
    elif not isinstance(t, datetime):
        t = datetime(t.year, t.month, t.day)
    return t.astimezone(timezone.utc) if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _session(trust_env: bool = True):
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    s = requests.Session()
    s.trust_env = trust_env
    retry = Retry(total=4, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",),
                  redirect=0, raise_on_redirect=False, raise_on_status=False)
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


def _search_span(session, bbox, t0: datetime, t1: datetime, timeout: float) -> list:
    """API results for acquisitions in [t0, t1]. The API refuses (HTTP 400) a query that would return more than
    MAX_RESULTS unless maxResults is set, so a span that fills maxResults is split in two and asked again."""
    params = {"dataset": "OPERA-S1", "processingLevel": "RTC", "intersectsWith": _bbox_wkt(bbox), "output": "jsonlite",
              "start": t0.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": t1.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "maxResults": MAX_RESULTS}
    r = session.get(SEARCH_URL, params=params, timeout=timeout)  # gzip: ~0.3 KB per product on the wire
    if r.status_code >= 400:
        raise RuntimeError(f"ASF search failed, HTTP {r.status_code}: {r.text[:300]}")
    results = r.json().get("results", [])
    if len(results) >= MAX_RESULTS and t1 - t0 > timedelta(days=1):
        mid = t0 + (t1 - t0) / 2
        return _search_span(session, bbox, t0, mid, timeout) + _search_span(session, bbox, mid, t1, timeout)
    return results


def search(bbox, start=None, end=None, timeout: float = 180) -> list:
    """All RTC-S1 products whose footprint meets bbox (west, south, east, north degrees), time-sorted. No login.

    Includes every burst and track that touches bbox, and reprocessed copies of the same burst and date: pick_burst
    sorts that out. start / end: date, datetime or ISO string (UTC) on the acquisition time; default: all.
    Asks one year at a time, so long series stay under the API's result cap.
    """
    t0 = _utc(start) if start is not None else FIRST_ACQUISITION
    t1 = _utc(end) if end is not None else datetime.now(timezone.utc)
    items = {}
    with _session() as s:
        while t0 < t1:
            t_next = min(t1, datetime(t0.year + 1, 1, 1, tzinfo=timezone.utc))
            for item in _search_span(s, bbox, t0, t_next, timeout):
                items[item["granuleName"]] = item  # a product on a span edge comes back twice
            t0 = t_next
    return sorted((scene_from_api(item) for item in items.values()), key=lambda sc: sc.start)


def _one_per_date(scenes) -> list:
    best = {}
    for sc in scenes:
        key = sc.start.date()
        if key not in best or _ranked(sc) > _ranked(best[key]):
            best[key] = sc
    return sorted(best.values(), key=lambda sc: sc.start)


def pick_burst(scenes, bbox) -> list:
    """The scenes of one burst only (one fixed grid), one per date, time-sorted.

    Prefers bursts whose footprint contains the whole bbox, then (among bursts that do not) the larger share of bbox
    covered, then the most dates. Among reprocessed copies of one date, the newest product wins.
    """
    from shapely import wkt
    from shapely.geometry import box

    area = box(*bbox)
    by_burst = {}
    for sc in scenes:
        by_burst.setdefault(sc.burst_id, []).append(sc)

    def score(item):
        burst_id, group = item
        dated = _one_per_date(group)
        covers = []
        for sc in dated:
            try:
                shape = wkt.loads(sc.footprint)
            except Exception:  # no or bad footprint: counts as not covering
                covers.append(0.0)
                continue
            covers.append(1.0 if shape.covers(area) else
                          (shape.intersection(area).area / area.area if area.area > 0 else 0.0))
        cover = float(np.median(covers)) if covers else 0.0
        return (cover >= 1.0, round(cover, 2), len(dated), burst_id)

    if not by_burst:
        return []
    best = max(by_burst.items(), key=score)
    return _one_per_date(best[1])


def thin(scenes, max_dates=None, min_gap_days=None) -> list:
    """Thin a long time-sorted series: at least min_gap_days between kept dates, then at most max_dates, evenly
    spread in time (the scene nearest each of max_dates evenly spaced instants). The first scene is always kept,
    and the last one too when max_dates applies.
    """
    kept = sorted(scenes, key=lambda sc: sc.start)
    if min_gap_days and kept:
        gap, out = timedelta(days=min_gap_days), [kept[0]]
        for sc in kept[1:]:
            if sc.start - out[-1].start >= gap:
                out.append(sc)
        kept = out
    if max_dates is not None and len(kept) > max_dates:
        if max_dates <= 0:
            return []
        t = np.array([sc.start.timestamp() for sc in kept])
        targets = np.linspace(t[0], t[-1], max_dates)
        idx = sorted({int(np.abs(t - x).argmin()) for x in targets})
        kept = [kept[i] for i in idx]
    return kept


# ---------------------------------------------------------------- reading

_local = threading.local()


def _thread_session():
    if not hasattr(_local, "session"):
        _local.session = _session(trust_env=False)  # else a ~/.netrc entry would replace the bearer header
    return _local.session


def _token_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in TOKEN_HOSTS)


def _refusal(r, url: str) -> str:
    """Message for a 401 / 403 from the archive, with Earthdata's reason and fix when the body is JSON, e.g.
    {"error": "invalid_token", "error_description": "EULA Acceptance Failure", "resolution_url": "https://urs..."}.
    The URL never carries the token (it travels in a header), so the message cannot leak it."""
    try:
        body = r.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return f"HTTP {r.status_code} for {url}: token refused or no access"
    reason = body.get("error_description") or body.get("error") or "token refused or no access"
    fix = body.get("resolution_url")
    todo = f": open {fix} while logged in to Earthdata and approve, then retry" if fix else ""
    return f"{reason}{todo} (HTTP {r.status_code} for {url})"


def resolve_url(url: str, token: str, max_hops: int = 6) -> tuple:
    """Follow ASF's redirects to the URL GDAL should range-read. Returns (url, headers GDAL must send).

    The token goes only to TOKEN_HOSTS. The usual end is a redirect to a signed AWS URL (valid about an hour), read
    with no headers. A redirect to the Earthdata login page means the token was refused. Resolve with GET, not HEAD:
    ASF signs the URL for the method it was asked with.
    """
    for _ in range(max_hops):
        headers = {"Authorization": f"Bearer {token}"} if _token_host(url) else {}
        with _thread_session().get(url, headers={**headers, "Range": "bytes=0-0"}, allow_redirects=False,
                                   stream=True, timeout=60) as r:
            if r.is_redirect:
                nxt = urljoin(url, r.headers["Location"])
                host = (urlparse(nxt).hostname or "").lower()
                if host == LOGIN_HOST or host.endswith("." + LOGIN_HOST):
                    raise PermissionError(f"Earthdata refused the token (redirected to login) for {url}. "
                                          "Check EARTHDATA_TOKEN: a user token from urs.earthdata.nasa.gov, not expired.")
                if not _token_host(nxt):
                    return nxt, {}
                url = nxt
                continue
            if r.status_code in (200, 206):
                return url, headers  # served directly: GDAL must send the token itself
            if r.status_code in (401, 403):
                raise PermissionError(_refusal(r, url))
            r.raise_for_status()
            raise RuntimeError(f"unexpected HTTP {r.status_code} for {url}")
    raise RuntimeError(f"more than {max_hops} redirects for {url}")


def _bounds_window(ds, bbox) -> tuple:
    """Pixel window (row0, col0, rows, cols) of ds that covers the lon/lat bbox, grown outward to whole pixels."""
    from rasterio.warp import transform_bounds

    xmin, ymin, xmax, ymax = transform_bounds("EPSG:4326", ds.crs, *bbox, densify_pts=21)
    t = ds.transform
    c0, c1 = sorted(((xmin - t.c) / t.a, (xmax - t.c) / t.a))
    r0, r1 = sorted(((ymax - t.f) / t.e, (ymin - t.f) / t.e))
    eps = 1e-6  # a bbox edge exactly on a pixel edge must not add a pixel
    col0, row0 = math.floor(c0 + eps), math.floor(r0 + eps)
    col1, row1 = math.ceil(c1 - eps), math.ceil(r1 - eps)
    return row0, col0, max(row1 - row0, 1), max(col1 - col0, 1)


def _grid(ds) -> dict:
    t = ds.transform
    return {"epsg": ds.crs.to_epsg() if ds.crs else None, "a": t.a, "b": t.b, "c": t.c, "d": t.d, "e": t.e, "f": t.f}


def _window_in(ds, ref: dict, label: str) -> tuple:
    """(row0, col0) in ds of the reference window's top-left corner; ValueError unless ds lies on the same grid."""
    g = _grid(ds)
    if g["epsg"] != ref["epsg"]:
        raise ValueError(f"grid mismatch in {label}: EPSG {g['epsg']} vs {ref['epsg']}")
    if abs(g["b"]) > 1e-9 or abs(g["d"]) > 1e-9 or abs(g["a"] - ref["a"]) > 1e-6 or abs(g["e"] - ref["e"]) > 1e-6:
        raise ValueError(f"grid mismatch in {label}: pixel size or rotation ({g['a']}, {g['e']}) "
                         f"vs ({ref['a']}, {ref['e']})")
    col = (ref["x0"] - g["c"]) / g["a"]
    row = (ref["y0"] - g["f"]) / g["e"]
    if abs(col - round(col)) > 1e-3 or abs(row - round(row)) > 1e-3:
        raise ValueError(f"grid mismatch in {label}: pixel edges offset by ({col - round(col):.3f}, "
                         f"{row - round(row):.3f}) pixels from the first date")
    return int(round(row)), int(round(col))


def _tile_bytes(ds, r0, c0, r1, c1) -> int:
    """Compressed size of the band-1 tiles that rows r0:r1, cols c0:c1 touch (0 when the driver cannot tell)."""
    bh, bw = ds.block_shapes[0]
    total = 0
    for by in range(r0 // bh, (r1 - 1) // bh + 1):
        for bx in range(c0 // bw, (c1 - 1) // bw + 1):
            size = ds.get_tag_item(f"BLOCK_SIZE_{bx}_{by}", "TIFF", bidx=1)
            total += int(size) if size else 0
    return total


def _remote(url: str) -> bool:
    return url.startswith(("http://", "https://"))


def _gdal_source(url: str, token) -> tuple:
    """(path for rasterio.open, GDAL options): a local path as it is, a remote URL resolved for /vsicurl/."""
    if not _remote(url):
        return url, {}
    target, headers = resolve_url(url, token)
    opts = dict(GDAL_HTTP_OPTIONS)
    if headers:
        opts["GDAL_HTTP_HEADERS"] = "\r\n".join(f"{k}: {v}" for k, v in headers.items())
    return "/vsicurl/" + target, opts


def _read_one(url: str, ref: dict, label: str, token, is_mask: bool) -> tuple:
    """Read the reference window from one file. Returns (array, bytes estimate). Outside the file: fill value."""
    import rasterio
    from rasterio.windows import Window

    path, opts = _gdal_source(url, token)
    rows, cols = ref["rows"], ref["cols"]
    out = np.full((rows, cols), MASK_FILL if is_mask else np.nan, dtype=np.uint8 if is_mask else np.float32)
    with rasterio.Env(**opts), rasterio.open(path) as ds:
        row0, col0 = _window_in(ds, ref, label)
        r0, c0 = max(row0, 0), max(col0, 0)
        r1, c1 = min(row0 + rows, ds.height), min(col0 + cols, ds.width)
        nbytes = HEADER_BYTES if _remote(url) else 0
        if r1 > r0 and c1 > c0:
            block = ds.read(1, window=Window(c0, r0, c1 - c0, r1 - r0))
            dst = out[r0 - row0:r1 - row0, c0 - col0:c1 - col0]
            if is_mask:
                dst[...] = block
            else:
                vals = block.astype(np.float32)
                bad = ~np.isfinite(vals) | (vals <= 0)
                if ds.nodata is not None and np.isfinite(ds.nodata):
                    bad |= vals == ds.nodata
                vals[bad] = np.nan
                dst[...] = vals
            nbytes += _tile_bytes(ds, r0, c0, r1, c1)
    return out, nbytes


def read_stack(scenes, bbox, pols=("VV", "VH"), token=None, workers: int = 8) -> tuple:
    """Read the window around bbox from every scene: (stack, dates, transform, epsg).

    stack: pol -> (time, y, x) float32 gamma0 linear power, NaN where no data, non-positive, or masked (any mask value
    but MASK_VALID). dates: list[date] (UTC acquisition day). transform: (a, b, c, d, e, f) of the window, pixel-corner
    convention. epsg: the burst's UTM zone. The window covers bbox grown outward to whole pixels; parts outside the
    burst's raster are NaN. All files must sit on the first file's grid (same EPSG, pixel size and pixel edges),
    else ValueError. Remote files need an Earthdata token (token=None reads os.environ["EARTHDATA_TOKEN"]); local
    paths in Scene.urls need none. The cost lands in the module-level dict last_read_stats.
    """
    import rasterio

    t_start = time.perf_counter()
    scenes = sorted(scenes, key=lambda sc: sc.start)
    if not scenes:
        raise ValueError("no scenes to read")
    pols = tuple(pols)
    for sc in scenes:
        missing = [p for p in pols if p not in sc.urls]
        if missing:
            raise ValueError(f"{sc.name} has no {missing} layer (has {sorted(sc.urls)})")
    jobs = [(i, p, sc.urls[p]) for i, sc in enumerate(scenes) for p in pols]
    jobs += [(i, "mask", sc.urls["mask"]) for i, sc in enumerate(scenes) if "mask" in sc.urls]
    if any(_remote(url) for _, _, url in jobs):
        token = token or os.environ.get("EARTHDATA_TOKEN")
        if not token:
            raise RuntimeError("remote OPERA files need an Earthdata user token: set EARTHDATA_TOKEN "
                               "(urs.earthdata.nasa.gov -> Generate Token) or pass token=")

    # The first file fixes the grid and the window.
    path, opts = _gdal_source(scenes[0].urls[pols[0]], token)
    with rasterio.Env(**opts), rasterio.open(path) as ds:
        row0, col0, rows, cols = _bounds_window(ds, bbox)
        if row0 >= ds.height or col0 >= ds.width or row0 + rows <= 0 or col0 + cols <= 0:
            raise ValueError(f"bbox {bbox} lies outside burst {scenes[0].burst_id} ({scenes[0].name})")
        ref = _grid(ds)
        t = ds.transform
    ref.update(x0=t.c + col0 * t.a, y0=t.f + row0 * t.e, rows=rows, cols=cols)

    def run(job):
        i, layer, url = job
        return job, _read_one(url, ref, f"{scenes[i].name} {layer}", token, layer == "mask")

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(run, jobs))

    stack = {p: np.empty((len(scenes), rows, cols), dtype=np.float32) for p in pols}
    masks, nbytes = {}, 0
    for (i, layer, _), (arr, nb) in results:
        nbytes += nb
        if layer == "mask":
            masks[i] = arr
        else:
            stack[layer][i] = arr
    for i, m in masks.items():
        bad = m != MASK_VALID
        for p in pols:
            stack[p][i][bad] = np.nan

    transform = (ref["a"], 0.0, ref["x0"], 0.0, ref["e"], ref["y0"])
    seconds = time.perf_counter() - t_start
    last_read_stats.clear()
    last_read_stats.update(files=len(jobs), dates=len(scenes), shape=(rows, cols), bytes=nbytes,
                           bytes_per_date=nbytes / len(scenes), seconds=seconds, seconds_per_date=seconds / len(scenes),
                           bytes_note="estimate: compressed tiles the window touches + header per remote file")
    return stack, [sc.start.date() for sc in scenes], transform, ref["epsg"]
