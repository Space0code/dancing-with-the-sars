"""Protected areas: PEIN (Catalan plan of natural areas), Natura 2000 and specially protected natural areas (ENPE).

Service: ArcGIS REST MapServer run by Diputació de Barcelona, covering **all of Catalonia**, native CRS EPSG:25831.
Layers: 0 = PEIN, 1 = Natura 2000 (SAC + SPA), 3 = ENPE (national/natural parks, reserves, their buffer zones).
We send the polygon in EPSG:25831 and ask "which areas intersect it" (no geometry back, so the answer stays small).
"""
from __future__ import annotations

import json

from shapely.geometry import LinearRing, MultiPolygon, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from shapely.validation import make_valid

from ._common import UTM, fetch, safe, to_utm

SOURCE = "PEIN + Natura 2000 (Generalitat de Catalunya, via Diputació de Barcelona)"
SERVICE = "https://gissrv.diba.cat/arcgis/rest/services/SITXELL/PEIN_XN2000_ENPE/MapServer"
VIEWER = "https://sig.gencat.cat/visors/hipermapa.html"
SIMPLIFY_M = 5  # the service generalises the returned outlines to this many metres

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


def _shape(geom: dict | None):
    """ArcGIS polygon (``rings``: outer rings clockwise, holes counter-clockwise) -> shapely geometry, or None."""
    outers, holes = [], []
    for ring in (geom or {}).get("rings", []):
        if len(ring) >= 4:
            (holes if LinearRing(ring).is_ccw else outers).append(make_valid(Polygon(ring)))
    if not outers:
        return None
    g = unary_union(outers)
    return g.difference(unary_union(holes)) if holes else g


def _query(layer: int, esri_geom: str) -> list[tuple[dict, object]]:
    """[(attributes, shapely geometry in EPSG:25831 or None)]. The service simplifies the outlines to ``SIMPLIFY_M``
    metres, which keeps park outlines small and is far below the size of a detected change."""
    body = fetch("protected", f"{SERVICE}/{layer}/query", {
        "geometry": esri_geom, "geometryType": "esriGeometryPolygon", "inSR": UTM,
        "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "returnGeometry": "true", "outSR": UTM,
        "maxAllowableOffset": SIMPLIFY_M, "f": "json",
    }, method="POST")
    return [(f["attributes"], _shape(f.get("geometry"))) for f in json.loads(body)["features"]]


@safe(SOURCE, VIEWER)
def lookup(geometry: dict, **options) -> dict:
    """``inside`` (bool: the polygon touches at least one protected area), ``areas`` ([{name, kind, code,
    overlap_share}]) and ``overlap_share`` (share of the polygon inside any protected area, 0-1). A 1 m² edge touch has
    a share near 0 and a real overlap near 1; ``None`` if the service sent no outline for some area."""
    g = to_utm(geometry).simplify(1.0)
    esri = _esri_polygon(g)
    areas, shapes = [], []

    def add(attrs, shp, name, kind, code):
        shapes.append(shp)
        share = None if shp is None else round(make_valid(shp).intersection(g).area / g.area, 4)
        areas.append({"name": attrs[name], "kind": kind, "code": attrs[code], "overlap_share": share})

    for a, shp in _query(0, esri):
        add(a, shp, "NOM_PEIN", "PEIN", "CODI_PEIN")
    out = {}
    for a, shp in _query(1, esri):
        types = [t for t, flag in (("SAC", a["LIC_ZEC"]), ("SPA", a["ZEPA"])) if flag == "S"]
        add(a, shp, "NOM_XN2", "Natura 2000 " + "/".join(types or ["site"]), "CODI_XN2")
        if a.get("FND_ZEC", "").strip().startswith("http"):
            out["url"] = a["FND_ZEC"].strip()  # official Natura 2000 site sheet: a page a human can open
    for a, shp in _query(3, esri):
        add(a, shp, "NOM_ESPAI", ENPE_KINDS.get(a["CODI_ESPAI"], a["CODI_ESPAI"]), "CODI_ESPAI")
    known = [make_valid(s) for s in shapes if s is not None]  # not buffer(0): that can drop a lobe of a bowtie
    overall = None
    if areas and len(known) == len(shapes):
        overall = round(unary_union(known).intersection(g).area / g.area, 4)
    elif not areas:
        overall = 0.0
    return {**out, "inside": bool(areas), "areas": areas, "overlap_share": overall}
