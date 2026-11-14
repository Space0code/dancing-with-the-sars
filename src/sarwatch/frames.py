"""Picture frames for the app's time-lapse and before / after swipe (issue #89, format: kb/data-contract.md).

One radar picture per Sentinel-1 pass (cross-pol VH in dB, speckle-smoothed in space and over neighbouring passes, one grey stretch for every date,
with the pixels that lost echo since summer 2025 tinted orange)
and real colour photos (NASA HLS, cloud-free days only, one fixed colour stretch), all warped to one north-up grid
over the site window. Output: app/data/<site>/frames/{radar,photo}/<date>.jpg + app/data/<site>/frames.json.

    python -m sarwatch.frames muhos [--stacks data/stacks] [--no-photos] [--no-radar]

The grid is lon/lat aligned (north up; the four corners go into frames.json). Pixels are square on the ground at the
window's mid latitude (a map shows them right, and so does an image viewer), about WIDTH px across.
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from . import pipeline

log = logging.getLogger(__name__)

REPO_ROOT = pipeline.REPO_ROOT
WIDTH = 700
JPEG_QUALITY = 80
MAX_FRAME_BYTES = 60_000
SPECKLE_BOX = 3                      # mean over this many pixels square, in linear power
RADAR_RANGE_DB = (-21.0, -9.0)       # fixed grey stretch of VH (after the per-date offset): black .. white
PHOTO_RANGE = (0.0, 0.22)            # reflectance mapped to 0..1 before the gamma (same for every date)
PHOTO_GAMMA = 1.0 / 1.8
PHOTO_MIN_CLEAR = 0.9
PHOTO_MIN_GAP_DAYS = 3               # thin photo days closer together than this (keep the clearer one)
TIME_MAX_GAP_DAYS = 15               # temporal average: neighbours further away in time (snow gap) are not used
BASELINE_SPAN = (date(2025, 6, 1), date(2025, 9, 30))   # snow-free summer: per-pixel median = "unchanged" level
TINT_FROM_DB = 2.0                   # tint where VH is this far below the baseline ...
TINT_FULL_DB = 5.0                   # ... full strength at this drop
TINT_MIN_ALPHA, TINT_MAX_ALPHA = 0.35, 0.9
MIN_PATCH_HA = 1.0                   # smaller tinted patches are dropped
WATER_DB = -22.0                     # baseline darker than this = water, never tinted
TINT_RGB = (255, 70, 0)              # orange-red
RADAR_CAPTION = "Radar picture. Grey: unchanged since summer 2025. Orange: the echo from trees and plants dropped here."
PHOTO_CAPTION = "Colour images from Landsat and Sentinel-2 (NASA HLS), cloud-free days only."


@dataclass(frozen=True)
class FrameSite:
    window: tuple          # (west, south, east, north) degrees
    photo_periods: tuple   # ((first day, last day), ...) searched for photos
    photo_exclude: tuple = ()  # days dropped by eye although Fmask calls them clear (thin haze, small cloud puffs)


FRAME_SITES = {
    "muhos": FrameSite(window=(26.02, 64.795, 26.20, 64.875),
                       photo_periods=((date(2025, 6, 1), date(2025, 9, 30)), (date(2026, 3, 1), date(2026, 11, 14))),
                       photo_exclude=(date(2025, 6, 16), date(2026, 8, 9))),
}


# ---------------------------------------------------------------- grid


def grid_for(window, width: int = WIDTH) -> tuple:
    """(transform, width, height) of the common grid: window corners, square ground pixels at the mid latitude."""
    from rasterio.transform import from_bounds

    west, south, east, north = window
    ratio = (north - south) / ((east - west) * math.cos(math.radians((north + south) / 2)))
    height = int(round(width * ratio))
    return from_bounds(west, south, east, north, width, height), width, height


def corners(window) -> list:
    west, south, east, north = window
    return [[west, north], [east, north], [east, south], [west, south]]


def warp(array: np.ndarray, transform, epsg: int, dst_transform, width: int, height: int, method: str = "cubic"):
    """Resample one (rows, cols) float array onto the common grid; NaN marks no data (also in the result)."""
    from rasterio.crs import CRS
    from rasterio.transform import Affine
    from rasterio.warp import Resampling, reproject

    out = np.full((height, width), np.nan, np.float32)
    reproject(np.ascontiguousarray(array, np.float32), out, src_transform=Affine(*transform[:6]),
              src_crs=CRS.from_epsg(epsg), src_nodata=np.nan, dst_transform=dst_transform,
              dst_crs=CRS.from_epsg(4326), dst_nodata=np.nan,
              resampling=getattr(Resampling, method))
    return out


def jpeg_bytes(img: np.ndarray, quality: int = JPEG_QUALITY, max_bytes: int = MAX_FRAME_BYTES) -> bytes:
    """img: uint8 (h, w) or (h, w, 3). Quality steps down from `quality` (to 60) until the file fits max_bytes."""
    from PIL import Image

    while True:
        buf = io.BytesIO()
        Image.fromarray(img).save(buf, "JPEG", quality=quality, optimize=True)
        if buf.tell() <= max_bytes or quality <= 60:
            return buf.getvalue()
        quality -= 5


# ---------------------------------------------------------------- radar


def smooth_linear(power: np.ndarray, box: int = SPECKLE_BOX) -> np.ndarray:
    """Box mean in linear power that ignores NaN (edges and gaps average what is there)."""
    from scipy import ndimage

    ok = np.isfinite(power)
    total = ndimage.uniform_filter(np.where(ok, power, 0.0), size=box, mode="nearest")
    count = ndimage.uniform_filter(ok.astype(np.float64), size=box, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        out = total / count
    out[count < 0.5 / (box * box) + 1e-9] = np.nan
    return out.astype(np.float32)


def to_db(power: np.ndarray) -> np.ndarray:
    """Linear power -> dB; NaN where invalid or not positive."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return (10.0 * np.log10(np.where(power > 0, power, np.nan))).astype(np.float32)


