"""Cleared hectares over time inside the Muhos clearing outline, one line per source (#27, #73).

    PYTHONPATH=src python explore/muhos/story_series.py --cache <radar cache>   # -> app/data/muhos/story_series.json

Three separate lines, never one stitched curve (kb/evidence-check.md): they measure different things.
- Optical alerts: confirmed vegetation loss, cumulative by month of first detection (the clearing's changes in
  app/data/muhos/changes.geojson, which are the alerts' monthly parts), starting at 0 on the last look before winter.
- Sentinel-1: ground inside the outline that the detector flagged, cumulative by the pass from which each pixel stayed
  changed (its first-change pass). C-band dates the block's edges early (5 x 5 boxcar of 30 m pixels, spring snow).
- NISAR: ground inside the outline that looks bare on each pass: vegetation echo (HV, 7 x 7 boxcar in linear power)
  at least BARE_DB below the window's median of that pass. A state, not a cumulative count: it can go down.
All hectares are true ground area: the radar grids' pixels are counted as projected squares, which inflate area (the
NISAR polar grid by about 3.7 % at Muhos), so each pixel is divided by the grid's areal scale at the outline (areal_scale).
Settings and skip dates are the pipeline's Muhos settings; reads the radar cache only (no network).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
from scipy import ndimage
from pyproj import Geod
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from sarwatch import pipeline as pl  # noqa: E402

BARE_DB = 1.25  # NISAR: half way between standing forest (about the window median) and the cleared block (-2.5 dB)
SITE_DIR = ROOT / "app" / "data" / "muhos"
EVENTS = ("2026-04-30", "2026-05-01", "2026-10-06")  # from story.json: the request, the answer, the stop notice


def areal_scale(epsg: int, lon: float, lat: float) -> float:
    """How many times larger an area is on the EPSG grid than on the ground, at a point (projected area of a
    100 m square on that grid over the geodesic area of the same square)."""
    from pyproj import Geod, Transformer

    x, y = Transformer.from_crs(4326, epsg, always_xy=True).transform(lon, lat)
    ring = [(x, y), (x + 100, y), (x + 100, y + 100), (x, y + 100)]
    lons, lats = Transformer.from_crs(epsg, 4326, always_xy=True).transform(*zip(*ring))
    return 1e4 / abs(Geod(ellps="WGS84").polygon_area_perimeter(lons, lats)[0])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cache", default=str(ROOT / "data" / "stacks"))
    cache = Path(p.parse_args().cache)
    site = pl.SITES["muhos"]
    spans = pl._skip_spans(site)
    days = {s: [d for d in pl.cached_days(cache / "muhos" / s) if not any(lo <= d <= hi for lo, hi in spans)]
            for s in (pl.NISAR, pl.S1)}
    scope = json.loads((ROOT / site.primary_scope).read_text())["geometry"]
    centre = shape(scope).centroid
    outline_ha = round(abs(Geod(ellps="WGS84").geometry_area_perimeter(shape(scope))[0]) / 1e4)
    where = f"inside the clearing outline ({outline_ha} ha)"
    series = []

    # optical alerts: the clearing's monthly parts, cumulative
    feats = json.loads((SITE_DIR / "changes.geojson").read_text(encoding="utf-8"))["features"]
    outline = shape(scope)
    parts = [f["properties"] for f in feats if f["properties"]["sensor"] == pl.OPTICAL
             and shape(f["geometry"]).intersection(outline).area >= 0.5 * shape(f["geometry"]).area]
    by_day = {}
    for prop in parts:
        by_day[prop["first_date"]] = by_day.get(prop["first_date"], 0.0) + prop["area_ha"]
    start = min(prop["not_before"] for prop in parts)
    dates, values, total = [start], [0.0], 0.0
    for d in sorted(by_day):
        total += by_day[d]
        dates.append(d)
        values.append(round(total, 1))
    series.append({"name": "Optical alerts",
                   "note": f"Optical alerts: vegetation loss confirmed, cumulative, {where}.", "unit": "ha",
                   "sensor": pl.OPTICAL, "dates": dates, "values": values})

    # Sentinel-1: flagged ground, cumulative by first-change pass
    s1 = pl.detect(pl.S1, site, cache, days[pl.S1], pl._params(site, pl.S1))
    part = pl._part_mask(s1, scope)
    px_ha = abs(s1.transform[0] * s1.transform[4]) / 1e4 / areal_scale(s1.epsg, centre.x, centre.y)
    n0 = pl._params(site, pl.S1).n_early
    idx = np.maximum(s1.result.first_change_idx[part & (s1.result.labels > 0)], n0)  # a baseline date is no date
    # the winter (1 Oct 2025 - 31 Mar 2026) is skipped: the curve starts at the first pass after it, with the
    # ground already flagged then, and no point is invented in between
    first = next(t for t in range(n0, len(s1.dates)) if s1.dates[t].year >= 2026)
    dates = [str(d) for d in s1.dates[first:]]
    values = [round(float((idx <= t).sum() * px_ha), 1) for t in range(first, len(s1.dates))]
    series.append({"name": "Sentinel-1 radar",
                   "note": f"Sentinel-1 radar: ground flagged as changed, cumulative, {where}. "
                           "Winter 2025-26 was not observed and edges are dated early.", "unit": "ha",
                   "sensor": s1.sensor, "dates": dates, "values": values})

    # NISAR: bare-looking ground on each pass
    stack, ndates, transform, epsg = pl.load_stack(cache / "muhos" / pl.NISAR, days[pl.NISAR], site.bbox)
    run = pl.detect(pl.NISAR, site, cache, days[pl.NISAR], pl._params(site, pl.NISAR))
    part = pl._part_mask(run, scope)
    scale = areal_scale(epsg, centre.x, centre.y)  # the polar grid inflates area at Muhos
    px_ha = abs(transform[0] * transform[4]) / 1e4 / scale
    values = []
    for k in range(len(ndates)):
        hv = np.asarray(stack["HV"][k], dtype=np.float64)
        ok = np.isfinite(hv) & (hv > 0)
        mean = ndimage.uniform_filter(np.where(ok, hv, 0), 7) / np.maximum(ndimage.uniform_filter(ok * 1.0, 7), 1e-9)
        db = 10 * np.log10(np.maximum(mean, 1e-12))
        bare = (db - np.median(db[ok])) <= -BARE_DB
        values.append(round(float((bare & part & ok).sum() * px_ha), 1))
    series.append({"name": "NISAR radar", "unit": "ha", "sensor": run.sensor,
                   "note": f"NISAR radar: bare-looking ground on each pass, {where}, as true ground area.",
                   "dates": [str(d) for d in ndates], "values": values})

    story = json.loads((SITE_DIR / "story.json").read_text(encoding="utf-8"))
    events = [e for e in story["events"] if e["date"] in EVENTS]
    events.append({"date": str(s1.dates[first]), "label": "Sentinel-1 was not observed from 1 Oct 2025 to 31 Mar 2026: "
                   "its curve starts at its first 2026 pass, with the ground already flagged by then"})
    events.sort(key=lambda e: e["date"])
    out = {"series": series, "events": events}
    (SITE_DIR / "story_series.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("areal scale NISAR grid", round(scale, 4), "S1 grid", round(areal_scale(s1.epsg, centre.x, centre.y), 4))
    for s in series:
        print(s["name"], list(zip(s["dates"], s["values"]))[::max(1, len(s["dates"]) // 12)], s["values"][-1])


if __name__ == "__main__":
    main()
