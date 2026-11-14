"""Picture frames for the app's time-lapse and before / after swipe (issue #89, format: kb/data-contract.md).

One radar picture per Sentinel-1 pass (cross-pol VH in dB, speckle-smoothed, the same grey stretch for every date)
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
RADAR_RANGE_DB = (-26.0, -8.0)       # fixed grey stretch of VH (after the per-date offset): black .. white
PHOTO_RANGE = (0.0, 0.22)            # reflectance mapped to 0..1 before the gamma (same for every date)
PHOTO_GAMMA = 1.0 / 1.8
PHOTO_MIN_CLEAR = 0.9
PHOTO_MIN_GAP_DAYS = 3               # thin photo days closer together than this (keep the clearer one)
RADAR_CAPTION = "Dark = bare ground or water. Bright = forest and buildings."
PHOTO_CAPTION = "Colour images from Landsat and Sentinel-2 (NASA HLS), cloud-free days only."


@dataclass(frozen=True)
class FrameSite:
    window: tuple          # (west, south, east, north) degrees
    photo_periods: tuple   # ((first day, last day), ...) searched for photos


FRAME_SITES = {
    "muhos": FrameSite(window=(26.02, 64.795, 26.20, 64.875),
                       photo_periods=((date(2025, 6, 1), date(2025, 9, 30)), (date(2026, 3, 1), date(2026, 11, 14)))),
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


def vh_db(power: np.ndarray) -> np.ndarray:
    """3x3-mean smoothed VH, in dB; NaN where invalid or not positive."""
    sm = smooth_linear(power)
    with np.errstate(invalid="ignore", divide="ignore"):
        db = 10.0 * np.log10(np.where(sm > 0, sm, np.nan))
    return db.astype(np.float32)


def radar_stretch(db: np.ndarray, lo: float = RADAR_RANGE_DB[0], hi: float = RADAR_RANGE_DB[1]) -> np.ndarray:
    """dB -> uint8 grey with one fixed stretch; NaN -> 0 (black)."""
    g = np.clip((db - lo) / (hi - lo), 0.0, 1.0)
    return np.round(np.nan_to_num(g, nan=0.0) * 255).astype(np.uint8)


def radar_frames(site_id: str, stacks, out_dir: Path, window, skip_spans) -> list:
    """Write one grey JPEG per usable Sentinel-1 pass; returns [{date, sensor, url}] sorted by date."""
    cache = Path(stacks) / site_id / "s1"
    days = [d for d in pipeline.cached_days(cache) if not any(lo <= d <= hi for lo, hi in skip_spans)]
    if not days:
        raise pipeline.PipelineError(f"no usable Sentinel-1 passes in {cache}")
    dst_t, w, h = grid_for(window)
    warped = []
    for day in days:
        fr = pipeline.load_frame(pipeline.cache_path(cache, day))
        warped.append(warp(vh_db(fr.data["VH"]), fr.transform, fr.epsg, dst_t, w, h))
    medians = np.array([np.nanmedian(a) for a in warped])  # one offset per date: wet / dry days must not flicker
    ref = float(np.median(medians))
    log.info("radar: %d passes, per-date median %.1f .. %.1f dB (reference %.1f)", len(days), medians.min(),
             medians.max(), ref)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for day, db, med in zip(days, warped, medians):
        data = jpeg_bytes(radar_stretch(db - med + ref))
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
    kept = thin_days([(g.start.date(), f, g) for g, f in clear])
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
