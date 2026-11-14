"""When was the Muhos clearing cut? Sentinel-1 VH inside the radar outline, month by month (#27).

    PYTHONPATH=src python explore/muhos/s1_clearing_dates.py [--cache data/stacks] [--all-dates]

Sentinel-1 (C-band, 30 m, burst T160_341904_IW3) has passes every 6-12 days since May 2025, so it sees the spring 2026
felling that NISAR (from 25 Jun 2026) misses. Per pixel: VH after a 5 x 5 boxcar, in dB, minus that pass's scene
median (wet, dry and frozen days move the whole window together), compared with the median of the snow-free
Jun-Sep 2025 passes. A pixel counts as felled if its median drop over Jun-Oct 2026 is at least DROP_DB; it is dated by
the first pass from which it stays at least half that far down for PERSIST passes. The site's skip dates
(pipeline.py: May 2025, Oct 2025 - 6 Mar 2026, Nov 2026) are left out unless --all-dates is given (snow and frozen
ground change C-band backscatter; see the quick-looks).
Prints felled hectares inside clearing_scope.geojson and in the search box around it, by month first seen.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import shapely
from pyproj import Geod, Transformer
from rasterio import features
from rasterio.transform import Affine
from scipy import ndimage
from shapely.geometry import box, shape

from sarwatch.pipeline import REPO_ROOT, SITES, _skip_spans, load_stack

DROP_DB = 1.5    # C-band VH: felling removes the canopy volume, but slash and stumps keep part of the echo
PERSIST = 3      # passes (18-36 days) the drop must hold to date it
BOXCAR = 5
SEARCH = (26.065, 64.815, 26.150, 64.860)  # same box as clearing_scope.py
SCOPE = REPO_ROOT / "explore" / "muhos" / "clearing_scope.geojson"


def smooth_db(power, k=BOXCAR):
    ok = np.isfinite(power) & (power > 0)
    total = ndimage.uniform_filter(np.where(ok, power, 0.0), k)
    weight = ndimage.uniform_filter(ok.astype(float), k)
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10 * np.log10(total / weight)


def rasterize(geom_ll, transform, epsg, shp):
    to = Transformer.from_crs(4326, epsg, always_xy=True)
    geom = shapely.transform(geom_ll, lambda xy: np.column_stack(to.transform(xy[:, 0], xy[:, 1])))
    return features.rasterize([(geom, 1)], out_shape=shp, transform=Affine(*transform)).astype(bool)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--cache", default=str(REPO_ROOT / "data" / "stacks"))
    p.add_argument("--all-dates", action="store_true", help="keep the passes the site skips")
    args = p.parse_args(argv)
    stack, dates, transform, epsg = load_stack(Path(args.cache) / "muhos" / "s1")
    spans = [] if args.all_dates else _skip_spans(SITES["muhos"])
    keep = [i for i, d in enumerate(dates) if not any(lo <= d <= hi for lo, hi in spans)]
    dates = [dates[i] for i in keep]
    vh = np.stack([smooth_db(stack["VH"][i]) for i in keep])
    vh -= np.nanmedian(vh, axis=(1, 2))[:, None, None]
    base = np.nanmedian(vh[[i for i, d in enumerate(dates) if d.year == 2025 and 6 <= d.month <= 9]], axis=0)
    late = np.nanmedian(vh[[i for i, d in enumerate(dates) if d.year == 2026 and 6 <= d.month <= 10]], axis=0)
    felled = late - base <= -DROP_DB

    drop = (vh - base) <= -DROP_DB / 2
    run = drop.copy()
    for k in range(1, PERSIST):
        run[:-k] &= drop[k:]
    first = np.where(run.any(axis=0), run.argmax(axis=0), -1)

    shp = felled.shape
    scope = shape(json.loads(SCOPE.read_text(encoding="utf-8"))["features"][0]["geometry"])
    areas = {"inside the outline": rasterize(scope, transform, epsg, shp),
             "search box": rasterize(box(*SEARCH), transform, epsg, shp)}
    a, b, _, d, e, _ = transform
    px_ha = abs(a * e - b * d) / 1e4  # UTM at 26 E: scale factor ~0.9997, close enough
    geod = Geod(ellps="WGS84")
    print(f"{len(dates)} passes {dates[0]} .. {dates[-1]} ({'all dates' if args.all_dates else 'skip dates left out'}); "
          f"outline {abs(geod.geometry_area_perimeter(scope)[0]) / 1e4:.0f} ha")
    for name, where in areas.items():
        sel = felled & where & (first >= 0)
        months = Counter(f"{dates[i]:%Y-%m}" for i in first[sel])
        print(f"{name}: felled {np.count_nonzero(felled & where) * px_ha:.0f} ha of {where.sum() * px_ha:.0f} ha")
        total = 0.0
        for m in sorted(months):
            total += months[m] * px_ha
            print(f"  first seen {m}: {months[m] * px_ha:6.1f} ha  (running {total:6.1f} ha)")
    return dates, first, felled, areas


if __name__ == "__main__":
    main()
