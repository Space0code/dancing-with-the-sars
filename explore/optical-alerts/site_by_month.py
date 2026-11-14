"""Vegetation loss by month of first detection in a site window, from NASA's optical alerts (issue #44, R6 step 1).

    python explore/optical-alerts/site_by_month.py muhos      # tables + explore/optical-alerts/muhos_alerts.png
    python explore/optical-alerts/site_by_month.py agroparc   # 2023 -> today, per year + 2025-26 by month

Reads the alert state at the end of each month from the one MGRS tile that covers the site window
(sarwatch.distalert). Alerts first detected before the site's `since` date are dropped, then each pixel keeps its
earliest confirmed first-detection date (distalert.combine: a "finished" alert is overwritten by a later one, which
would move its date). Prints hectares per month of first detection for the window, a 3 km circle around the given
site centre and the largest connected patch of confirmed loss ("block"), a per-year table when the run spans several
years (each year's alerts counted on their own: fields are alerted again every year), and what the reads cost.
Needs an Earthdata token ($EARTHDATA_TOKEN or the repo's .env). Nothing is cached: ~0.35 MB per year of snapshots.
"""
from __future__ import annotations

import argparse
import dataclasses
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from sarwatch import distalert as da  # noqa: E402

SITES = {  # start: first snapshot month to read; since: alerts first detected from here on are counted and mapped
    "muhos": {"label": "Muhos", "bbox": (25.94, 64.80, 26.15, 64.89), "centre": (26.044, 64.843),
              "start": "2025-10-01", "since": "2026-01-01"},
    "agroparc": {"label": "Agroparc Penedes", "bbox": (1.79, 41.41, 1.91, 41.49), "centre": (1.85, 41.45),
                 "start": "2023-01-01", "since": "2025-01-01"},  # earthworks 2025-27 (kb/project-context.md)
}
RADIUS_M = 3000
OUT_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------- analysis

def within(states, lo, hi=None) -> list:
    """Copies of the snapshots with every alert first detected outside [lo, hi) removed (status 0, date NaT)."""
    out = []
    for a in states:
        keep = a.first_date >= np.datetime64(lo, "D")
        if hi is not None:
            keep &= a.first_date < np.datetime64(hi, "D")
        out.append(dataclasses.replace(a, status=np.where(keep, a.status, 0).astype(a.status.dtype),
                                       first_date=np.where(keep, a.first_date, np.datetime64("NaT", "D")), layers={}))
    return out


def confirmed_ha_by_year(states, years, regions: dict) -> dict:
    """{year: {region name: confirmed ha}}, each calendar year's alerts counted on their own (a pixel at most once
    per year), so a field alerted again every year counts every year."""
    out = {}
    for y in years:
        alerts = da.combine(within(states, f"{y}-01-01", f"{y + 1}-01-01"))
        conf = np.isin(alerts.status, da.CONFIRMED) & ~np.isnat(alerts.first_date)
        out[y] = {name: float((conf & region).sum() * alerts.pixel_ha) for name, region in regions.items()}
    return out


def largest_patch(alerts) -> np.ndarray:
    """The largest connected patch of confirmed alerts, gaps of up to ~3 pixels closed, holes filled."""
    from scipy import ndimage

    hit = np.isin(alerts.status, da.CONFIRMED) & ~np.isnat(alerts.first_date)
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


def distance_km(epsg, p, q) -> float:
    from rasterio.warp import transform as warp_transform

    xs, ys = warp_transform("EPSG:4326", f"EPSG:{epsg}", [p[0], q[0]], [p[1], q[1]])
    return math.hypot(xs[1] - xs[0], ys[1] - ys[0]) / 1000


def table(title, by_month) -> str:
    rows = [f"**{title}**", "", "| month | confirmed ha | provisional ha | first-only ha |", "|---|---:|---:|---:|"]
    total = dict.fromkeys(da.CLASSES, 0.0)
    for month, v in by_month.items():
        rows.append(f"| {month} | {v['confirmed']:.1f} | {v['provisional']:.1f} | {v['first']:.1f} |")
        for k in total:
            total[k] += v[k]
    rows.append(f"| **total** | **{total['confirmed']:.1f}** | **{total['provisional']:.1f}** | "
                f"**{total['first']:.1f}** |")
    return "\n".join(rows)


# ---------------------------------------------------------------- picture

