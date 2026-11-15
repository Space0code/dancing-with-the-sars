"""Map layers of "what the public records say" over a Catalan site box, for the app (#45).

    python -m sarwatch.context.layers agroparc        # writes app/data/agroparc/context/

Uses the same services, cache and network manners as the lookups (``kb/data-sources.md`` §3), but asks for the
geometry back and clips it to the site's ``bbox`` from ``app/data/sites.json``. Output format: ``kb/data-contract.md``
("Record layers"). A service that fails is left out of ``index.json`` and named on stderr; nothing raises.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

from . import cadastre, protected, solar, zoning
from ._common import UTM, fetch

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "app" / "data"
MAX_FILE = 1_000_000          # bytes per GeoJSON
BIG_BOX_M2 = 400e6            # a site box over 400 km2: the buildings layer covers only the land near the changes
FOCUS_M = 200                 # ... within this many metres of a marked change (400 m gave a 2 MB file at Barcelona)
TILE_WORKERS = 3              # cadastre tiles asked in parallel (the service is slow on dense towns)
_to_wgs = Transformer.from_crs(UTM, 4326, always_xy=True).transform
_to_utm = Transformer.from_crs(4326, UTM, always_xy=True).transform

USE = {  # Catastro currentUse codes (INSPIRE BuildingExtended2D) in plain words
    "1_residential": "home", "2_agriculture": "farm building", "3_industrial": "industrial",
    "4_1_office": "office", "4_2_retail": "shop", "4_3_publicServices": "public service",
}
ZONING_CLASS = {"urban": "buildable", "developable": "planned", "non_buildable": "non_buildable"}
ZONING_LABEL = {
    "buildable": "Urban land (building allowed)",
    "planned": "Land planned for development",
    "non_buildable": "Non-buildable land (rural / protected by the plan)",
}


def site_bbox(site: str) -> list[float]:
    sites = json.loads((DATA / "sites.json").read_text(encoding="utf-8"))["sites"]
    s = next((x for x in sites if x["id"] == site), None)
    if s is None:
        raise SystemExit(f"unknown site {site!r}; known: {', '.join(x['id'] for x in sites)}")
    return s["bbox"]


def _utm_box(bbox):
    w, so, e, n = bbox
    return shapely.transform(box(w, so, e, n).segmentize(0.001),  # densify so the UTM box keeps its curved edges
                             lambda xy: np.column_stack(_to_utm(xy[:, 0], xy[:, 1])))


def _short(text: str, n: int = 160) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip(" ,;") + "…"


def _wgs(g):
    return shapely.transform(g, lambda xy: np.column_stack(_to_wgs(xy[:, 0], xy[:, 1])))


def _snap(geom, grid: float):
    """Round the coordinates to ``grid`` degrees. Snapping can make a thin or nearly degenerate polygon invalid (GEOS
    "side location conflict"): repair it first, and if the grid still cannot hold it, round the points as they are."""
    try:
        return shapely.set_precision(geom, grid)
    except shapely.errors.GEOSException:
        try:
            return shapely.set_precision(shapely.make_valid(geom), grid)
        except shapely.errors.GEOSException:
            return shapely.set_precision(geom, grid, mode="pointwise")


def _feature(g, props: dict, grid: float = 1e-6) -> dict:
    geom = mapping(_snap(_wgs(g), grid))
    return {"type": "Feature", "geometry": geom, "properties": {k: v for k, v in props.items() if v is not None}}


def _safe_feature(g, props: dict, grid: float = 1e-6) -> dict | None:
    """``_feature``, or None (said on stderr) for a shape that cannot be written: one bad outline must not lose a layer."""
    try:
        return _feature(g, props, grid)
    except shapely.errors.GEOSException as e:
        print(f"  skipped one shape ({props.get('label', '?')[:50]}): {e}", file=sys.stderr)
        return None


def _write(path: Path, feats: list[dict]) -> int:
    doc = {"type": "FeatureCollection", "features": feats}
    text = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    path.write_text(text, encoding="utf-8")
    return len(text.encode())


def _polys(g):
    """Keep only the areal part of a clip result (drop stray lines / points on the box edge)."""
    if g.is_empty:
        return None
    if g.geom_type in ("Polygon", "MultiPolygon"):
        return g
    parts = [p for p in getattr(g, "geoms", []) if p.geom_type in ("Polygon", "MultiPolygon")]
    return unary_union(parts) if parts else None


# --- one builder per layer: return (features, meta) --------------------------------------------------------------

def protected_layer(site_box, tol: float):
    xmin, ymin, xmax, ymax = site_box.bounds
    feats = []
    for layer, cls in ((1, "natura2000"), (0, "pein"), (3, "other")):
        body = fetch("protected", f"{protected.SERVICE}/{layer}/query", {
            "geometry": f"{xmin:.1f},{ymin:.1f},{xmax:.1f},{ymax:.1f}", "geometryType": "esriGeometryEnvelope",
            "inSR": UTM, "outSR": UTM, "spatialRel": "esriSpatialRelIntersects", "outFields": "*",
            "returnGeometry": "true", "maxAllowableOffset": tol, "f": "json",
        }, method="POST")
        for f in json.loads(body)["features"]:
            a = f["attributes"]
            rings = f.get("geometry", {}).get("rings") or []
            g = _polys(_rings_to_shape(rings).intersection(site_box))
            if g is None:
                continue
            if layer == 1:
                types = [t for t, flag in (("habitats", a["LIC_ZEC"]), ("birds", a["ZEPA"])) if flag == "S"]
                name = a["NOM_XN2"]
                label = f"Natura 2000 site: {name} ({' + '.join(types) or 'EU'} directive)"
            elif layer == 0:
                name = a["NOM_PEIN"]
                label = f"Catalan protected natural area (PEIN): {name}"
            else:
                name = a["NOM_ESPAI"]
                label = f"{protected.ENPE_KINDS.get(a['CODI_ESPAI'], 'Protected area').capitalize()}: {name}"
            feats.append((g, {"label": label, "class": cls, "name": name, "area_ha": round(g.area / 1e4, 1)}))
    names = sorted({props["name"] for _, props in feats})
    note = ("Inside the box: " + "; ".join(names)) if names else "No protected area inside this box."
    return feats, {"id": "protected", "title": "Protected nature areas", "kind": "protected",
                   "source": protected.SOURCE, "url": protected.VIEWER, "note": note}


def _rings_to_shape(rings):
    """ArcGIS rings (outer clockwise, holes counter-clockwise) -> shapely (Multi)Polygon."""
    from shapely.geometry import LinearRing, Polygon
    outers, holes = [], []
    for r in rings:
        if len(r) < 4:
            continue
        (outers if not LinearRing(r).is_ccw else holes).append(Polygon(r))
    g = unary_union(outers)
    if holes:
        g = g.difference(unary_union(holes))
    return g.buffer(0)


def zoning_layer(site_box, tol: float):
    merged = {}
    for f in zoning.features_in_box(*site_box.bounds):
        zone = zoning.ZONES.get(f["properties"]["CODI_CLAS_MUC"])
        cls = ZONING_CLASS.get(zone)
        if cls is None:
            continue
        g = _polys(shape(f["geometry"]).buffer(0).intersection(site_box))
        if g is not None:
            merged.setdefault(cls, []).append(g)
    feats = []
    for cls in ("non_buildable", "planned", "buildable"):
        if cls in merged:
            g = unary_union(merged[cls]).simplify(tol)
            feats.append((g, {"label": ZONING_LABEL[cls], "class": cls, "area_ha": round(g.area / 1e4, 1)}))
    share = {props["class"]: g.area / site_box.area for g, props in feats}
    note = "Share of the box: " + ", ".join(f"{ZONING_LABEL[c].split(' (')[0].lower()} {round(100 * v)} %"
                                             for c, v in share.items())
    return feats, {"id": "zoning", "title": "Zoning: where building is allowed", "kind": "zoning",
                   "source": zoning.SOURCE, "url": zoning.VIEWER, "note": note}


def focus_area(site: str, buffer_m: float = FOCUS_M):
    """The land within ``buffer_m`` of the site's marked changes (EPSG:25831), or None without a changes file."""
    path = DATA / site / "changes.geojson"
    if not path.is_file():
        return None
    geoms = [shape(f["geometry"]) for f in json.loads(path.read_text(encoding="utf-8"))["features"]]
    if not geoms:
        return None
    area = unary_union([shapely.transform(g, lambda xy: np.column_stack(_to_utm(xy[:, 0], xy[:, 1]))) for g in geoms])
    return area.buffer(buffer_m, 4).simplify(5)


