"""Protected areas: PEIN (Catalan plan of natural areas), Natura 2000 and specially protected natural areas (ENPE).

Service: ArcGIS REST MapServer run by Diputació de Barcelona, covering **all of Catalonia**, native CRS EPSG:25831.
Layers: 0 = PEIN, 1 = Natura 2000 (SAC + SPA), 3 = ENPE (national/natural parks, reserves, their buffer zones).
We send the polygon in EPSG:25831 and ask "which areas intersect it" (no geometry back, so the answer stays small).
"""
from __future__ import annotations

import json

from shapely.geometry import MultiPolygon
from shapely.geometry.polygon import orient

from ._common import UTM, fetch, safe, to_utm

SOURCE = "PEIN + Natura 2000 (Generalitat de Catalunya, via Diputació de Barcelona)"
SERVICE = "https://gissrv.diba.cat/arcgis/rest/services/SITXELL/PEIN_XN2000_ENPE/MapServer"
VIEWER = "https://sig.gencat.cat/visors/hipermapa.html"

ENPE_KINDS = {
    "pnac": "national park", "zpnac": "national park buffer zone",
    "pnat": "natural park", "zpnat": "natural park buffer zone",
    "pnin": "natural site of national interest",
    "rni": "strict nature reserve", "rnp": "partial nature reserve", "zrnp": "partial nature reserve buffer zone",
    "rnfs": "wildlife reserve",
}


def _esri_polygon(g) -> str:
    parts = g.geoms if isinstance(g, MultiPolygon) else [g]
    rings = []
    for p in parts:
        p = orient(p, sign=-1.0)  # ArcGIS: outer rings clockwise, holes counter-clockwise
        rings.append([[round(x, 2), round(y, 2)] for x, y in p.exterior.coords])
        rings += [[[round(x, 2), round(y, 2)] for x, y in r.coords] for r in p.interiors]
    return json.dumps({"rings": rings, "spatialReference": {"wkid": UTM}}, separators=(",", ":"))


def _query(layer: int, esri_geom: str) -> list[dict]:
    body = fetch("protected", f"{SERVICE}/{layer}/query", {
        "geometry": esri_geom, "geometryType": "esriGeometryPolygon", "inSR": UTM,
        "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "returnGeometry": "false", "f": "json",
    }, method="POST")
    return [f["attributes"] for f in json.loads(body)["features"]]


@safe(SOURCE, VIEWER)
def lookup(geometry: dict, **options) -> dict:
    """``inside`` (bool: the polygon touches at least one protected area) and ``areas`` ([{name, kind, code}])."""
    g = to_utm(geometry).simplify(1.0)
    esri = _esri_polygon(g)
    areas = []
    for a in _query(0, esri):
        areas.append({"name": a["NOM_PEIN"], "kind": "PEIN", "code": a["CODI_PEIN"]})
    out = {}
    for a in _query(1, esri):
        types = [t for t, flag in (("SAC", a["LIC_ZEC"]), ("SPA", a["ZEPA"])) if flag == "S"]
        areas.append({"name": a["NOM_XN2"], "kind": "Natura 2000 " + "/".join(types or ["site"]), "code": a["CODI_XN2"]})
        if a.get("FND_ZEC", "").strip().startswith("http"):
            out["url"] = a["FND_ZEC"].strip()  # official Natura 2000 site sheet: a page a human can open
    for a in _query(3, esri):
        areas.append({"name": a["NOM_ESPAI"], "kind": ENPE_KINDS.get(a["CODI_ESPAI"], a["CODI_ESPAI"]),
                      "code": a["CODI_ESPAI"]})
    return {**out, "inside": bool(areas), "areas": areas}
