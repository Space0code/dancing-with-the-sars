"""Picture frames for the app's time-lapse and before / after swipe (issue #89, format: kb/data-contract.md).

One radar picture per Sentinel-1 pass (cross-pol VH in dB, speckle-smoothed in space and over neighbouring passes, one grey stretch for every date,
with the pixels that lost echo since summer 2025 tinted magenta-pink) up to NISAR's first pass, then one per NISAR pass
(cross-pol HV, its own grey stretch, tinted where HV fell 3 dB below NISAR's own first picture),
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
NISAR_RANGE_DB = (-17.5, -8.0)       # fixed grey stretch of HV: forest (median -10.5 dB, 90 % under -9) light, bare ground (-13 and below) dark
NISAR_TINT_FROM_DB = 3.0             # tint where HV is this far below NISAR's own first pass ...
NISAR_TINT_FULL_DB = 6.0             # ... full strength at this drop
NISAR_STABLE_MIN_DB = -12.0          # a pixel whose HV never falls below this is "stable forest": sets each pass's offset
TINT_RGB = (214, 40, 160)              # magenta-pink, apart from the verdict colours
RADAR_CAPTION = "Radar picture. Grey: unchanged since summer 2025. Pink: the echo from trees and plants dropped here."
NISAR_CAPTION = ("NISAR radar picture (NASA and ISRO). Light: forest. Dark: bare ground or water. "
                 "Pink: trees gone since NISAR's first picture on {first}.")
PHOTO_CAPTION = "Colour images from Landsat and Sentinel-2 (NASA HLS), cloud-free days only."


@dataclass(frozen=True)
class FrameSite:
    window: tuple          # (west, south, east, north) degrees
    photo_periods: tuple   # ((first day, last day), ...) searched for photos
    photo_exclude: tuple = ()  # days dropped by eye although Fmask calls them clear (thin haze, small cloud puffs)
    # The settings below default to Muhos'; a larger or busier site (Barcelona) sets its own.
    width: int = WIDTH                   # pixels across the picture
    max_frame_bytes: int = MAX_FRAME_BYTES
    s1_range: tuple = RADAR_RANGE_DB     # grey stretch of Sentinel-1 VH (dB)
    nisar_range: tuple = NISAR_RANGE_DB  # grey stretch of NISAR HV (dB)
    baseline_first: int = 0              # > 0: Sentinel-1 baseline = median of the first N passes (else BASELINE_SPAN)
    tint_rise: bool = False              # tint echo that rose too (new buildings), not only echo that fell
    water_mask: bool = False             # water = the pipeline's mask: never tinted, drawn black, levels the passes
    tint_db: tuple = (TINT_FROM_DB, TINT_FULL_DB)  # Sentinel-1: tint from this change (dB), full at that
    min_patch_ha: float = MIN_PATCH_HA   # smaller tinted patches are dropped
    time_gap: int = TIME_MAX_GAP_DAYS    # neighbouring passes up to this many days apart are averaged
    captions: tuple = ()                 # (Sentinel-1 set caption, NISAR caption): the satellite's name only
    photo_yearly: int = -1               # >= 0: one clear photo per year, plus this many more in the last year


FRAME_SITES = {
    # Barcelona (#44): 50 x 39 km, so twice the width and a stretch for the city; the sea comes from the pipeline's
    # mask; the baseline is the 2016 summer (5 passes, as in the detection); echo that rose (buildings) is tinted too
    "barcelona": FrameSite(window=(1.85, 41.25, 2.45, 41.60),
                           photo_periods=tuple((date(y, 6, 1), date(y, 9, 30)) for y in range(2016, 2027)) +
                                         ((date(2026, 10, 1), date(2026, 11, 14)),),
                           width=1400, max_frame_bytes=900_000, s1_range=(-27.0, -3.0), nisar_range=(-28.0, -2.0),
                           baseline_first=5, tint_rise=True, water_mask=True, time_gap=30,
                           tint_db=(4.0, 8.0), min_patch_ha=2.0,
                           captions=("Sentinel-1", "NISAR"), photo_yearly=3),
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


def lost_alpha(drop_db: np.ndarray, baseline_db: np.ndarray, pixel_ha: float, from_db: float = TINT_FROM_DB,
               full_db: float = TINT_FULL_DB, water: np.ndarray | None = None,
               min_ha: float = MIN_PATCH_HA) -> np.ndarray:
    """Tint strength 0..1 per pixel: 0 below from_db of drop, full at full_db. Patches smaller than MIN_PATCH_HA
    and water (very dark in the baseline, or True in the `water` mask when given) get none."""
    from scipy import ndimage

    ok = np.isfinite(drop_db) & ((baseline_db > WATER_DB) if water is None else ~water)
    d = np.where(ok, drop_db, 0.0)
    mask = d >= from_db
    labels, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n:
        size = ndimage.sum(mask, labels, index=np.arange(1, n + 1))
        mask &= np.isin(labels, 1 + np.flatnonzero(size * pixel_ha >= min_ha))
    alpha = np.clip((d - from_db) / (full_db - from_db), 0.0, 1.0)
    alpha = TINT_MIN_ALPHA + (TINT_MAX_ALPHA - TINT_MIN_ALPHA) * alpha
    return np.where(mask, alpha, 0.0).astype(np.float32)


def tint(grey: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """grey (h, w) 0..1 and alpha (h, w) -> uint8 RGB with TINT_RGB blended over the grey picture."""
    rgb = np.asarray(TINT_RGB, np.float32) / 255.0
    out = grey[..., None] * (1 - alpha[..., None]) + rgb * alpha[..., None]
    return np.round(out * 255).astype(np.uint8)


def pipeline_water(site_id: str, sensor: str, cache, days: list, dst_t, w: int, h: int) -> np.ndarray:
    """The detection's water mask (pipeline._water_mask: baseline of the site's water polarisation, shore grown) on the
    common grid, True = water. Reads only the baseline passes of `days` (one more than n_early, as the mask wants)."""
    site = pipeline.SITES[site_id]
    settings = site.nisar if sensor == pipeline.NISAR else site.s1
    n = settings.params.n_early
    stack, _, transform, epsg = pipeline.load_stack(cache, days[:n + 1], site.bbox)
    valid = pipeline._water_mask(stack, sensor, n, settings.water_db, settings.water_grow, settings.water_pol)
    return warp((~valid).astype(np.float32), transform, epsg, dst_t, w, h, "nearest") > 0.5


def radar_series(site_id: str, stacks, window, skip_spans, cfg: FrameSite | None = None) -> tuple:
    """(days, db, baseline, pixel_ha, water): the smoothed, per-date levelled VH of every usable pass on the common
    grid; water = the pipeline's mask when cfg.water_mask (else None)."""
    cfg = cfg or FrameSite(window, ())
    cache = Path(stacks) / site_id / "s1"
    days = [d for d in pipeline.cached_days(cache) if not any(lo <= d <= hi for lo, hi in skip_spans)]
    if not days:
        raise pipeline.PipelineError(f"no usable Sentinel-1 passes in {cache}")
    dst_t, w, h = grid_for(window, cfg.width)
    warped = []
    for day in days:
        fr = pipeline.load_frame(pipeline.cache_path(cache, day))
        warped.append(warp(smooth_linear(fr.data["VH"]), fr.transform, fr.epsg, dst_t, w, h, "bilinear"))
    warped = time_average(warped, days, cfg.time_gap)
    dbs = [to_db(a) for a in warped]
    water = pipeline_water(site_id, pipeline.S1, cache, days, dst_t, w, h) if cfg.water_mask else None
    land = slice(None) if water is None else ~water
    medians = np.array([np.nanmedian(a[land]) for a in dbs])  # one offset per date: wet / dry days must not flicker
    ref = float(np.median(medians))
    log.info("radar: %d passes, per-date median %.1f .. %.1f dB (reference %.1f)", len(days), medians.min(),
             medians.max(), ref)
    dbs = [a - m + ref for a, m in zip(dbs, medians)]
    if cfg.baseline_first:
        base = dbs[:cfg.baseline_first]
    else:
        base = [a for a, d in zip(dbs, days) if BASELINE_SPAN[0] <= d <= BASELINE_SPAN[1]]
    if not base:
        raise pipeline.PipelineError("no passes for the baseline")
    baseline = np.nanmedian(np.stack(base), axis=0)
    west, south, east, north = window
    mid = math.radians((north + south) / 2)
    pixel_ha = (east - west) * 111_320 * math.cos(mid) / w * (north - south) * 110_574 / h / 1e4
    return days, dbs, baseline, pixel_ha, water