def _building_shape(parts, area):
    """One building's footprint clipped to ``area``, or None. Registry outlines are sometimes invalid (a bowtie from a
    mistyped vertex): repair each part first, and leave out a building that still cannot be clipped."""
    try:
        return _polys(unary_union([shapely.make_valid(p) for p in parts]).intersection(area))
    except shapely.errors.GEOSException:
        return None


def buildings_layer(site_box, tol: float, focus=None):
    """Registered buildings in the box; with ``focus`` (a big site) only those within it, clipped to it."""
    area = focus.intersection(site_box) if focus is not None else site_box
    tiles = [t for t in cadastre.grid_tiles(*area.bounds) if box(*t).intersects(area)]
    found = {}
    with ThreadPoolExecutor(TILE_WORKERS) as pool:
        for feats in pool.map(lambda t: cadastre._tile(*t), tiles):
            for b in feats:
                found.setdefault(b["id"], b)
    groups, years = {}, []  # one feature per (year, use): thousands of footprints stay under 1 MB
    for b in found.values():
        g = _building_shape(b["parts"], area) if b["parts"] else None
        if g is None:
            continue
        year = int(b["date"][:4]) if b["date"] else None
        groups.setdefault((year, USE.get(b.get("use"))), []).append(g.simplify(tol))
        if year:
            years.append(year)
    feats = []
    for (year, use), gs in sorted(groups.items(), key=lambda kv: (kv[0][0] or 0, kv[0][1] or "")):
        n = len(gs)
        label = (f"{n} registered building{'s' if n > 1 else ''}" + (f" ({use})" if use else "")
                 + (f", built {year}" if year else ", year unknown"))
        feats.append((unary_union([shapely.make_valid(g) for g in gs]), {"label": label, "year": year}))
    recent = sum(1 for y in years if y >= 2016)
    note = (f"{sum(len(gs) for gs in groups.values())} registered buildings, merged; {recent} built in 2016 or later"
            + (f", newest {max(years)}" if years else "") + ". Construction year only, no exact date."
            + (f" Only within {FOCUS_M} m of a marked change." if focus is not None else ""))
    return feats, {"id": "buildings", "title": "Registered buildings", "kind": "buildings",
                   "source": cadastre.SOURCE, "url": cadastre.VIEWER, "note": note}


