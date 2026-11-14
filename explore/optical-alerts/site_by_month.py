"""Vegetation loss by month of first detection in a site window, from NASA's optical alerts (issue #44, R6 step 1).

    python explore/optical-alerts/site_by_month.py muhos      # tables + explore/optical-alerts/muhos_alerts.png
    python explore/optical-alerts/site_by_month.py agroparc   # 2023 -> today

Reads the alert state at the end of each month from the one MGRS tile that covers the site window
(sarwatch.distalert), keeps each pixel's earliest confirmed first-detection date (distalert.combine: a "finished"
alert is overwritten by a later one, which would move its date), then prints hectares per month of first detection
for the window, a 3 km circle around the site centre and the largest connected patch of confirmed loss ("block"),
plus what the reads cost. Needs an Earthdata token ($EARTHDATA_TOKEN or the repo's .env). Nothing is cached: a run
reads about 1 MB per year of snapshots.
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from sarwatch import distalert as da  # noqa: E402

SITES = {
    "muhos": {"label": "Muhos", "bbox": (25.94, 64.80, 26.15, 64.89), "centre": (26.044, 64.843),
              "start": "2025-10-01", "block_from": "2026-01-01", "map_from": "2026-03-01"},
    "agroparc": {"label": "Agroparc Penedès", "bbox": (1.79, 41.41, 1.91, 41.49), "centre": (1.85, 41.45),
                 "start": "2023-01-01", "block_from": "2023-01-01", "map_from": "2023-01-01"},
}
RADIUS_M = 3000
OUT_DIR = Path(__file__).resolve().parent


def largest_patch(alerts, since) -> np.ndarray:
    """The largest connected patch of confirmed alerts first seen on or after `since`, gaps of up to ~3 pixels
    closed, holes filled."""
    from scipy import ndimage

    hit = np.isin(alerts.status, da.CONFIRMED) & (alerts.first_date >= np.datetime64(since))
    closed = ndimage.binary_closing(hit, structure=np.ones((3, 3)), iterations=3)
    labels, n = ndimage.label(closed)
    if n == 0:
        return np.zeros_like(hit)
    sizes = ndimage.sum(closed, labels, range(1, n + 1))
    return ndimage.binary_fill_holes(labels == int(np.argmax(sizes)) + 1)


def centroid_lonlat(alerts, mask) -> tuple:
    from rasterio.warp import transform as warp_transform

    rows, cols = np.nonzero(mask)
    a, _, c, _, e, f = alerts.transform
    lon, lat = warp_transform(f"EPSG:{alerts.epsg}", "EPSG:4326", [c + (cols.mean() + 0.5) * a],
                              [f + (rows.mean() + 0.5) * e])
    return lon[0], lat[0]


def table(title, by_month, since=None) -> str:
    rows = [f"**{title}**", "", "| month | confirmed ha | provisional ha | first-only ha |", "|---|---:|---:|---:|"]
    total = {"confirmed": 0.0, "provisional": 0.0, "first": 0.0}
    for month, v in by_month.items():
        if since and month < since:
            continue
        rows.append(f"| {month} | {v['confirmed']:.1f} | {v['provisional']:.1f} | {v['first']:.1f} |")
        for k in total:
            total[k] += v[k]
    rows.append(f"| **total** | **{total['confirmed']:.1f}** | **{total['provisional']:.1f}** | "
                f"**{total['first']:.1f}** |")
    return "\n".join(rows)


# ---------------------------------------------------------------- picture

# Ordinal ramp, dark (early) -> light (late): monotone lightness, adjacent steps distinguishable, colour-blind safe
# (viridis samples). A one-hue ramp cannot hold seven visibly different steps.
RAMP = ["#440154", "#443983", "#31688e", "#21918c", "#35b779", "#90d743", "#fde725"]
LAND, WATER, OLDER, INK, PANEL = "#a9a8a4", "#8c8b87", "#dcdbd7", "#1f1f1d", "#fcfcfb"


def _rgb(hex_colour):
    return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))


def month_bins(months, map_from) -> list:
    """Up to len(RAMP) colour bins over the months on the map: one month each; a few months too many -> the
    earliest ones merged into the first bin; many more (several years) -> one bin per year."""
    months = sorted(m for m in set(months) if m >= map_from)
    extra = len(months) - len(RAMP)
    if extra <= 0:
        return [[m] for m in months]
    if extra <= 2:
        return [months[:extra + 1]] + [[m] for m in months[extra + 1:]]
    years = sorted({m[:4] for m in months})
    return [[m for m in months if m.startswith(y)] for y in years][-len(RAMP):]


def _bin_label(group) -> str:
    from datetime import datetime

    names = [datetime.strptime(m, "%Y-%m").strftime("%b %Y") for m in group]
    if len(names) == 1:
        return names[0]
    if len(names) == 12 or (names[0][4:] == names[-1][4:] and len(names) > 6):
        return names[0][4:]  # a whole year
    return f"{names[0][:3]}-{names[-1]}"


def draw_png(path, site, alerts, water, block, circle_centre, by_block, bins, footer):
    from PIL import Image, ImageDraw, ImageFont
    from rasterio.warp import transform as warp_transform

    k = 2  # screen pixels per 30 m pixel
    rows, cols = alerts.status.shape
    rgb = np.empty((rows, cols, 3), np.uint8)
    rgb[...] = _rgb(LAND)
    rgb[water] = _rgb(WATER)
    conf = np.isin(alerts.status, da.CONFIRMED) & ~np.isnat(alerts.first_date)
    months = alerts.first_date.astype("datetime64[M]").astype(str)
    first_map_month = bins[0][0] if bins else "9999-12"
    rgb[conf & (months < first_map_month)] = _rgb(OLDER)
    for colour, group in zip(RAMP[:len(bins)] if len(bins) == len(RAMP) else _spread(len(bins)), bins):
        rgb[conf & np.isin(months, group)] = _rgb(colour)
    big = np.kron(rgb, np.ones((k, k, 1), np.uint8))
    edge = np.kron(block, np.ones((k, k), bool))
    inner = edge.copy()
    inner[1:-1, 1:-1] = edge[1:-1, 1:-1] & edge[:-2, 1:-1] & edge[2:, 1:-1] & edge[1:-1, :-2] & edge[1:-1, 2:]
    big[edge & ~inner] = _rgb(INK)

    margin, legend_w, title_h, footer_h = 16, 330, 56, 46
    W, H = margin * 3 + cols * k + legend_w, title_h + rows * k + footer_h + margin
    img = Image.new("RGB", (W, H), _rgb(PANEL))
    img.paste(Image.fromarray(big), (margin, title_h))
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=15)
    small = ImageFont.load_default(size=13)
    bold = ImageFont.load_default(size=19)
    ox, oy = margin, title_h
    d.text((margin, 12), f"{site['label']}: vegetation loss by month of first detection", fill=_rgb(INK), font=bold)
    d.text((margin, 35), "NASA OPERA DIST-ALERT-HLS (Landsat + Sentinel-2), confirmed alerts, 30 m pixels",
           fill=_rgb(INK), font=small)

    # site centre + 3 km circle (dashed)
    a, _, c, _, e, f = alerts.transform
    xs, ys = warp_transform("EPSG:4326", f"EPSG:{alerts.epsg}", [circle_centre[0]], [circle_centre[1]])
    px, py = ox + (xs[0] - c) / a * k, oy + (ys[0] - f) / e * k
    r = RADIUS_M / a * k
    for i in range(0, 120, 2):
        t0, t1 = 2 * math.pi * i / 120, 2 * math.pi * (i + 1) / 120
        d.line([(px + r * math.cos(t0), py + r * math.sin(t0)), (px + r * math.cos(t1), py + r * math.sin(t1))],
               fill=_rgb(INK), width=2)
    d.line([(px - 9, py), (px + 9, py)], fill=_rgb(INK), width=3)
    d.line([(px, py - 9), (px, py + 9)], fill=_rgb(INK), width=3)
    d.text((px + 8, py + 6), "given site centre", fill=_rgb(INK), font=small)

    # north arrow
    nx, ny = ox + 22, oy + 18
    d.polygon([(nx, ny), (nx - 8, ny + 20), (nx + 8, ny + 20)], fill=_rgb(INK))
    d.text((nx - 5, ny + 22), "N", fill=_rgb(INK), font=font)

    # scale bar: 2 km in 1 km segments
    seg = 1000 / a * k
    sx, sy = ox + 14, oy + rows * k - 26
    d.rectangle([sx - 6, sy - 20, sx + 2 * seg + 30, sy + 12], fill=_rgb(PANEL))
    for i in range(2):
        d.rectangle([sx + i * seg, sy, sx + (i + 1) * seg, sy + 7], fill=_rgb(INK if i == 0 else PANEL),
                    outline=_rgb(INK))
    for i, label in enumerate(("0", "1", "2 km")):
        d.text((sx + i * seg - 3, sy - 18), label, fill=_rgb(INK), font=small)

    # legend
    lx, ly = ox + cols * k + margin, oy + 4
    d.text((lx, ly), "First detected", fill=_rgb(INK), font=font)
    d.text((lx + 175, ly), "ha in block", fill=_rgb(INK), font=small)
    ly += 26
    colours = RAMP if len(bins) == len(RAMP) else _spread(len(bins))
    for colour, group in zip(colours, bins):
        d.rectangle([lx, ly, lx + 22, ly + 16], fill=_rgb(colour))
        d.text((lx + 32, ly), _bin_label(group), fill=_rgb(INK), font=font)
        ha = sum(by_block.get(m, {}).get("confirmed", 0.0) for m in group)
        d.text((lx + 175, ly), f"{ha:6.1f}", fill=_rgb(INK), font=font)
        ly += 24
    d.rectangle([lx, ly, lx + 22, ly + 16], fill=_rgb(OLDER), outline=_rgb(LAND))
    d.text((lx + 32, ly), f"before {_bin_label([first_map_month])}", fill=_rgb(INK), font=font)
    ly += 34
    d.rectangle([lx, ly + 4, lx + 22, ly + 12], outline=_rgb(INK), width=2)
    d.text((lx + 32, ly), "largest patch (\"block\")", fill=_rgb(INK), font=font)
    ly += 24
    d.ellipse([lx + 3, ly + 1, lx + 19, ly + 17], outline=_rgb(INK), width=2)
    d.text((lx + 32, ly), f"{RADIUS_M // 1000} km around the given centre", fill=_rgb(INK), font=font)
    ly += 24
    d.rectangle([lx, ly, lx + 22, ly + 16], fill=_rgb(WATER))
    d.text((lx + 32, ly), "water", fill=_rgb(INK), font=font)
    ly += 34
    for line in ("Only confirmed alerts are coloured:", "provisional and single-look alerts", "are left out.",
                 "", "UTM grid, north up (< 1° from", "true north)."):
        d.text((lx, ly), line, fill=_rgb(INK), font=small)
        ly += 18
    d.text((margin, oy + rows * k + 10), footer, fill=_rgb(INK), font=small)
    img.save(path, optimize=True)


def _spread(n) -> list:
    """n colours spread over RAMP (for fewer bins than ramp steps)."""
    if n <= 1:
        return RAMP[-1:] * n
    return [RAMP[round(i * (len(RAMP) - 1) / (n - 1))] for i in range(n)]


# ---------------------------------------------------------------- main

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("site", choices=sorted(SITES))
    p.add_argument("--start", help="first month to read (default: per site)")
    p.add_argument("--end", help="last day to read (default: today)")
    p.add_argument("--no-png", action="store_true")
    args = p.parse_args(argv)
    site = SITES[args.site]
    bbox, start = site["bbox"], args.start or site["start"]

    t0 = time.perf_counter()
    granules = da.search(bbox, start, args.end)
    t_search = time.perf_counter() - t0
    tile = da.pick_tile(granules, bbox)
    snaps = da.month_ends(granules, tile)
    print(f"{len(granules)} granules over the window ({sorted({g.tile for g in granules})}), "
          f"search {t_search:.1f} s; tile {tile}: {len(snaps)} month-end snapshots, "
          f"{snaps[0].start.date()} -> {snaps[-1].start.date()}")

    t1 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as pool:  # 4 snapshots at a time, 2 layers each
        states = list(pool.map(lambda g: da.read_window(g, bbox, workers=2), snaps))
    t_read = time.perf_counter() - t1
    newest = states[-1]
    alerts = da.combine(states)
    rows, cols = alerts.status.shape
    print(f"read {alerts.cost['files']} files, window {rows} x {cols} px (EPSG:{alerts.epsg}), "
          f"~{alerts.cost['bytes'] / 1e6:.2f} MB, {t_read:.0f} s wall clock "
          f"({alerts.cost['seconds'] / len(snaps):.1f} s per snapshot, 4 in parallel); newest state: {newest.granule}")

    circle = da.circle_mask(alerts, *site["centre"], RADIUS_M)
    block = largest_patch(alerts, site["block_from"])
    blon, blat = centroid_lonlat(alerts, block)
    from rasterio.warp import transform as warp_transform
    (cx,), (cy,) = warp_transform("EPSG:4326", f"EPSG:{alerts.epsg}", [site["centre"][0]], [site["centre"][1]])
    (bx,), (by_,) = warp_transform("EPSG:4326", f"EPSG:{alerts.epsg}", [blon], [blat])
    block_ha = block.sum() * alerts.pixel_ha
    print(f"block: {block_ha:.0f} ha outline, centroid lon {blon:.4f} lat {blat:.4f}, "
          f"{math.hypot(bx - cx, by_ - cy) / 1000:.1f} km from the site centre {site['centre']}")
    block_circle = da.circle_mask(alerts, blon, blat, RADIUS_M)

    since = site["block_from"][:7]
    by_block = da.hectares_by_month(alerts, block)
    print()
    print(table(f"Window {bbox} ({rows * cols * alerts.pixel_ha:.0f} ha)", da.hectares_by_month(alerts), since))
    print()
    print(table(f"{RADIUS_M // 1000} km circle around the site centre {site['centre']}",
                da.hectares_by_month(alerts, circle), since))
    print()
    print(table(f"Largest patch (block, {block_ha:.0f} ha outline)", by_block, since))
    print()
    print(table(f"{RADIUS_M // 1000} km circle around the block centroid ({blon:.3f}, {blat:.3f})",
                da.hectares_by_month(alerts, block_circle), since))
    print()
    print(table("Block, newest state only (no snapshots): dates of the newest alert per pixel",
                da.hectares_by_month(newest, block), since))
    print()
    cum, line = 0.0, []
    for m, v in by_block.items():
        if m >= since:
            cum += v["confirmed"]
            line.append(f"{m}: {cum:.0f}")
    print("Block, confirmed loss piling up (cumulative ha by month of first detection): " + " | ".join(line))
    strong = sum(v["confirmed"] for m, v in da.hectares_by_month(newest, block, strong_only=True).items()
                 if m >= since)
    print(f"Block, newest state: {strong:.0f} ha confirmed with a loss >= 50% of the vegetation cover")

    if not args.no_png:
        summer = [g for g in granules if g.tile == tile and g.start.month in (6, 7, 8)
                  and g.extra.get("coverage", 0) >= 90] or [g for g in granules if g.tile == tile]
        clear = min(summer, key=lambda g: g.extra.get("cloud", 100))
        mask = da.read_window(clear, bbox, layers=("DATA-MASK",)).layers["DATA-MASK"]
        bins = month_bins(list(da.hectares_by_month(alerts)), site["map_from"][:7])
        path = OUT_DIR / f"{args.site}_alerts.png"
        footer = (f"Tile {tile}, {len(snaps)} monthly states to {newest.acquired:%d %b %Y}; earliest confirmed "
                  f"date per pixel. Water: {clear.start:%d %b %Y} scene. Data: NASA OPERA / LP DAAC.")
        draw_png(path, site, alerts, mask == 2, block, site["centre"], by_block, bins, footer)
        print(f"\nwrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
