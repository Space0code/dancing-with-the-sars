"""Colour satellite photos: small windows of NASA's HLS (Harmonized Landsat Sentinel-2) surface reflectance, 30 m.

Same archive and access as distalert.py (NASA LP DAAC; search through NASA CMR without login; window reads of
cloud-optimized GeoTIFFs with the Earthdata bearer token, which never goes to the signed redirect host).

Products (version 2.0): HLSS30 (Sentinel-2) and HLSL30 (Landsat 8/9). One granule per MGRS tile and scene, one COG
per band on the tile's UTM grid. Verified on the granule file lists in CMR: both products name the visible bands
B02 (blue), B03 (green), B04 (red) (they differ in the near-infrared: S30 B08/B8A, L30 B05), and both carry `Fmask`.
Values are reflectance scaled by 10000 (int16, -9999 = no data).

Fmask (uint8, bit flags, 255 = no data): bit 0 cirrus · 1 cloud · 2 adjacent to cloud / shadow · 3 cloud shadow ·
4 snow / ice · 5 water · 6-7 aerosol level. "Clear" here = bits 1, 2, 3, 4 all off and the pixel has data.

Flow: search() -> pick_tile() -> clear_granules() (reads Fmask only) -> read_rgb() for the clear ones.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import numpy as np

from . import distalert, s1

log = logging.getLogger(__name__)

CMR_VERSION = "2.0"
PRODUCTS = ("HLSS30", "HLSL30")
BANDS = {"red": "B04", "green": "B03", "blue": "B02"}
FMASK = "Fmask"
FMASK_NODATA = 255
BAD_BITS = (1, 2, 3, 4)          # cloud, adjacent to cloud / shadow, cloud shadow, snow / ice
NODATA = -9999
SCALE = 10000.0                  # reflectance = value / SCALE


def granule_from_umm(item: dict) -> distalert.Granule:
    """One CMR umm_json item as a Granule: name HLS.<S30|L30>.T<tile>.<YYYYDDDThhmmss>.v2.0, urls by band name."""
    umm = item.get("umm", item)
    name = umm["GranuleUR"]
    parts = name.split(".")
    urls = {}
    for link in umm.get("RelatedUrls", []):
        url = link.get("URL", "")
        if link.get("Type") == "GET DATA" and url.startswith("http") and url.endswith(".tif"):
            stem = url.rsplit("/", 1)[-1][:-4]
            if stem.startswith(name + "."):
                urls[stem[len(name) + 1:]] = url
    t = umm["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"]
    return distalert.Granule(
        name=name, tile=parts[2][1:] if len(parts) > 2 else "",
        start=datetime.fromisoformat(t.replace("Z", "+00:00")), sensor=parts[1] if len(parts) > 1 else "",
        urls=urls, footprint=distalert._footprint(umm),
        extra={"produced": "", "platform": next((x.get("ShortName", "") for x in umm.get("Platforms", [])), "")})


def search(bbox, start, end, products=PRODUCTS, timeout: float = 120) -> list:
    """Granules of the HLS products meeting bbox (west, south, east, north) acquired in [start, end], time-sorted.
    Returns distalert.Granule objects (name, tile, start, urls by band name, footprint); sensor is S30 or L30."""
    t0, t1 = s1._utc(start), s1._utc(end)
    out = {}
    with s1._session() as s:
        for product in products:
            params = {"short_name": product, "version": CMR_VERSION, "bounding_box": ",".join(str(v) for v in bbox),
                      "temporal": f"{t0:%Y-%m-%dT%H:%M:%SZ},{t1:%Y-%m-%dT%H:%M:%SZ}",
                      "page_size": distalert.PAGE_SIZE, "sort_key": "start_date"}
            after = None
            while True:
                headers = {"CMR-Search-After": after} if after else {}
                r = s.get(distalert.CMR_URL, params=params, headers=headers, timeout=timeout)
                if r.status_code >= 400:
                    raise RuntimeError(f"CMR search failed, HTTP {r.status_code}: {r.text[:300]}")
                page = r.json().get("items", [])
                for item in page:
                    g = granule_from_umm(item)
                    out[g.name] = g
                after = r.headers.get("CMR-Search-After")
                if len(page) < distalert.PAGE_SIZE or not after:
                    break
    return sorted(out.values(), key=lambda g: (g.start, g.name))


def pick_tile(granules, bbox) -> str:
    """The MGRS tile to read bbox from (one that covers it, else the best cover): see distalert.pick_tile."""
    return distalert.pick_tile(granules, bbox)


def clear_mask(fmask: np.ndarray) -> np.ndarray:
    """True where the pixel has data and no cloud, cloud edge, cloud shadow or snow / ice."""
    bad = np.zeros(fmask.shape, bool)
    for bit in BAD_BITS:
        bad |= ((fmask >> bit) & 1) == 1
    return (fmask != FMASK_NODATA) & ~bad


def clear_fraction(fmask: np.ndarray) -> float:
    return float(clear_mask(fmask).mean()) if fmask.size else 0.0


def read_band(granule, band: str, bbox, token=None) -> tuple:
    """(array, grid dict) of the window around bbox in one band of one granule. Grid: epsg, a, e, x0, y0, rows, cols."""
    if band not in granule.urls:
        raise ValueError(f"{granule.name} has no {band} band (has {sorted(granule.urls)})")
    url = granule.urls[band]
    if s1._remote(url):
        token = distalert._token(token)
    arr, grid, _ = distalert._read_layer(url, bbox, token)
    return arr, grid


def read_fmask(granule, bbox, token=None) -> tuple:
    return read_band(granule, FMASK, bbox, token)


def read_rgb(granule, bbox, token=None) -> tuple:
    """(rgb float32 (rows, cols, 3) reflectance, NaN = no data, grid dict) of the window."""
    chans, grid = [], None
    for name in ("red", "green", "blue"):
        arr, g = read_band(granule, BANDS[name], bbox, token)
        if grid is None:
            grid = g
        elif (g["rows"], g["cols"]) != (grid["rows"], grid["cols"]):
            raise ValueError(f"grid mismatch in {granule.name}: {BANDS[name]}")
        v = arr.astype(np.float32) / SCALE
        v[arr == NODATA] = np.nan
        chans.append(v)
    return np.stack(chans, axis=-1), grid


def clear_granules(granules, bbox, min_clear: float = 0.9, token=None, workers: int = 6) -> list:
    """[(granule, clear fraction)] for the granules whose window is at least min_clear clear (reads Fmask only).
    A granule that cannot be read is logged and dropped."""
    if any(s1._remote(u) for g in granules for u in g.urls.values()):
        token = distalert._token(token)

    def one(g):
        try:
            return g, clear_fraction(read_fmask(g, bbox, token)[0])
        except Exception as exc:  # one broken granule must not stop the run
            log.warning("%s: Fmask unreadable (%s)", g.name, exc)
            return g, 0.0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, granules))
    return [(g, f) for g, f in results if f >= min_clear]