def solar_note(site_box) -> str | None:
    """The solar list has no coordinates: name the plants filed in the municipalities the box touches."""
    munis = {}
    for f in zoning.features_in_box(*site_box.bounds, layer="PLANEJAMENT:MUC_AMBIT_MUNICIPAL"):
        if shape(f["geometry"]).buffer(0).intersection(site_box).area > 0:
            munis[f["properties"]["CODI_INE"]] = f["properties"]["MUNICIPI"]
    status = {"En tramitació": "pending", "Autoritzat": "authorised", "En servei": "in service", "Aprovat": "approved",
              "No autoritzat": "refused", "Desistit": "withdrawn"}
    plants = []
    for code in sorted(munis):
        rows = json.loads(fetch("solar", solar.SERVICE, {"$where": f"starts_with(codi_municipi, '{code}')",
                                                         "$limit": 1000}))
        plants += [f"{r.get('nom')}, {r.get('municipi')}, {r.get('superf_cie_ha', '?')} ha, "
                   f"{status.get(r.get('estat'), r.get('estat'))}"
                   for r in rows if str(r.get("codi_municipi", ""))[:5] == code]
    if not plants:
        return f"No solar plant filed in {', '.join(sorted(munis.values()))} (list has no map positions)."
    head = f"{len(plants)} solar plants filed in these towns (no map positions): "
    text, shown = head, 0
    for pl in plants:  # whole entries only, then "+N more", within the 160-char note
        more = f" +{len(plants) - shown - 1} more" if shown + 1 < len(plants) else ""
        if len(text) + len(pl) + len(more) + 2 > 160:
            break
        text += ("; " if shown else "") + pl
        shown += 1
    return text + (f"; +{len(plants) - shown} more" if shown < len(plants) else "")


