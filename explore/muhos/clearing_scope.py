"""Outline of the Muhos data-centre clearing as NISAR sees it, for the verdict track (#27).

    PYTHONPATH=src python explore/muhos/clearing_scope.py [--cache data/stacks]

Bare ground (felled forest) has a low cross-pol (HV) echo: no canopy volume to rotate the radar wave. The outline is
the connected area below BARE_DB in the median of the last three good passes (29 Sep, 11 Oct, 23 Oct; 4 Nov is
frozen), grown from a seed inside the clearing and kept inside a search box, so neighbouring fields and bogs do not
leak in. Prints the hectares below BARE_DB inside the outline at every pass (each pass levelled to the same
scene median first), and how much of it the change detector
(app/data/muhos/changes.geojson) covers. Writes explore/muhos/clearing_scope.geojson (lon/lat).

Caveat: a bog or an old clear-cut is just as dark; what marks this area as the 2026 clearing is that it grows at its
north-east edge from 19 Jul to 24 Aug (quick-looks in explore/muhos/).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import shapely
from pyproj import Geod, Transformer
from rasterio import features
from rasterio.transform import Affine
from scipy import ndimage
from shapely.geometry import mapping, shape

from sarwatch.pipeline import REPO_ROOT, SITES, load_stack

SITE = SITES["muhos"]
BARE_DB = -11.8  # HV dB (7 x 7 boxcar): standing forest here -10.5 .. -8.5, this summer's felling -12 .. -11.5
                 # (slash and stumps keep some L-band volume), older bare ground -15 .. -13
BOXCAR = 7
SEED = (26.110, 64.838)              # lon, lat inside the clearing
SEARCH = (26.065, 64.815, 26.150, 64.860)  # lon/lat box the outline must stay in
CLOSE_PX = 3   # close gaps up to ~6 px (120 m): skid trails, strips of standing trees
OPEN_PX = 4    # then drop strips narrower than ~8 px (160 m): the road and rail corridor, river banks
WATER_HH_DB = -14.0  # HH below this is open water (the river), never part of the clearing
OUT = REPO_ROOT / "explore" / "muhos" / "clearing_scope.geojson"
GEOD = Geod(ellps="WGS84")


def smooth_db(power: np.ndarray, k: int = BOXCAR) -> np.ndarray:
    ok = np.isfinite(power) & (power > 0)
    total = ndimage.uniform_filter(np.where(ok, power, 0.0), k)
    weight = ndimage.uniform_filter(ok.astype(float), k)
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10 * np.log10(total / weight)


def lonlat_grid(transform, epsg, shape):
    rows, cols = np.mgrid[0:shape[0], 0:shape[1]] + 0.5
    a, b, c, d, e, f = transform
    x, y = c + a * cols + b * rows, f + d * cols + e * rows
    return Transformer.from_crs(epsg, 4326, always_xy=True).transform(x, y)


def geodesic_ha(geom) -> float:
    return abs(GEOD.geometry_area_perimeter(geom)[0]) / 1e4


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--cache", default=str(REPO_ROOT / "data" / "stacks"))
    args = p.parse_args(argv)
    stack, dates, transform, epsg = load_stack(Path(args.cache) / "muhos" / "nisar", bbox=SITE.bbox)
    keep = [i for i, d in enumerate(dates) if d.isoformat() not in SITE.skip_dates]
    hv = np.stack([smooth_db(stack["HV"][i]) for i in keep])
    dates = [dates[i] for i in keep]
    late = np.nanmedian(hv[-3:], axis=0)
    # wet or dry days move the whole window by up to 1 dB: level every pass to the late median's scene median
    hv -= (np.nanmedian(hv, axis=(1, 2)) - np.nanmedian(late))[:, None, None]

    lon, lat = lonlat_grid(transform, epsg, late.shape)
    w, s, e, n = SEARCH
    inside = (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)
    hh_late = np.nanmedian(np.stack([smooth_db(stack["HH"][i]) for i in keep[-3:]]), axis=0)
    water = ndimage.binary_dilation(hh_late < WATER_HH_DB, iterations=2)
    bare = (late < BARE_DB) & inside & ~water
    disk = ndimage.generate_binary_structure(2, 1)
    mask = ndimage.binary_closing(bare, structure=disk, iterations=CLOSE_PX)
    mask = ndimage.binary_opening(mask, structure=disk, iterations=OPEN_PX)
    mask = ndimage.binary_fill_holes(mask) & inside & ~water
    labels, _ = ndimage.label(mask)
    seed = np.unravel_index(np.argmin((lon - SEED[0]) ** 2 + ((lat - SEED[1]) * 2.35) ** 2), lon.shape)
    if labels[seed] == 0:
        raise SystemExit("the seed is not on bare ground: check BARE_DB / SEED")
    area = labels == labels[seed]

    affine = Affine(*transform)
    geom = shapely.union_all([shape(g) for g, v in features.shapes(area.astype(np.uint8), mask=area,
                                                                    transform=affine) if v == 1])
    to_ll = Transformer.from_crs(epsg, 4326, always_xy=True)
    geom_ll = shapely.transform(geom.simplify(10),  # 10 m: half a pixel
                                lambda xy: np.column_stack(to_ll.transform(xy[:, 0], xy[:, 1])))
    total_ha = geodesic_ha(geom_ll)
    px_ha = total_ha / area.sum()  # ground area per pixel here (EPSG:3413 is ~3.7 % larger on paper)

    per_pass = {d.isoformat(): round(float(np.count_nonzero(area & (hv[i] < BARE_DB)) * px_ha), 1)
                for i, d in enumerate(dates)}
    detected = {}
    changes = REPO_ROOT / "app" / "data" / "muhos" / "changes.geojson"
    if changes.is_file():
        for f in json.loads(changes.read_text(encoding="utf-8"))["features"]:
            overlap = shape(f["geometry"]).intersection(geom_ll)
            if not overlap.is_empty:
                kind = f'{f["properties"]["sensor"].split()[0]} {f["properties"]["type"]}'
                detected[kind] = round(detected.get(kind, 0) + geodesic_ha(overlap), 1)

    props = {
        "name": "Muhos data-centre clearing (radar outline)",
        "source": "NISAR L2 GCOV track 157 / frame 35, HV, median of the last three good passes",
        "passes": [dates[-3].isoformat(), dates[-1].isoformat()],
        "rule": f"HV < {BARE_DB} dB after a {BOXCAR} x {BOXCAR} boxcar, connected to the seed, inside {SEARCH}",
        "area_ha": round(total_ha, 1),
        "bare_ha_per_pass": per_pass,
        "detected_ha_inside": detected,
        "caveat": "Radar outline, not a survey: an older clear-cut or bog next to the site looks the same.",
    }
    fc = {"type": "FeatureCollection",
          "features": [{"type": "Feature", "properties": props,
                        "geometry": json.loads(json.dumps(mapping(geom_ll), default=float))}]}
    text = json.dumps(fc, separators=(",", ":"))
    text = __import__("re").sub(r"(-?\d+\.\d{6})\d+", r"\1", text)  # ~0.1 m precision is plenty
    OUT.write_text(text + "\n", encoding="utf-8")
    print(f"outline: {total_ha:.0f} ha -> {OUT.relative_to(REPO_ROOT)}")
    for d, ha in per_pass.items():
        print(f"  {d}: {ha:6.1f} ha below {BARE_DB} dB HV")
    print(f"  change detector inside the outline: {detected or 'nothing'}")


if __name__ == "__main__":
    main()
