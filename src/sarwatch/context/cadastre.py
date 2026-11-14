"""Spanish land registry (Catastro) buildings: how many registered buildings touch the polygon, and how recent.

Service: INSPIRE WFS of the Dirección General del Catastro, no login. Limits: the request box must be **≤ 4 km²** (else
``Area of extension out of limits``) and holds at most 5,000 buildings, so we tile the polygon's bounding box into
≤ 1.9 km squares and split a tile again if it comes back full. Answer: GML 3.2 in EPSG:25831, ISO-8859-1.
Construction date (``dateOfConstruction/beginning``) is **year precision** (stored as 1 January), so ``since`` is
compared by year. ``beginLifespanVersion`` is the date the record was last edited, not a construction date.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET

from pyproj import Transformer
from shapely.geometry import Polygon, box

from ._common import UTM, fetch, safe, to_utm

SOURCE = "Catastro buildings (INSPIRE WFS, Dirección General del Catastro)"
SERVICE = "https://ovc.catastro.meh.es/INSPIRE/wfsBU.aspx"
VIEWER = "https://www1.sedecatastro.gob.es/Cartografia/mapa.aspx"
TILE_M = 1900          # 1.9 km x 1.9 km = 3.61 km² < 4 km² limit
MAX_FEATURES = 5000
NS = {"gml": "http://www.opengis.net/gml/3.2",
      "bu-core2d": "http://inspire.jrc.ec.europa.eu/schemas/bu-core2d/2.0",
      "bu-ext2d": "http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0"}
_to_wgs = Transformer.from_crs(UTM, 4326, always_xy=True).transform


def _date(text: str | None) -> str | None:
    """``YYYY-MM-DD`` from the registry's text, or None when it is missing or malformed (a few records carry a
    placeholder such as ``1-01-01``): such a building counts, but has no construction year."""
    head = (text or "")[:10]
    return head if re.fullmatch(r"[12]\d{3}-\d{2}-\d{2}", head) else None


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
        out.append({
            "id": b.get(f"{{{NS['gml']}}}id"),
            "date": _date(begin.text) if begin is not None else None,
            "parts": parts,
        })
    return out


def _tile(x0: float, y0: float, x1: float, y1: float) -> list[dict]:
    body = fetch("cadastre", SERVICE, {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": "BU:Building",
        "srsName": "EPSG::25831", "bbox": f"{x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}",
    }, timeout=120)  # dense industrial tiles answer slowly
    feats = _parse(body)
    if len(feats) >= MAX_FEATURES:  # truncated: split in four
        xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
        return [f for q in ((x0, y0, xm, ym), (xm, y0, x1, ym), (x0, ym, xm, y1), (xm, ym, x1, y1)) for f in _tile(*q)]
    return feats


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