# --- driver -------------------------------------------------------------------------------------------------------

BUILDERS = {"protected": (protected_layer, 10.0), "zoning": (zoning_layer, 5.0), "buildings": (buildings_layer, 0.5)}
# If a file is over MAX_FILE: simplify more and round coarser (1e-5° ≈ 1 m), without asking the services again.
SHRINK = [(1, 1e-6), (2, 1e-6), (2, 1e-5), (4, 1e-5), (8, 1e-5), (16, 1e-5)]


def build(site: str, out_dir: Path | None = None, today: str | None = None, bbox: list[float] | None = None,
          focus=None) -> dict:
    """Write ``<site>/context/*.geojson`` + ``index.json``; return the index. Failed services are skipped.
    ``bbox`` ([west, south, east, north], EPSG:4326) overrides the site's box from ``sites.json``."""
    site_box = _utm_box(bbox or site_bbox(site))
    if focus is None and bbox is None and site_box.area > BIG_BOX_M2:
        focus = focus_area(site)  # a region-sized box: buildings only near the changes
    out = out_dir or DATA / site / "context"
    out.mkdir(parents=True, exist_ok=True)
    today = today or dt.date.today().isoformat()
    index = {"layers": []}
    for lid, (fn, tol) in BUILDERS.items():
        try:
            shapes, meta = fn(site_box, tol, focus=focus) if lid == "buildings" else fn(site_box, tol)
            path = out / f"{lid}.geojson"
            for factor, grid in SHRINK:
                feats = [_safe_feature(g.simplify(tol * factor) if factor > 1 else g, props, grid) for g, props in shapes]
                feats = [f for f in feats if f and f["geometry"]["coordinates"]]
                size = _write(path, feats)
                if size <= MAX_FILE:
                    break
            index["layers"].append({**meta, "note": _short(meta["note"]), "file": path.name, "checked": today})
            print(f"{lid}: {len(feats)} features, {size / 1e3:.0f} kB", file=sys.stderr)
        except Exception as e:  # noqa: BLE001 (a failed service leaves its layer out, never crashes)
            (out / f"{lid}.geojson").unlink(missing_ok=True)
            print(f"{lid}: FAILED, layer left out ({type(e).__name__}: {e})", file=sys.stderr)
    try:
        note = solar_note(site_box)
        index["notes"] = [{"kind": "solar", "source": solar.SOURCE, "url": solar.VIEWER, "checked": today,
                           "note": _short(note)}]
    except Exception as e:  # noqa: BLE001
        print(f"solar: FAILED, note left out ({type(e).__name__}: {e})", file=sys.stderr)
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return index


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("site", help="site id from app/data/sites.json (Catalan sites only)")
    args = ap.parse_args(argv)
    index = build(args.site)
    return 0 if index["layers"] else 1


if __name__ == "__main__":
    sys.exit(main())