def radar_stretch(db: np.ndarray, lo: float = RADAR_RANGE_DB[0], hi: float = RADAR_RANGE_DB[1]) -> np.ndarray:
    """dB -> grey in 0..1 with one fixed stretch; NaN -> 0 (black)."""
    return np.nan_to_num(np.clip((db - lo) / (hi - lo), 0.0, 1.0), nan=0.0)


def time_average(stack: list, days: list, max_gap: int = TIME_MAX_GAP_DAYS) -> list:
    """Weights 1-2-1 over (pass before, pass, pass after) in linear power. A neighbour more than max_gap days away
    (the snow gap) is left out; NaN pixels of a neighbour are ignored."""
    out = []
    for i, arr in enumerate(stack):
        num, den = 2.0 * np.nan_to_num(arr), 2.0 * np.isfinite(arr)
        for j in (i - 1, i + 1):
            if 0 <= j < len(stack) and abs((days[j] - days[i]).days) <= max_gap:
                num = num + np.nan_to_num(stack[j])
                den = den + np.isfinite(stack[j])
        with np.errstate(invalid="ignore", divide="ignore"):
            out.append(np.where(np.isfinite(arr) & (den > 0), num / den, np.nan).astype(np.float32))
    return out


def lost_alpha(drop_db: np.ndarray, baseline_db: np.ndarray, pixel_ha: float) -> np.ndarray:
    """Tint strength 0..1 per pixel: 0 below TINT_FROM_DB of drop, full at TINT_FULL_DB. Patches smaller than
    MIN_PATCH_HA and water (very dark in the baseline) get none."""
    from scipy import ndimage

    ok = np.isfinite(drop_db) & (baseline_db > WATER_DB)
    d = np.where(ok, drop_db, 0.0)
    mask = d >= TINT_FROM_DB
    labels, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n:
        size = ndimage.sum(mask, labels, index=np.arange(1, n + 1))
        mask &= np.isin(labels, 1 + np.flatnonzero(size * pixel_ha >= MIN_PATCH_HA))
    alpha = np.clip((d - TINT_FROM_DB) / (TINT_FULL_DB - TINT_FROM_DB), 0.0, 1.0)
    alpha = TINT_MIN_ALPHA + (TINT_MAX_ALPHA - TINT_MIN_ALPHA) * alpha
    return np.where(mask, alpha, 0.0).astype(np.float32)


