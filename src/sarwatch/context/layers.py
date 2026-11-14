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
import math
import sys
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


def _feature(g, props: dict) -> dict:
    geom = mapping(shapely.set_precision(_wgs(g), 1e-6))
    return {"type": "Feature", "geometry": geom, "properties": {k: v for k, v in props.items() if v is not None}}


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
            feats.append(_feature(g, {"label": label, "class": cls, "name": name,
                                      "area_ha": round(g.area / 1e4, 1)}))
    names = sorted({f["properties"]["name"] for f in feats})
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
            feats.append(_feature(g, {"label": ZONING_LABEL[cls], "class": cls,
                                      "area_ha": round(g.area / 1e4, 1)}))
    total = site_box.area
    share = {f["properties"]["class"]: f["properties"]["area_ha"] * 1e4 / total for f in feats}
    note = "Share of the box: " + ", ".join(f"{ZONING_LABEL[c].split(' (')[0].lower()} {round(100 * v)} %"
                                             for c, v in share.items())
    return feats, {"id": "zoning", "title": "Zoning: where building is allowed", "kind": "zoning",
                   "source": zoning.SOURCE, "url": zoning.VIEWER, "note": note}


def buildings_layer(site_box, tol: float):
    minx, miny, maxx, maxy = site_box.bounds
    step = cadastre.TILE_M
    found = {}
    for i in range(math.ceil((maxx - minx) / step)):
        for j in range(math.ceil((maxy - miny) / step)):
            t = box(minx + i * step, miny + j * step, min(maxx, minx + (i + 1) * step), min(maxy, miny + (j + 1) * step))
            if t.intersects(site_box):
                for b in cadastre._tile(*t.bounds):
                    found.setdefault(b["id"], b)
    feats, years = [], []
    for b in found.values():
        g = _polys(unary_union(b["parts"]).buffer(0).intersection(site_box)) if b["parts"] else None
        if g is None:
            continue
        year = int(b["date"][:4]) if b["date"] else None
        use = USE.get(b.get("use"), None)
        label = "Registered building" + (f" ({use})" if use else "") + (f", built {year}" if year else ", year unknown")
        feats.append(_feature(g.simplify(tol), {"label": label, "year": year, "name": b["id"].rsplit(".", 1)[-1]}))
        if year:
            years.append(year)
    recent = sum(1 for y in years if y >= 2016)
    note = (f"{len(feats)} buildings on the land registry; {recent} built in 2016 or later"
            + (f", newest {max(years)}" if years else "") + ". Construction year only, no exact date.")
    return feats, {"id": "buildings", "title": "Buildings on the land registry", "kind": "buildings",
                   "source": cadastre.SOURCE, "url": cadastre.VIEWER, "note": note}


def solar_note(site_box) -> str | None:
    """The solar list has no coordinates: name the plants filed in the municipalities the box touches."""
    munis = {}
    for f in zoning.features_in_box(*site_box.bounds, layer="PLANEJAMENT:MUC_AMBIT_MUNICIPAL"):
        if shape(f["geometry"]).buffer(0).intersection(site_box).area > 0:
            munis[f["properties"]["CODI_INE"]] = f["properties"]["MUNICIPI"]
    plants = []
    for code in sorted(munis):
        rows = json.loads(fetch("solar", solar.SERVICE, {"$where": f"starts_with(codi_municipi, '{code}')",
                                                         "$limit": 1000}))
        plants += [f"{r.get('nom')} ({r.get('municipi')}, {r.get('superf_cie_ha', '?')} ha, {r.get('estat', '').lower()})"
                   for r in rows if str(r.get("codi_municipi", ""))[:5] == code]
    if not plants:
        return f"No solar plant filed in {', '.join(sorted(munis.values()))} (list has no map positions)."
    return "Solar plants filed here (list has no map positions): " + "; ".join(plants)


# --- driver -------------------------------------------------------------------------------------------------------

BUILDERS = {"protected": (protected_layer, 10.0), "zoning": (zoning_layer, 5.0), "buildings": (buildings_layer, 0.5)}


def build(site: str, out_dir: Path | None = None, today: str | None = None, bbox: list[float] | None = None) -> dict:
    """Write ``<site>/context/*.geojson`` + ``index.json``; return the index. Failed services are skipped.
    ``bbox`` ([west, south, east, north], EPSG:4326) overrides the site's box from ``sites.json``."""
    site_box = _utm_box(bbox or site_bbox(site))
    out = out_dir or DATA / site / "context"
    out.mkdir(parents=True, exist_ok=True)
    today = today or dt.date.today().isoformat()
    index = {"layers": []}
    for lid, (fn, tol) in BUILDERS.items():
        try:
            feats, meta = fn(site_box, tol)
            path = out / f"{lid}.geojson"
            size = _write(path, feats)
            while size > MAX_FILE and tol < 50:  # too big: simplify harder
                tol *= 2
                feats, meta = fn(site_box, tol)
                size = _write(path, feats)
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