def radar_frames(site_id: str, stacks, out_dir: Path, window, skip_spans, until: date | None = None,
                 cfg: FrameSite | None = None) -> list:
    """Write one JPEG per usable Sentinel-1 pass before `until` (grey radar, lost vegetation echo tinted); returns
    [{date, sensor, url}] sorted by date. The smoothing and levelling still use every pass."""
    cfg = cfg or FrameSite(window, ())
    days, dbs, baseline, pixel_ha, water = radar_series(site_id, stacks, window, skip_spans, cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, (day, db) in enumerate(zip(days, dbs)):
        if until is not None and day >= until:
            continue
        change = baseline - db
        alpha = lost_alpha(np.abs(change) if cfg.tint_rise else change, baseline, pixel_ha, *cfg.tint_db, water,
                           cfg.min_patch_ha)
        if i < cfg.baseline_first:  # the baseline passes are what "unchanged" means
            alpha[:] = 0
        grey = radar_stretch(db, *cfg.s1_range)
        if water is not None:
            grey[water] = 0.0  # the sea: no wind streaks, no ships
        data = jpeg_bytes(tint(grey, alpha), max_bytes=cfg.max_frame_bytes)
        (out_dir / f"{day.isoformat()}.jpg").write_bytes(data)
        frames.append({"date": day.isoformat(), "sensor": "Sentinel-1", "url": f"frames/radar/{day.isoformat()}.jpg"})
        if len(data) > cfg.max_frame_bytes:
            log.warning("radar %s: %d KB (target %d KB)", day, len(data) // 1000, cfg.max_frame_bytes // 1000)
    return frames


def nisar_series(site_id: str, stacks, window, skip_spans, cfg: FrameSite | None = None) -> tuple:
    """(days, db, water, pixel_ha): smoothed, levelled HV of every usable NISAR pass on the common grid, and the
    detection's water mask (pipeline._water_mask: HH baseline, shore grown) on that grid, True = water."""
    cfg = cfg or FrameSite(window, ())
    site = pipeline.SITES[site_id]
    cache = Path(stacks) / site_id / pipeline.NISAR
    days = [d for d in pipeline.cached_days(cache) if not any(lo <= d <= hi for lo, hi in skip_spans)]
    if not days:
        raise pipeline.PipelineError(f"no usable NISAR passes in {cache}")
    dst_t, w, h = grid_for(window, cfg.width)
    warped = []
    for day in days:
        fr = pipeline.load_frame(pipeline.cache_path(cache, day))
        warped.append(warp(smooth_linear(fr.data["HV"]), fr.transform, fr.epsg, dst_t, w, h, "bilinear"))
    dbs = [to_db(a) for a in time_average(warped, days, cfg.time_gap)]
    stable = np.all([np.nan_to_num(a, nan=-99.0) >= NISAR_STABLE_MIN_DB for a in dbs], axis=0)
    medians = np.array([np.nanmedian(a[stable]) for a in dbs])  # one offset per pass: moisture must not flicker
    ref = float(np.median(medians))
    log.info("nisar: %d passes, stable forest (%d px) median %.2f .. %.2f dB", len(days), stable.sum(), medians.min(),
             medians.max())
    dbs = [a - m + ref for a, m in zip(dbs, medians)]
    stack, _, transform, epsg = pipeline.load_stack(cache, days, site.bbox)
    s = site.nisar
    valid = pipeline._water_mask(stack, pipeline.NISAR, s.params.n_early, s.water_db, s.water_grow, s.water_pol)
    water = warp((~valid).astype(np.float32), transform, epsg, dst_t, w, h, "nearest") > 0.5
    s1_cache = Path(stacks) / site_id / pipeline.S1
    if cfg.water_mask and site.s1 is not None and pipeline.cached_days(s1_cache):  # one sea for both sensors
        water |= pipeline_water(site_id, pipeline.S1, s1_cache, pipeline.cached_days(s1_cache), dst_t, w, h)
    log.info("nisar: water mask %.1f%% of the window", 100 * water.mean())
    west, south, east, north = window
    mid = math.radians((north + south) / 2)
    pixel_ha = (east - west) * 111_320 * math.cos(mid) / w * (north - south) * 110_574 / h / 1e4
    return days, dbs, water, pixel_ha


def nisar_alphas(dbs: list, water: np.ndarray, pixel_ha: float, rise: bool = False,
                 min_ha: float = MIN_PATCH_HA) -> list:
    """Tint strength per NISAR pass: HV below the first pass by NISAR_TINT_FROM_DB or more (none on the first pass);
    with rise, above it by that much too."""
    return [lost_alpha(np.abs(dbs[0] - db) if rise else dbs[0] - db, dbs[0], pixel_ha, NISAR_TINT_FROM_DB,
                       NISAR_TINT_FULL_DB, water, min_ha) if i else np.zeros(db.shape, np.float32) for i, db in enumerate(dbs)]


def nisar_frames(site_id: str, stacks, out_dir: Path, window, skip_spans, cfg: FrameSite | None = None) -> list:
    """Write one JPEG per usable NISAR pass (grey HV, trees gone since the first pass tinted); returns
    [{date, sensor, url, caption}] sorted by date. File names end in -nisar so they never meet a Sentinel-1 file."""
    cfg = cfg or FrameSite(window, ())
    days, dbs, water, pixel_ha = nisar_series(site_id, stacks, window, skip_spans, cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    caption = cfg.captions[1] if cfg.captions else NISAR_CAPTION.format(first=f"{days[0].day} {days[0]:%b %Y}")
    frames = []
    for day, db, alpha in zip(days, dbs, nisar_alphas(dbs, water, pixel_ha, cfg.tint_rise,
                                                                 cfg.min_patch_ha)):
        grey = radar_stretch(db, *cfg.nisar_range)
        if cfg.water_mask:
            grey[water] = 0.0
        data = jpeg_bytes(tint(grey, alpha), max_bytes=cfg.max_frame_bytes)
        name = f"{day.isoformat()}-nisar.jpg"
        (out_dir / name).write_bytes(data)
        frames.append({"date": day.isoformat(), "sensor": "NISAR", "url": f"frames/radar/{name}", "caption": caption})
        if len(data) > cfg.max_frame_bytes:
            log.warning("nisar %s: %d KB (target %d KB)", day, len(data) // 1000, cfg.max_frame_bytes // 1000)
    return frames


def radar_set(site_id: str, stacks, out_dir: Path, window, skip_spans, cfg: FrameSite | None = None) -> list:
    """The radar frames of the app: Sentinel-1 up to NISAR's first pass, NISAR pictures from then on. Files of
    frames no longer listed (the later Sentinel-1 passes, older runs) are deleted."""
    has_nisar = (Path(stacks) / site_id / pipeline.NISAR).is_dir() and pipeline.SITES[site_id].nisar is not None
    nisar = nisar_frames(site_id, stacks, out_dir, window, skip_spans, cfg) if has_nisar else []
    until = date.fromisoformat(nisar[0]["date"]) if nisar else None
    frames = radar_frames(site_id, stacks, out_dir, window, skip_spans, until, cfg) + nisar
    listed = {Path(f["url"]).name for f in frames}
    for path in out_dir.glob("*.jpg"):
        if path.name not in listed:
            path.unlink()
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


def pick_yearly(candidates, extra: int = 0, min_gap: int = 20, mid_summer=(7, 15)) -> list:
    """candidates: [(day, score, payload)]. One per calendar year: the best score (to 2 decimals), ties to the day
    nearest 15 July, so the seasons of different years look alike. Then `extra` more from the last year, best score
    first, each at least min_gap days from every kept day. Sorted by day."""
    def near(day):
        return abs((day - date(day.year, *mid_summer)).days)

    ranked = sorted(candidates, key=lambda c: (-round(c[1], 2), near(c[0]), c[0]))
    kept, years = [], set()
    for c in ranked:
        if c[0].year not in years:
            years.add(c[0].year)
            kept.append(c)
    if kept and extra:
        last = max(years)
        more = 0
        for c in ranked:
            if more < extra and c[0].year == last and all(abs((c[0] - k[0]).days) >= min_gap for k in kept):
                kept.append(c)
                more += 1
    return sorted(kept, key=lambda t: t[0])


def photo_name(g) -> str:
    """The satellite's name: Landsat 8 / Landsat 9 (from the CMR platform) or Sentinel-2."""
    if g.sensor != "L30":
        return "Sentinel-2"
    platform = str(g.extra.get("platform", "")).upper().replace("LANDSAT-", "")
    return f"Landsat {platform}" if platform.isdigit() else "Landsat"


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
    cands = [(g.start.date(), f, g) for g, f in clear if g.start.date() not in site.photo_exclude]
    kept = pick_yearly(cands, site.photo_yearly) if site.photo_yearly >= 0 else thin_days(cands)
    log.info("photos: %d clear granules, %d days after thinning", len(clear), len(kept))
    dst_t, w, h = grid_for(window, site.width)
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
        data = jpeg_bytes(photo_stretch(np.stack(chans, axis=-1)), max_bytes=site.max_frame_bytes)
        (out_dir / f"{day.isoformat()}.jpg").write_bytes(data)
        frames.append({"date": day.isoformat(), "sensor": "Landsat" if g.sensor == "L30" else "Sentinel-2",
                       "url": f"frames/photo/{day.isoformat()}.jpg"})
        if site.captions:
            frames[-1]["caption"] = photo_name(g)
        if len(data) > site.max_frame_bytes:
            log.warning("photo %s: %d KB (target %d KB)", day, len(data) // 1000, site.max_frame_bytes // 1000)
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
        frames = radar_set(site_id, stacks, site_dir / "frames" / "radar", site.window, spans, site)
        sets.append({"id": "radar", "title": "Radar", "caption": site.captions[0] if site.captions else RADAR_CAPTION,
                     "frames": frames})
    if photos:
        frames = photo_frames(site, site_dir / "frames" / "photo", root / "data" / "hls" / site_id, token)
        sets.append({"id": "photo", "title": "Satellite photo",
                     "caption": "Landsat and Sentinel-2" if site.captions else PHOTO_CAPTION, "frames": frames})
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
    p.add_argument("--stacks", help="cache root holding <site>/s1 and <site>/nisar (*.npz) (default: data/stacks)")
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
