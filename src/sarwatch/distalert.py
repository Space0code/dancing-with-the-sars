"""Optical vegetation-loss alerts: small windows of NASA's OPERA DIST-ALERT-HLS product (and its annual summary).

The product (verified facts, sources and measured costs: kb/data-sources.md, section "OPERA DIST-ALERT-HLS: how to
read it"): Landsat 8/9 + Sentinel-2 (HLS) scenes, one granule per MGRS tile and scene, 30 m pixels on the tile's fixed
UTM grid (3660 x 3660). Each layer is one Cloud-Optimized GeoTIFF. Each granule carries the running alert state of the
whole tile, so the newest granule holds every alert of roughly the last year:
  VEG-DIST-STATUS  uint8: 0 none · 1 first <50% · 2 provisional <50% · 3 confirmed <50% · 4 first >=50% ·
                   5 provisional >=50% · 6 confirmed >=50% · 7 confirmed <50% finished · 8 confirmed >=50% finished ·
                   255 no data (annual product: 9 / 10 = confirmed, first seen the previous year)
  VEG-DIST-DATE    int16: day of the first loss anomaly of the pixel's most recent alert, counted from 2020-12-31
                   (1 = 2021-01-01); 0 no alert in the last year; -1 no data
"<50%" / ">=50%": the largest vegetation-cover loss seen (VEG-ANOM-MAX, percent). A "finished" alert is overwritten
when a new one starts on the same pixel, so its date then moves: combine() keeps the earliest confirmed date over
several snapshots.

Flow: search(bbox, start, end) lists granules (NASA CMR, no login) -> pick_tile() keeps one tile that covers bbox ->
latest() / month_ends() choose granules -> read_window() reads the window around bbox from each layer (HTTP range
requests with an Earthdata token; LP DAAC answers 303 to a signed CloudFront URL, see s1.resolve_url) -> Alerts ->
combine() over snapshots -> hectares_by_month().
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import numpy as np

from . import s1

CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
ALERT = "OPERA_L3_DIST-ALERT-HLS_V1"   # one granule per tile and HLS scene, from 2023-01-01
ANNUAL = "OPERA_L3_DIST-ANN-HLS_V1"    # one granule per tile and year (confirmed alerts only), from 2023
PAGE_SIZE = 2000                       # CMR's maximum page size
FIRST_DATA = datetime(2023, 1, 1, tzinfo=timezone.utc)
EPOCH = np.datetime64("2020-12-31", "D")  # VEG-DIST-DATE counts days from here
STATUS, DATE = "VEG-DIST-STATUS", "VEG-DIST-DATE"
STATUS_NODATA = 255
FIRST = (1, 4)                         # one anomalous observation so far
PROVISIONAL = (2, 5)                   # two or more, confidence not yet high
CONFIRMED = (3, 6, 7, 8, 9, 10)        # high confidence (7, 8 finished; 9, 10 only in the annual product)
STRONG = (4, 5, 6, 8, 10)              # largest loss >= 50% of the vegetation cover
CLASSES = {"confirmed": CONFIRMED, "provisional": PROVISIONAL, "first": FIRST}

# Cost of the last read_window call: files, window shape, bytes (estimate: compressed tiles the window touches plus
# s1.HEADER_BYTES per remote file) and wall-clock seconds.
last_read_stats: dict = {}


@dataclass
class Granule:
    name: str          # e.g. OPERA_L3_DIST-ALERT-HLS_T35WMM_20261023T100041Z_20261025T065842Z_S2A_30_v1
    tile: str          # MGRS tile, e.g. "35WMM": one fixed UTM grid
    start: datetime    # acquisition time (annual product: start of its year's data), UTC
    sensor: str        # L8 | L9 | S2A | S2B | S2C; "" for the annual product
    urls: dict         # layer name ("VEG-DIST-STATUS", ...) -> https URL or local path
    footprint: str = ""  # WKT polygon in lon/lat degrees
    extra: dict = field(default_factory=dict)  # "produced" (YYYYMMDDTHHMMSSZ), "epsg", "coverage" / "cloud" (%)


@dataclass
class Alerts:
    """Alert state of one window. status / first_date / layers share one shape; transform is pixel-corner."""
    status: np.ndarray      # uint8 VEG-DIST-STATUS
    first_date: np.ndarray  # datetime64[D] from VEG-DIST-DATE; NaT where no alert or no data
    transform: tuple        # (a, b, c, d, e, f) of the window
    epsg: int
    granule: str            # source granule; "combined: <first> .. <last>" after combine()
    acquired: date          # acquisition date of the (newest) source granule
    layers: dict = field(default_factory=dict)  # every layer read, raw: name -> array

    @property
    def pixel_ha(self) -> float:
        return abs(self.transform[0] * self.transform[4]) / 10_000


def _name_parts(name: str) -> dict:
    """Fields of OPERA_L3_DIST-ALERT-HLS_T<tile>_<acq>_<produced>_<sensor>_30_v1 and
    OPERA_L3_DIST-ANN-HLS_T<tile>_<year>_<produced>_30_v1."""
    parts = name.split("_")
    if len(parts) < 7 or parts[0] != "OPERA" or not parts[3].startswith("T"):
        return {}
    out = {"tile": parts[3][1:], "produced": parts[5]}
    if "ANN" in parts[2]:
        out.update(year=parts[4], sensor="")
    else:
        out.update(acquired=parts[4], sensor=parts[6] if len(parts) > 6 else "")
    return out


def _attrs(umm: dict) -> dict:
    return {a["Name"]: (a.get("Values") or [""])[0] for a in umm.get("AdditionalAttributes", [])}


def _footprint(umm: dict) -> str:
    try:
        polygons = umm["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["GPolygons"]
    except KeyError:
        return ""
    rings = []
    for poly in polygons:
        pts = poly["Boundary"]["Points"]
        rings.append("((" + ",".join(f"{p['Longitude']} {p['Latitude']}" for p in pts) + "))")
    if len(rings) == 1:
        return "POLYGON " + rings[0]
    return "MULTIPOLYGON (" + ",".join(f"({r[1:-1]})" for r in rings) + ")"


def granule_from_umm(item: dict) -> Granule:
    """One item of a CMR granules.umm_json answer as a Granule (https 'GET DATA' links only)."""
    umm = item.get("umm", item)
    name = umm["GranuleUR"]
    parts = _name_parts(name)
    attrs = _attrs(umm)
    urls = {}
    for link in umm.get("RelatedUrls", []):
        url = link.get("URL", "")
        if link.get("Type") == "GET DATA" and url.startswith("http") and url.endswith(".tif"):
            stem = url.rsplit("/", 1)[-1][:-4]
            if stem.startswith(name + "_"):
                urls[stem[len(name) + 1:]] = url
    t = umm["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"]
    epsg = attrs.get("HORIZONTAL_CS_CODE", "")
    extra = {"produced": parts.get("produced", ""), "epsg": int(epsg.split(":")[1]) if ":" in epsg else None}
    if attrs.get("SPATIAL_COVERAGE", "").isdigit():
        extra["coverage"] = int(attrs["SPATIAL_COVERAGE"])
    if umm.get("CloudCover") is not None:
        extra["cloud"] = umm["CloudCover"]
    return Granule(name=name, tile=attrs.get("MGRS_TILE_ID") or parts.get("tile", ""),
                   start=datetime.fromisoformat(t.replace("Z", "+00:00")), sensor=parts.get("sensor", ""),
                   urls=urls, footprint=_footprint(umm), extra=extra)


def search(bbox, start=None, end=None, product: str = ALERT, timeout: float = 120) -> list:
    """All granules of product (ALERT or ANNUAL) whose footprint meets bbox (west, south, east, north degrees),
    acquired in [start, end], time-sorted. NASA CMR, no login; pages of PAGE_SIZE with CMR-Search-After.
    start / end: date, datetime or ISO string (UTC); default: from 2023 to now."""
    t0 = s1._utc(start) if start is not None else FIRST_DATA
    t1 = s1._utc(end) if end is not None else datetime.now(timezone.utc)
    params = {"short_name": product, "bounding_box": ",".join(str(v) for v in bbox),
              "temporal": f"{t0:%Y-%m-%dT%H:%M:%SZ},{t1:%Y-%m-%dT%H:%M:%SZ}", "page_size": PAGE_SIZE,
              "sort_key": "start_date"}
    items, after = {}, None
    with s1._session() as s:
        while True:
            headers = {"CMR-Search-After": after} if after else {}
            r = s.get(CMR_URL, params=params, headers=headers, timeout=timeout)
            if r.status_code >= 400:
                raise RuntimeError(f"CMR search failed, HTTP {r.status_code}: {r.text[:300]}")
            page = r.json().get("items", [])
            for item in page:
                items[item["umm"]["GranuleUR"]] = item
            after = r.headers.get("CMR-Search-After")
            if len(page) < PAGE_SIZE or not after:
                break
    return sorted((granule_from_umm(it) for it in items.values()), key=lambda g: (g.start, g.extra["produced"]))


def pick_tile(granules, bbox) -> str:
    """The tile to read bbox from: one whose footprint covers all of bbox, else the largest cover; ties: more
    granules, then the tile name. "" when there are no granules."""
    from shapely import wkt
    from shapely.geometry import box

    area = box(*bbox)
    by_tile = {}
    for g in granules:
        by_tile.setdefault(g.tile, []).append(g)

    def cover(g) -> float:
        try:
            shape = wkt.loads(g.footprint)
        except Exception:  # no or bad footprint: counts as not covering
            return 0.0
        if shape.covers(area):
            return 1.0
        return shape.intersection(area).area / area.area if area.area > 0 else 0.0

    def score(item):
        tile, group = item
        c = float(np.median([cover(g) for g in group]))
        return (c >= 1.0, round(c, 2), len(group), tile)

    return max(by_tile.items(), key=score)[0] if by_tile else ""


def _rank(g: Granule) -> tuple:
    return g.start, g.extra.get("produced", "")


def latest(granules, tile=None, before=None):
    """The newest granule (of tile, acquired before `before` if given): it holds the tile's running alert state.
    Ties (two scenes the same minute, or reprocessed copies): the newest production wins. None if there is none."""
    t_max = s1._utc(before) if before is not None else None
    pool = [g for g in granules if (tile is None or g.tile == tile) and (t_max is None or g.start < t_max)]
    return max(pool, key=_rank) if pool else None


def month_ends(granules, tile=None) -> list:
    """The newest granule of each calendar month (of tile), time-sorted: monthly snapshots of the alert state."""
    best = {}
    for g in granules:
        if tile is not None and g.tile != tile:
            continue
        key = (g.start.year, g.start.month)
        if key not in best or _rank(g) > _rank(best[key]):
            best[key] = g
    return sorted(best.values(), key=_rank)


def days_to_dates(days) -> np.ndarray:
    """VEG-DIST-DATE day numbers -> datetime64[D]; NaT where <= 0 (no alert, -1 no data)."""
    days = np.asarray(days)
    out = EPOCH + np.where(days > 0, days, 0).astype("timedelta64[D]")
    return np.where(days > 0, out, np.datetime64("NaT"))


def _token(token):
    if token:
        return token
    from .pipeline import load_token  # $EARTHDATA_TOKEN, else EARTHDATA_TOKEN / EARTH_DATA_TOKEN in the repo's .env

    token = load_token()
    if not token:
        raise RuntimeError("remote OPERA files need an Earthdata user token: set EARTHDATA_TOKEN "
                           "(urs.earthdata.nasa.gov -> Generate Token), put it in the repo's .env, or pass token=")
    return token


def _read_layer(url: str, bbox, token) -> tuple:
    """(array, grid dict, bytes estimate) of the window around bbox in one layer file."""
    import rasterio
    from rasterio.windows import Window

    path, opts = s1._gdal_source(url, token)
    with rasterio.Env(**opts), rasterio.open(path) as ds:
        row0, col0, rows, cols = s1._bounds_window(ds, bbox)
        if row0 >= ds.height or col0 >= ds.width or row0 + rows <= 0 or col0 + cols <= 0:
            raise ValueError(f"bbox {bbox} lies outside {url.rsplit('/', 1)[-1]}")
        fill = ds.nodata if ds.nodata is not None else 0
        out = np.full((rows, cols), fill, dtype=ds.dtypes[0])
        r0, c0 = max(row0, 0), max(col0, 0)
        r1, c1 = min(row0 + rows, ds.height), min(col0 + cols, ds.width)
        out[r0 - row0:r1 - row0, c0 - col0:c1 - col0] = ds.read(1, window=Window(c0, r0, c1 - c0, r1 - r0))
        grid = s1._grid(ds)
        grid.update(x0=grid["c"] + col0 * grid["a"], y0=grid["f"] + row0 * grid["e"], rows=rows, cols=cols)
        nbytes = (s1.HEADER_BYTES if s1._remote(url) else 0) + s1._tile_bytes(ds, r0, c0, r1, c1)
    return out, grid, nbytes


def read_window(granule: Granule, bbox, layers=(STATUS, DATE), token=None, workers: int = 4) -> Alerts:
    """Read the window around bbox (lon/lat degrees, grown outward to whole pixels) from each layer of one granule.

    Parts of the window outside the tile hold the layer's nodata value (status 255, date NaT). Remote files need an
    Earthdata token (token=None: $EARTHDATA_TOKEN or the repo's .env); local paths in Granule.urls need none. The
    token goes only to Earthdata hosts, never to the signed CloudFront URL. Cost: module-level last_read_stats.
    """
    t_start = time.perf_counter()
    layers = tuple(dict.fromkeys((STATUS, DATE) + tuple(layers)))
    missing = [name for name in layers if name not in granule.urls]
    if missing:
        raise ValueError(f"{granule.name} has no {missing} layer (has {sorted(granule.urls)})")
    if any(s1._remote(granule.urls[name]) for name in layers):
        token = _token(token)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = dict(zip(layers, pool.map(lambda name: _read_layer(granule.urls[name], bbox, token), layers)))

    ref = results[STATUS][1]
    for name, (_, grid, _) in results.items():
        if grid["epsg"] != ref["epsg"] or any(abs(grid[k] - ref[k]) > 1e-6 for k in ("a", "e", "x0", "y0")) \
                or (grid["rows"], grid["cols"]) != (ref["rows"], ref["cols"]):
            raise ValueError(f"grid mismatch in {granule.name}: {name} vs {STATUS}")
    raw = {name: arr for name, (arr, _, _) in results.items()}
    nbytes = sum(nb for _, _, nb in results.values())
    seconds = time.perf_counter() - t_start
    last_read_stats.clear()
    last_read_stats.update(files=len(layers), shape=(ref["rows"], ref["cols"]), bytes=nbytes, seconds=seconds,
                           bytes_note="estimate: compressed tiles the window touches + header per remote file")
    return Alerts(status=raw[STATUS], first_date=days_to_dates(raw[DATE]),
                  transform=(ref["a"], 0.0, ref["x0"], 0.0, ref["e"], ref["y0"]), epsg=ref["epsg"],
                  granule=granule.name, acquired=granule.start.date(), layers=raw)


def combine(snapshots) -> Alerts:
    """Merge alert states of one window read at several times (any order; all on one grid) into one.

    A pixel confirmed in any snapshot keeps its earliest confirmed first-detection date and that snapshot's status,
    so a finished alert later overwritten by a new one keeps its original date. Every other pixel takes the newest
    snapshot's status and date (still-open first / provisional alerts; alerts that were dropped are gone).
    """
    snaps = sorted(snapshots, key=lambda a: a.acquired)
    if not snaps:
        raise ValueError("no snapshots to combine")
    newest = snaps[-1]
    for a in snaps:
        if a.epsg != newest.epsg or a.status.shape != newest.status.shape \
                or not np.allclose(a.transform, newest.transform):
            raise ValueError(f"grid mismatch: {a.granule} vs {newest.granule}")
    status = newest.status.copy()
    first = newest.first_date.copy()
    best = np.full(status.shape, np.datetime64("NaT"), dtype="datetime64[D]")
    best_status = np.zeros(status.shape, dtype=status.dtype)
    for a in snaps:
        conf = np.isin(a.status, CONFIRMED) & ~np.isnat(a.first_date)
        earlier = conf & (np.isnat(best) | (a.first_date < best))
        best[earlier] = a.first_date[earlier]
        best_status[earlier] = a.status[earlier]
    hit = ~np.isnat(best)
    first[hit] = best[hit]
    status[hit] = best_status[hit]
    return Alerts(status=status, first_date=first, transform=newest.transform, epsg=newest.epsg,
                  granule=f"combined: {snaps[0].granule} .. {newest.granule}", acquired=newest.acquired,
                  layers={})


def circle_mask(alerts: Alerts, lon: float, lat: float, radius_m: float) -> np.ndarray:
    """True for pixels whose centre lies within radius_m metres of (lon, lat), measured on the window's grid."""
    from rasterio.warp import transform as warp_transform

    xs, ys = warp_transform("EPSG:4326", f"EPSG:{alerts.epsg}", [lon], [lat])
    a, _, c, _, e, f = alerts.transform
    rows, cols = alerts.status.shape
    x = c + (np.arange(cols) + 0.5) * a
    y = f + (np.arange(rows) + 0.5) * e
    return (x[None, :] - xs[0]) ** 2 + (y[:, None] - ys[0]) ** 2 <= radius_m ** 2


def hectares_by_month(alerts: Alerts, region=None, strong_only: bool = False) -> dict:
    """{"YYYY-MM": {"confirmed": ha, "provisional": ha, "first": ha}} by month of first detection, time-sorted.

    region: optional bool mask of the window (e.g. circle_mask); strong_only: only alerts whose largest loss was
    >= 50% of the vegetation cover. Months with no alert are left out.
    """
    ok = ~np.isnat(alerts.first_date)
    if region is not None:
        ok &= region
    if strong_only:
        ok &= np.isin(alerts.status, STRONG)
    months = alerts.first_date.astype("datetime64[M]")
    out = {}
    for m in np.unique(months[ok]):
        sel = ok & (months == m)
        out[str(m)] = {name: float(np.isin(alerts.status[sel], codes).sum() * alerts.pixel_ha)
                       for name, codes in CLASSES.items()}
    return out