# Ordinal ramp, dark (early) -> light (late): monotone lightness and clear steps (viridis samples, colour-blind safe).
# One hue cannot hold seven visibly different steps; the legend and the tables carry the exact months.
RAMP = ["#440154", "#443983", "#31688e", "#21918c", "#35b779", "#90d743", "#fde725"]
LAND, WATER, INK, PANEL = "#a9a8a4", "#8c8b87", "#1f1f1d", "#fcfcfb"


def _rgb(hex_colour):
    return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))


def month_bins(months) -> list:
    """At most len(RAMP) colour bins over the months: one month each; one or two months too many -> the earliest
    merged into the first bin; more -> calendar periods of 2, 3, 6 or 12 months, the shortest that fits."""
    months = sorted(set(months))
    extra = len(months) - len(RAMP)
    if extra <= 0:
        return [[m] for m in months]
    if extra <= 2:
        return [months[:extra + 1]] + [[m] for m in months[extra + 1:]]
    for n in (2, 3, 6, 12):
        groups = {}
        for m in months:
            groups.setdefault((m[:4], (int(m[5:]) - 1) // n), []).append(m)
        if len(groups) <= len(RAMP):
            break
    return list(groups.values())[-len(RAMP):]


def bin_label(group) -> str:
    names = [datetime.strptime(m, "%Y-%m").strftime("%b %Y") for m in group]
    if len(names) == 1:
        return names[0]
    return f"{names[0][:3]}-{names[-1]}"


def _ramp(n) -> list:
    """n colours spread over RAMP, always including both ends."""
    if n <= 1:
        return RAMP[-1:] * n
    return [RAMP[round(i * (len(RAMP) - 1) / (n - 1))] for i in range(n)]


def draw_png(path, site, alerts, water, block, by_block, bins, footer):
    from PIL import Image, ImageDraw, ImageFont
    from rasterio.warp import transform as warp_transform

    k = 2  # screen pixels per 30 m pixel
    rows, cols = alerts.status.shape
    rgb = np.empty((rows, cols, 3), np.uint8)
    rgb[...] = _rgb(LAND)
    rgb[water] = _rgb(WATER)
    conf = np.isin(alerts.status, da.CONFIRMED) & ~np.isnat(alerts.first_date)
    months = alerts.first_date.astype("datetime64[M]").astype(str)
    colours = _ramp(len(bins))
    for colour, group in zip(colours, bins):
        rgb[conf & np.isin(months, group)] = _rgb(colour)
    big = np.kron(rgb, np.ones((k, k, 1), np.uint8))
    edge = np.kron(block, np.ones((k, k), bool))
    inner = edge.copy()
    inner[1:-1, 1:-1] = edge[1:-1, 1:-1] & edge[:-2, 1:-1] & edge[2:, 1:-1] & edge[1:-1, :-2] & edge[1:-1, 2:]
    big[edge & ~inner] = _rgb(INK)

    margin, legend_w, title_h, footer_h = 16, 330, 56, 46
    img = Image.new("RGB", (margin * 3 + cols * k + legend_w, title_h + rows * k + footer_h + margin), _rgb(PANEL))
    img.paste(Image.fromarray(big), (margin, title_h))
    d = ImageDraw.Draw(img)
    font, small, bold = (ImageFont.load_default(size=s) for s in (15, 13, 19))
    ox, oy = margin, title_h
    d.text((margin, 12), f"{site['label']}: vegetation loss by month of first detection", fill=_rgb(INK), font=bold)
    d.text((margin, 35), "NASA OPERA DIST-ALERT-HLS (Landsat + Sentinel-2), confirmed alerts, 30 m pixels",
           fill=_rgb(INK), font=small)

    # given site centre + 3 km circle (dashed)
    a, _, c, _, e, f = alerts.transform
    xs, ys = warp_transform("EPSG:4326", f"EPSG:{alerts.epsg}", [site["centre"][0]], [site["centre"][1]])
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
    for colour, group in zip(colours, bins):
        d.rectangle([lx, ly, lx + 22, ly + 16], fill=_rgb(colour))
        d.text((lx + 32, ly), bin_label(group), fill=_rgb(INK), font=font)
        ha = sum(by_block.get(m, {}).get("confirmed", 0.0) for m in group)
        d.text((lx + 175, ly), f"{ha:6.1f}", fill=_rgb(INK), font=font)
        ly += 24
    ly += 10
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
                 "", "UTM grid, north up (< 1 degree", "from true north)."):
        d.text((lx, ly), line, fill=_rgb(INK), font=small)
        ly += 18
    d.text((margin, oy + rows * k + 10), footer, fill=_rgb(INK), font=small)
    img.save(path, optimize=True)


# ---------------------------------------------------------------- main

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("site", choices=sorted(SITES))
    p.add_argument("--end", help="last day to read (default: today)")
    p.add_argument("--no-png", action="store_true")
    args = p.parse_args(argv)
    site = SITES[args.site]
    bbox, since = site["bbox"], site["since"]

    t0 = time.perf_counter()
    granules = da.search(bbox, site["start"], args.end)
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
    cost = da.combine(states).cost
    rows, cols = newest.status.shape
    print(f"read {cost['files']} files, window {rows} x {cols} px (EPSG:{newest.epsg}), ~{cost['bytes'] / 1e6:.2f} MB, "
          f"{t_read:.0f} s wall clock ({cost['seconds'] / len(snaps):.1f} s per snapshot, 4 in parallel); "
          f"newest state: {newest.granule}")

    alerts = da.combine(within(states, since))
    circle = da.circle_mask(alerts, *site["centre"], RADIUS_M)
    block = largest_patch(alerts)
    centre = centroid_lonlat(alerts, block)
    block_ha = block.sum() * alerts.pixel_ha
    print(f"alerts counted from {since}; block: {block_ha:.0f} ha outline, centroid lon {centre[0]:.4f} "
          f"lat {centre[1]:.4f}, {distance_km(alerts.epsg, site['centre'], centre):.1f} km from the given centre")

    by_block = da.hectares_by_month(alerts, block)
    for title, by in (
            (f"Window {bbox} ({rows * cols * alerts.pixel_ha:.0f} ha)", da.hectares_by_month(alerts)),
            (f"{RADIUS_M // 1000} km circle around the given centre {site['centre']}",
             da.hectares_by_month(alerts, circle)),
            (f"Largest patch (block, {block_ha:.0f} ha outline)", by_block),
            (f"{RADIUS_M // 1000} km circle around the block centroid ({centre[0]:.3f}, {centre[1]:.3f})",
             da.hectares_by_month(alerts, da.circle_mask(alerts, *centre, RADIUS_M))),
            ("Block, newest state only (no snapshots): dates of the newest alert per pixel",
             da.hectares_by_month(within([newest], since)[0], block))):
        print(f"\n{table(title, by)}")
    cum, line = 0.0, []
    for m, v in by_block.items():
        cum += v["confirmed"]
        line.append(f"{m}: {cum:.0f}")
    print("\nBlock, confirmed loss piling up (cumulative ha by month of first detection): " + " | ".join(line))
    strong = sum(v["confirmed"] for v in da.hectares_by_month(within([newest], since)[0], block,
                                                               strong_only=True).values())
    print(f"Block, newest state: {strong:.0f} ha confirmed with a loss >= 50% of the vegetation cover")

    years = range(int(site["start"][:4]), newest.acquired.year + 1)
    if len(years) > 1:
        regions = {"window": np.ones_like(circle), "3 km circle": circle, "block": block}
        print("\n**Confirmed loss per calendar year (each year's alerts on their own)**\n")
        print("| year | " + " | ".join(f"{name} ha" for name in regions) + " |")
        print("|---|" + "---:|" * len(regions))
        for y, v in confirmed_ha_by_year(states, years, regions).items():
            print(f"| {y} | " + " | ".join(f"{v[name]:.1f}" for name in regions) + " |")

    if not args.no_png:
        summer = [g for g in granules if g.tile == tile and g.start.month in (6, 7, 8)
                  and g.extra.get("coverage", 0) >= 90] or [g for g in granules if g.tile == tile]
        clear = min(summer, key=lambda g: g.extra.get("cloud", 100))
        mask = da.read_window(clear, bbox, layers=("DATA-MASK",)).layers["DATA-MASK"]
        bins = month_bins(m for m, v in da.hectares_by_month(alerts).items() if v["confirmed"] > 0)
        path = OUT_DIR / f"{args.site}_alerts.png"
        footer = (f"Tile {tile}, {len(snaps)} monthly states to {newest.acquired:%d %b %Y}; earliest confirmed "
                  f"date per pixel since {since}. Water: {clear.start:%d %b %Y} scene. Data: NASA OPERA / LP DAAC.")
        draw_png(path, site, alerts, mask == 2, block, by_block, bins, footer)
        print(f"\nwrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