def tint(grey: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """grey (h, w) 0..1 and alpha (h, w) -> uint8 RGB with TINT_RGB blended over the grey picture."""
    rgb = np.asarray(TINT_RGB, np.float32) / 255.0
    out = grey[..., None] * (1 - alpha[..., None]) + rgb * alpha[..., None]
    return np.round(out * 255).astype(np.uint8)


def radar_series(site_id: str, stacks, window, skip_spans) -> tuple:
    """(days, db, baseline, pixel_ha): the smoothed, per-date levelled VH of every usable pass on the common grid."""
    cache = Path(stacks) / site_id / "s1"
    days = [d for d in pipeline.cached_days(cache) if not any(lo <= d <= hi for lo, hi in skip_spans)]
    if not days:
        raise pipeline.PipelineError(f"no usable Sentinel-1 passes in {cache}")
    dst_t, w, h = grid_for(window)
    warped = []
    for day in days:
        fr = pipeline.load_frame(pipeline.cache_path(cache, day))
        warped.append(warp(smooth_linear(fr.data["VH"]), fr.transform, fr.epsg, dst_t, w, h, "bilinear"))
    warped = time_average(warped, days)
    dbs = [to_db(a) for a in warped]
    medians = np.array([np.nanmedian(a) for a in dbs])  # one offset per date: wet / dry days must not flicker
    ref = float(np.median(medians))
    log.info("radar: %d passes, per-date median %.1f .. %.1f dB (reference %.1f)", len(days), medians.min(),
             medians.max(), ref)
    dbs = [a - m + ref for a, m in zip(dbs, medians)]
    base = [a for a, d in zip(dbs, days) if BASELINE_SPAN[0] <= d <= BASELINE_SPAN[1]]
    if not base:
        raise pipeline.PipelineError("no summer 2025 passes for the baseline")
    baseline = np.nanmedian(np.stack(base), axis=0)
    west, south, east, north = window
    mid = math.radians((north + south) / 2)
    pixel_ha = (east - west) * 111_320 * math.cos(mid) / w * (north - south) * 110_574 / h / 1e4
    return days, dbs, baseline, pixel_ha


def radar_frames(site_id: str, stacks, out_dir: Path, window, skip_spans) -> list:
    """Write one JPEG per usable Sentinel-1 pass (grey radar, lost vegetation echo tinted); returns
    [{date, sensor, url}] sorted by date."""
    days, dbs, baseline, pixel_ha = radar_series(site_id, stacks, window, skip_spans)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for day, db in zip(days, dbs):
        data = jpeg_bytes(tint(radar_stretch(db), lost_alpha(baseline - db, baseline, pixel_ha)))
        (out_dir / f"{day.isoformat()}.jpg").write_bytes(data)
        frames.append({"date": day.isoformat(), "sensor": "Sentinel-1", "url": f"frames/radar/{day.isoformat()}.jpg"})
        if len(data) > MAX_FRAME_BYTES:
            log.warning("radar %s: %d KB (target %d KB)", day, len(data) // 1000, MAX_FRAME_BYTES // 1000)
    return frames


# ---------------------------------------------------------------- photos


def photo_stretch(rgb: np.ndarray) -> np.ndarray:
    """Reflectance (h, w, 3) -> uint8 colour with one fixed stretch; NaN -> mid grey."""
    lo, hi = PHOTO_RANGE
    g = np.clip((rgb - lo) / (hi - lo), 0.0, 1.0) ** PHOTO_GAMMA
    return np.round(np.nan_to_num(g, nan=0.5) * 255).astype(np.uint8)


def thin_days(candidates, min_gap: int = PHOTO_MIN_GAP_DAYS) -> list:
    """candidates: [(day, score, payload)]. One per day (best score), then drop days closer than min_gap days to a
    better one already kept. Sorted by day."""
    best = {}
    for day, score, payload in candidates:
        if day not in best or score > best[day][0]:
            best[day] = (score, payload)
    kept = []
    for day, (score, payload) in sorted(best.items(), key=lambda kv: (-kv[1][0], kv[0])):
        if all(abs((day - k).days) >= min_gap for k, _, _ in kept):
            kept.append((day, score, payload))
    return sorted(kept, key=lambda t: t[0])


def photo_frames(site: FrameSite, out_dir: Path, cache_dir: Path, token=None) -> list:
    """Search HLS, keep clear days, write one colour JPEG per day; returns [{date, sensor, url}] sorted by date."""
    from . import hls

    window = site.window
    granules = []
    for first, last in site.photo_periods:
        granules += hls.search(window, first, last)
    tile = hls.pick_tile(granules, window)
    granules = [g for g in granules if g.tile == tile]
    log.info("photos: %d HLS granules on tile %s", len(granules), tile)
    clear = hls.clear_granules(granules, window, PHOTO_MIN_CLEAR, token)
    kept = thin_days([(g.start.date(), f, g) for g, f in clear if g.start.date() not in site.photo_exclude])
    log.info("photos: %d clear granules, %d days after thinning", len(clear), len(kept))
    dst_t, w, h = grid_for(window)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for day, _, g in kept:
        cache = cache_dir / f"{g.name}.npz"
        if cache.is_file():
            with np.load(cache) as z:
                rgb, grid = z["rgb"], {k: float(z[k]) for k in ("a", "e", "x0", "y0")} | {"epsg": int(z["epsg"])}
        else:
            rgb, grid = hls.read_rgb(g, window, token)
            np.savez_compressed(cache, rgb=rgb, epsg=grid["epsg"], a=grid["a"], e=grid["e"], x0=grid["x0"],
                                y0=grid["y0"])
        transform = (grid["a"], 0.0, grid["x0"], 0.0, grid["e"], grid["y0"])
        chans = [warp(rgb[..., i], transform, grid["epsg"], dst_t, w, h) for i in range(3)]
        data = jpeg_bytes(photo_stretch(np.stack(chans, axis=-1)))
        (out_dir / f"{day.isoformat()}.jpg").write_bytes(data)
        frames.append({"date": day.isoformat(), "sensor": "Landsat" if g.sensor == "L30" else "Sentinel-2",
                       "url": f"frames/photo/{day.isoformat()}.jpg"})
        if len(data) > MAX_FRAME_BYTES:
            log.warning("photo %s: %d KB (target %d KB)", day, len(data) // 1000, MAX_FRAME_BYTES // 1000)
    return frames


# ---------------------------------------------------------------- command


def build(site_id: str, stacks=None, root=None, radar: bool = True, photos: bool = True, token=None) -> dict:
    site = FRAME_SITES[site_id]
    root = Path(root or REPO_ROOT)
    stacks = Path(stacks or root / "data" / "stacks")
    site_dir = root / "app" / "data" / site_id
    sets = []
    if radar:
        spans = pipeline._skip_spans(pipeline.SITES[site_id])
        frames = radar_frames(site_id, stacks, site_dir / "frames" / "radar", site.window, spans)
        sets.append({"id": "radar", "title": "Radar", "caption": RADAR_CAPTION, "frames": frames})
    if photos:
        frames = photo_frames(site, site_dir / "frames" / "photo", root / "data" / "hls" / site_id, token)
        sets.append({"id": "photo", "title": "Satellite photo", "caption": PHOTO_CAPTION, "frames": frames})
    path = site_dir / "frames.json"
    if path.is_file():  # a partial run keeps the other set
        old = {s["id"]: s for s in json.loads(path.read_text(encoding="utf-8"))["sets"]}
        sets = [{**old, **{s["id"]: s for s in sets}}[k] for k in ("radar", "photo") if k in {**old, **{s["id"]: s for s in sets}}]
    doc = {"coordinates": corners(site.window), "sets": sets}
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m sarwatch.frames", description=__doc__.split("\n")[0])
    p.add_argument("site", choices=sorted(FRAME_SITES))
    p.add_argument("--stacks", help="cache root holding <site>/s1/*.npz (default: data/stacks)")
    p.add_argument("--no-radar", action="store_true")
    p.add_argument("--no-photos", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    doc = build(args.site, args.stacks, radar=not args.no_radar, photos=not args.no_photos)
    for s in doc["sets"]:
        size = sum((REPO_ROOT / "app" / "data" / args.site / f["url"]).stat().st_size for f in s["frames"])
        print(f"{s['id']}: {len(s['frames'])} frames, {size / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
