"""Spanish land registry (Catastro) buildings: how many registered buildings touch the polygon, and how recent.

Service: INSPIRE WFS of the Dirección General del Catastro, no login. Limits: the request box must be **≤ 1 km²** (else
``Area of extension out of limits``; tested 14 Nov 2026: 1,000 m square OK, 1,100 m or 4,000 x 500 m refused) and holds
at most 5,000 buildings, so we tile the polygon's bounding box into 990 m squares and split a tile again if it comes back full. Answer: GML 3.2 in EPSG:25831, ISO-8859-1.
Construction date (``dateOfConstruction/beginning``) is **year precision** (stored as 1 January), so ``since`` is
compared by year. ``beginLifespanVersion`` is the date the record was last edited, not a construction date.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET

import requests

from pyproj import Transformer
from shapely.geometry import Polygon, box

from ._common import UTM, OfflineMiss, ServiceError, fetch, safe, store, to_utm

SOURCE = "Derived from Dirección General del Catastro data"
SERVICE = "https://ovc.catastro.meh.es/INSPIRE/wfsBU.aspx"
VIEWER = "https://www1.sedecatastro.gob.es/Cartografia/mapa.aspx"
TILE_M = 990           # 0.98 km² < 1 km² limit
MAX_FEATURES = 5000
NS = {"gml": "http://www.opengis.net/gml/3.2",
      "bu-core2d": "http://inspire.jrc.ec.europa.eu/schemas/bu-core2d/2.0",
      "bu-ext2d": "http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0"}
_to_wgs = Transformer.from_crs(UTM, 4326, always_xy=True).transform


def _date(text: str | None) -> str | None:
    """``YYYY-MM-DD`` from the GML timestamp, or None for missing / malformed ones (some records hold e.g. ``0-01-01``)."""
    d = (text or "").strip()[:10]
    return d if len(d) == 10 and d[:4].isdigit() and d[4] == "-" and int(d[:4]) >= 1000 else None


def _parse(body: bytes) -> list[dict]:
    root = ET.fromstring(body)
    out = []
    for b in root.iter(f"{{{NS['bu-ext2d']}}}Building"):
        begin = b.find("bu-core2d:dateOfConstruction/bu-core2d:DateOfEvent/bu-core2d:beginning", NS)
        parts = []
        for pl in b.iterfind(".//gml:exterior//gml:posList", NS):
            v = [float(t) for t in pl.text.split()]
            if len(v) >= 6:
                parts.append(Polygon(list(zip(v[0::2], v[1::2]))))
        use = b.find("bu-ext2d:currentUse", NS)
        out.append({
            "id": b.get(f"{{{NS['gml']}}}id"),
            "date": _date(begin.text if begin is not None else None),
            "use": use.text if use is not None and use.text else None,
            "parts": parts,
        })
    return out


EMPTY_GML = b'<?xml version="1.0"?><gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml/3.2"/>'
MIN_SPLIT_M = 120      # don't split a slow tile below this side length


def _quarters(x0, y0, x1, y1):
    xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
    return ((x0, y0, xm, ym), (xm, y0, x1, ym), (x0, ym, xm, y1), (xm, ym, x1, y1))


def _tile(x0: float, y0: float, x1: float, y1: float) -> list[dict]:
    """Buildings in one box. A dense town tile (~4 MB of GML) can take minutes, so a big tile that times out is
    split in four instead of retried; a full tile (5,000 buildings, possibly truncated) is split too."""
    splittable = min(x1 - x0, y1 - y0) / 2 >= MIN_SPLIT_M
    params = {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": "BU:Building",
        "srsName": "EPSG::25831", "bbox": f"{x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}",
    }
    try:
        body = fetch("cadastre", SERVICE, params, timeout=60, retries=0 if splittable else None)
    except (requests.Timeout, OfflineMiss):  # a tile that timed out while recording was never cached: its quarters were
        if not splittable:
            raise
        return [f for q in _quarters(x0, y0, x1, y1) for f in _tile(*q)]
    except ServiceError as e:
        if "No records" in str(e):  # the registry's answer for a box with no building in it (sea, empty land)
            store("cadastre", SERVICE, params, EMPTY_GML)  # remember it: asking again takes retries and minutes
            return []
        raise
    feats = _parse(body)
    if len(feats) >= MAX_FEATURES:
        return [f for q in _quarters(x0, y0, x1, y1) for f in _tile(*q)]
    return feats


def grid_tiles(minx: float, miny: float, maxx: float, maxy: float) -> list[tuple[float, float, float, float]]:
    """Tiles of a fixed TILE_M grid (multiples of TILE_M in EPSG:25831) covering the box. Unlike tiles started at the
    box's corner, these stay the same when a site box grows or moves a little, so the cache keeps working."""
    i0, i1 = math.floor(minx / TILE_M), math.ceil(maxx / TILE_M)
    j0, j1 = math.floor(miny / TILE_M), math.ceil(maxy / TILE_M)
    return [(i * TILE_M, j * TILE_M, (i + 1) * TILE_M, (j + 1) * TILE_M) for i in range(i0, i1) for j in range(j0, j1)]


@safe(SOURCE, VIEWER)
def lookup(geometry: dict, since: str | None = None, **options) -> dict:
    """``buildings`` (count touching the polygon), ``newest_date`` (YYYY-MM-DD, year precision) and, with
    ``since="YYYY-MM-DD"``, ``built_since`` (buildings whose construction year is ≥ that year)."""
    g = to_utm(geometry)
    minx, miny, maxx, maxy = g.bounds
    nx, ny = max(1, math.ceil((maxx - minx) / TILE_M)), max(1, math.ceil((maxy - miny) / TILE_M))
    found = {}
    for i in range(nx):
        for j in range(ny):
            t = box(minx + i * TILE_M, miny + j * TILE_M,
                    min(maxx, minx + (i + 1) * TILE_M), min(maxy, miny + (j + 1) * TILE_M))
            if not t.intersects(g):
                continue
            for f in _tile(*t.bounds):
                if f["id"] not in found and any(p.intersects(g) for p in f["parts"]):
                    found[f["id"]] = f
    dates = sorted(f["date"] for f in found.values() if f["date"])
    lon, lat = _to_wgs(*g.centroid.coords[0])
    out = {
        "url": f"{VIEWER}?latitud={lat:.6f}&longitud={lon:.6f}&zoom=18",
        "buildings": len(found),
        "newest_date": dates[-1] if dates else None,
        "undated": len(found) - len(dates),  # buildings whose construction year is missing or malformed
    }
    if since:
        year = int(since[:4])
        out["built_since"] = sum(1 for d in dates if int(d[:4]) >= year)
    return out
