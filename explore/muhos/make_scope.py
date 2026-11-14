"""The outline of the Muhos clear-cut from NASA's optical alerts (issue #44, R6 step 2a).

    python explore/muhos/make_scope.py        # -> clearing_scope.geojson, clearing_scope.png, table on stdout

Reads the alert state at the end of each month (OPERA DIST-ALERT-HLS, tile 35WMM) as explore/optical-alerts/
site_by_month.py does, keeps each pixel's earliest confirmed first-detection date of 2026, takes the largest compact
patch of confirmed alerts (gaps of up to ~3 pixels closed, holes filled), simplifies its outline to <= 200 vertices
and draws the monthly regions (sarwatch.distregions) with the outline on top. Needs an Earthdata token
($EARTHDATA_TOKEN or the repo's .env); reads under 1 MB.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from sarwatch import distalert as da  # noqa: E402
from sarwatch import distregions as dr  # noqa: E402

spec = importlib.util.spec_from_file_location("site_by_month", ROOT / "explore" / "optical-alerts" / "site_by_month.py")
sbm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sbm)

OUT = Path(__file__).resolve().parent
SITE = sbm.SITES["muhos"]
MAX_VERTICES = 200
K = 4  # screen pixels per 30 m pixel


def outline(alerts, patch) -> dict:
    """Outer outline of the patch in lon/lat, simplified to <= MAX_VERTICES vertices, holes dropped."""
    import shapely
    from pyproj import Transformer
    from rasterio import features
    from rasterio.transform import Affine
    from shapely.geometry import Polygon, shape

    shapes = [shape(g) for g, _ in features.shapes(patch.astype(np.uint8), mask=patch,
                                                   transform=Affine(*alerts.transform[:3], *alerts.transform[3:]),
                                                   connectivity=8)]
    geom = max(shapes, key=lambda p: p.area)  # the patch is one connected piece
    geom = Polygon(geom.exterior)
    tol = 5.0
    while len(shapely.get_coordinates(geom.simplify(tol, preserve_topology=True))) - 1 > MAX_VERTICES:
        tol *= 1.2
    simple = geom.simplify(tol, preserve_topology=True)
    tr = Transformer.from_crs(alerts.epsg, 4326, always_xy=True)
    ll = shapely.transform(simple, lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1])))
    return dr.to_geojson(ll, 6)


def draw(path, alerts, regions, scope_ll, footer):
    from PIL import Image, ImageDraw, ImageFont
    from pyproj import Transformer

    patch_rows, patch_cols = np.nonzero(np.isin(alerts.status, da.CONFIRMED) & ~np.isnat(alerts.first_date))
    a, _, c, _, e, f = alerts.transform
    ring = np.array(scope_ll["coordinates"][0])
    tr = Transformer.from_crs(4326, alerts.epsg, always_xy=True)
    xs, ys = tr.transform(ring[:, 0], ring[:, 1])
    pad = 12
    col0 = max(int((min(xs) - c) / a) - pad, 0)
    col1 = min(int((max(xs) - c) / a) + pad, alerts.status.shape[1])
    row0 = max(int((f - max(ys)) / -e) - pad, 0)
    row1 = min(int((f - min(ys)) / -e) + pad, alerts.status.shape[0])
    rows, cols = row1 - row0, col1 - col0
    rgb = np.empty((rows, cols, 3), np.uint8)
    rgb[...] = sbm._rgb(sbm.LAND)
    months = sorted({r.month for r in regions})
    colours = dict(zip(months, sbm._ramp(len(months))))
    months_grid = alerts.first_date.astype("datetime64[M]").astype(str)
    conf = np.isin(alerts.status, da.CONFIRMED) & ~np.isnat(alerts.first_date)
    for m, colour in colours.items():  # all confirmed pixels, by month
        rgb[(conf & (months_grid == m))[row0:row1, col0:col1]] = sbm._rgb(colour)
    big = np.kron(rgb, np.ones((K, K, 1), np.uint8))

    margin, legend_w, title_h, footer_h = 16, 320, 56, 40
    img = Image.new("RGB", (margin * 3 + cols * K + legend_w, title_h + rows * K + footer_h + margin),
                    sbm._rgb(sbm.PANEL))
    img.paste(Image.fromarray(big), (margin, title_h))
    d = ImageDraw.Draw(img)
    font, small, bold = (ImageFont.load_default(size=s) for s in (15, 13, 19))
    ink = sbm._rgb(sbm.INK)
    ox, oy = margin, title_h
    d.text((margin, 12), "Muhos clear-cut: confirmed vegetation loss by month of first detection", fill=ink, font=bold)
    d.text((margin, 35), "NASA OPERA DIST-ALERT-HLS (Landsat + Sentinel-2), 2026, 30 m pixels; line = scope outline",
           fill=ink, font=small)
    pts = [(ox + (x - c) / a * K - col0 * K, oy + (y - f) / e * K - row0 * K) for x, y in zip(xs, ys)]
    d.line(pts, fill=ink, width=3)
    nx, ny = ox + 22, oy + 18
    d.polygon([(nx, ny), (nx - 8, ny + 20), (nx + 8, ny + 20)], fill=ink)
    d.text((nx - 5, ny + 22), "N", fill=ink, font=font)
    seg = 500 / a * K  # scale bar: 1 km in two 500 m segments
    sx, sy = ox + 14, oy + rows * K - 26
    d.rectangle([sx - 6, sy - 20, sx + 2 * seg + 40, sy + 12], fill=sbm._rgb(sbm.PANEL))
    for i in range(2):
        d.rectangle([sx + i * seg, sy, sx + (i + 1) * seg, sy + 7], fill=ink if i == 0 else sbm._rgb(sbm.PANEL),
                    outline=ink)
    for i, label in enumerate(("0", "0.5", "1 km")):
        d.text((sx + i * seg - 3, sy - 18), label, fill=ink, font=small)
    lx, ly = ox + cols * K + margin, oy + 4
    d.text((lx, ly), "First detected", fill=ink, font=font)
    d.text((lx + 120, ly), "ha, regions >= 1 ha", fill=ink, font=small)
    ly += 26
    for m, colour in colours.items():
        d.rectangle([lx, ly, lx + 22, ly + 16], fill=sbm._rgb(colour))
        d.text((lx + 32, ly), sbm.bin_label([m]), fill=ink, font=font)
        d.text((lx + 120, ly), f"{sum(r.area_ha for r in regions if r.month == m):6.1f}", fill=ink, font=font)
        ly += 24
    d.text((margin, oy + rows * K + 10), footer, fill=ink, font=small)
    img.save(path, optimize=True)


def main():
    bbox = SITE["bbox"]
    granules = da.search(bbox, SITE["start"])
    tile = da.pick_tile(granules, bbox)
    snaps = da.month_ends(granules, tile)
    with ThreadPoolExecutor(max_workers=4) as pool:
        states = list(pool.map(lambda g: da.read_window(g, bbox, workers=2), snaps))
    alerts = da.combine(sbm.within(states, SITE["since"]))
    state_dates = [s.acquired for s in states]
    patch = sbm.largest_patch(alerts)
    scope = outline(alerts, patch)
    from shapely.geometry import shape
    from pyproj import Geod

    poly = shape(scope)
    area = abs(Geod(ellps="WGS84").geometry_area_perimeter(poly)[0]) / 1e4
    pixel_ha = float(patch.sum() * alerts.pixel_ha)
    n_vertices = len(scope["coordinates"][0]) - 1
    regions = dr.regions_by_month(alerts, state_dates, mask=patch)
    date_range = [str(min(r.first_date for r in regions)), str(alerts.acquired)]
    feature = {"type": "Feature", "geometry": scope, "properties": {
        "area_ha": round(area, 1),
        "source": f"NASA OPERA DIST-ALERT-HLS v1 (Landsat + Sentinel-2, 30 m), tile {tile}",
        "method": ("largest connected patch of confirmed vegetation-loss alerts first detected in 2026 on the month-end "
                   "states, gaps of up to ~3 pixels closed, holes dropped, outline simplified to <= 200 vertices"),
        "date_range": date_range}}
    (OUT / "clearing_scope.geojson").write_text(json.dumps(feature, indent=1), encoding="utf-8")
    print(f"scope: {n_vertices} vertices, geodesic {area:.1f} ha, patch pixel area {pixel_ha:.1f} ha, "
          f"bbox {[round(v, 5) for v in poly.bounds]}")

    print("\n| month | regions | ha |\n|---|---:|---:|")
    for m in sorted({r.month for r in regions}):
        rs = [r for r in regions if r.month == m]
        print(f"| {m} | {len(rs)} | {sum(r.area_ha for r in rs):.1f} |")
    print(f"| **total** | **{len(regions)}** | **{sum(r.area_ha for r in regions):.1f}** |")
    footer = (f"Tile {tile}, {len(snaps)} monthly states to {alerts.acquired:%d %b %Y}; scope {area:.0f} ha "
              f"(outline), alerts of 2026. Data: NASA OPERA / LP DAAC.")
    draw(OUT / "clearing_scope.png", alerts, regions, scope, footer)
    print("\nwrote explore/muhos/clearing_scope.geojson and clearing_scope.png")


if __name__ == "__main__":
    main()
