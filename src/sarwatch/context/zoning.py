"""Urban-planning classification (MUC, Mapa urbanístic de Catalunya): is the land urban, developable or non-buildable?

Service: Generalitat GeoServer WFS ``sig.gencat.cat/ows/PLANEJAMENT/wfs``, layer ``PLANEJAMENT:MUC_CLASSIFICACIONS``,
covering **all of Catalonia** (the Diputació REST copy covers Barcelona province only, so we don't use it). GeoJSON
output in EPSG:25831 (x = easting, y = northing). We fetch the classification polygons in the change's bounding box,
intersect them with the change, and report the class covering the largest share.
"""
from __future__ import annotations

import json

from shapely.geometry import shape

from ._common import fetch, safe, to_utm

SOURCE = "Mapa urbanístic de Catalunya (MUC), Generalitat de Catalunya"
SERVICE = "https://sig.gencat.cat/ows/PLANEJAMENT/wfs"
VIEWER = "https://dtes.gencat.cat/muc-visor/AppJava/home.do"
LAYER = "PLANEJAMENT:MUC_CLASSIFICACIONS"
ZONES = {  # CODI_CLAS_MUC -> our label (the five codes found across Catalonia, Nov 2026)
    "SUC": "urban",           # Sòl urbà (consolidated)
    "SNC": "urban",           # Sòl urbà no consolidat
    "SUD": "developable",     # Sòl urbanitzable delimitat
    "SND": "developable",     # Sòl urbanitzable no delimitat
    "SNU": "non_buildable",   # Sòl no urbanitzable
}
PAGE = 500


def features_in_box(minx: float, miny: float, maxx: float, maxy: float, layer: str = LAYER) -> list[dict]:
    """All features of a PLANEJAMENT WFS layer whose geometry intersects the EPSG:25831 box (paged)."""
    feats, start = [], 0
    while True:
        body = fetch("zoning", SERVICE, {
            "service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": layer,
            "bbox": f"{minx:.1f},{miny:.1f},{maxx:.1f},{maxy:.1f},urn:ogc:def:crs:EPSG::25831",
            "outputFormat": "application/json", "count": PAGE, "startIndex": start, "sortBy": "ID",
        })
        page = json.loads(body)["features"]
        feats += page
        if len(page) < PAGE:
            return feats
        start += PAGE


@safe(SOURCE, VIEWER)
def lookup(geometry: dict, **options) -> dict:
    """``zone`` ("urban" | "developable" | "non_buildable" | None), ``class`` (raw MUC name of that zone),
    ``shares`` ({zone: fraction of the polygon's area}) and ``classes`` (every raw class touched)."""
    g = to_utm(geometry)
    shares, raw = {}, {}
    for f in features_in_box(*g.bounds):
        a = shape(f["geometry"]).buffer(0).intersection(g).area
        if a <= 0:
            continue
        p = f["properties"]
        zone = ZONES.get(p["CODI_CLAS_MUC"])
        shares[zone] = shares.get(zone, 0.0) + a / g.area
        raw.setdefault(zone, {})
        name = p["DESC_CLAS_MUC"]
        raw[zone][name] = raw[zone].get(name, 0.0) + a
    if not shares:
        return {"zone": None, "class": None, "shares": {}, "classes": []}
    zone = max(shares, key=shares.get)
    return {
        "zone": zone,
        "class": max(raw[zone], key=raw[zone].get),
        "shares": {k or "unknown": round(v, 3) for k, v in sorted(shares.items(), key=lambda kv: -kv[1])},
        "classes": sorted({n for d in raw.values() for n in d}),
    }
