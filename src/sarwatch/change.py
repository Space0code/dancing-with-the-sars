"""Change detection core: a stack of same-track radar images in, dated change regions out.

The method, for an engineer who does not know radar (background: kb/sar-primer.md, sections 2-4).
A radar image stores, per pixel, the echo power the ground sent back. It carries speckle, a
multiplicative noise, so single pixels are unreliable. Two channels matter: co-pol (HH or VV) is
bright for bare rough ground and wall-ground corners (buildings); cross-pol (HV or VH) is bright
for vegetation volume (tree canopies). Differences are taken in dB: 3 dB = a factor of 2 in power.

1. Smooth every image with a boxcar mean in linear power (noise falls as 1/sqrt(N)), then convert
   to dB. dB values are never averaged: that would bias the mean.
2. Per pixel, the median of the first passes is the baseline and the median of the last passes is
   the end state; their difference in dB is the change. A median ignores one odd pass (rain).
3. A pixel has changed if any channel moved by at least `threshold_db`. For farmland, two opt-in guards against rain
   and drought (ChangeParams.normalize, .hold): remove each pass's scene-wide shift, and require the change in
   every late pass.
4. Date it: the first pass from which the pixel stays at least DATING_FRACTION of the threshold
   away from its baseline, in the direction of the final change, for `persist` passes.
5. Group changed pixels into regions (8-connected, after a 3x3 opening that removes specks) and
   drop regions smaller than `min_area_ha`.
6. Name each region by rule (constants below) and attach the evidence: area, dates, before and
   after dB, a confidence grade and the region-mean time series.

Only numpy and scipy, no file or map handling: the caller supplies co-registered arrays.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
from scipy import ndimage

COPOL = ("HH", "VV")     # same polarization sent and received: surfaces, wall-ground corners
CROSSPOL = ("HV", "VH")  # polarization rotated by the target: vegetation volume

# Dating: a pixel counts as changed at a pass once it is this fraction of threshold_db away from
# its baseline. Half the threshold dates the change at the pass where it happens even at region
# edges, where the boxcar mixes changed and unchanged ground, and is still far above what speckle
# leaves after smoothing (about 0.2 dB for a 5x5 boxcar on 16-look data).
DATING_FRACTION = 0.5
# Region dates are percentiles of the per-pixel dates, not min / max, so a few stray pixels cannot
# move them: first_date = pass by which 5 % of the region had changed, last_date = 95 %.
DATE_PERCENTILES = (5, 95)

# Type rules, on region-mean changes in dB, checked in this order:
# 1. earthworks: the ground is being reworked, so it moves both ways in space or keeps moving in time
MIXED_SIGN_FRACTION = 0.2   # in one channel, >= 20 % of the region rose by threshold_db AND >= 20 % fell by it:
                            # part of the ground got rougher (brighter), part smoother (darker)
EARTHWORKS_JITTER_DB = 2.0  # or the median pass-to-pass step of the region mean, after the change started, is
                            # >= 2 dB: the surface keeps changing. A one-off step change settles to ~0 dB steps
JITTER_MIN_STEPS = 3        # the jitter rule needs at least this many passes after the change, else it is off
# 2. clearing: cross-pol region mean falls by >= threshold_db: the canopy that rotated the echo is gone
# 3. structure: co-pol rises by >= threshold_db (and no clearing): new walls or metal act as corner reflectors
# 4. other: anything else that still passed the pixel threshold
# Rules 2-3 use threshold_db itself, so a lower threshold for C-band (Sentinel-1) still names clearings.

# Confidence: one point for a strong signal, one for a large region; 0 / 1 / 2 points = low / medium / high.
CONF_MARGIN_DB = 2.0    # region-mean |change| is this far above threshold_db
CONF_AREA_FACTOR = 4.0  # region is this many times min_area_ha: many independent pixels agree

SQUARE3 = np.ones((3, 3), dtype=bool)  # the 3x3 opening element, and 8-connectivity for labelling


@dataclass
class ChangeParams:
    boxcar: int = 5            # spatial averaging window in pixels (speckle reduction, in linear power)
    n_early: int = 3           # number of first passes forming the baseline
    n_late: int = 3            # number of last passes forming the end state
    threshold_db: float = 3.0  # minimum |late - early| to call a change
    persist: int = 2           # passes the deviation must hold to date the change
    min_area_ha: float = 0.5   # drop smaller regions
    # Seasonal guards for farmland, both off by default. Rain and dry spells move a whole scene by 1-3 dB at once.
    normalize: bool = False    # subtract each pass's window-wide median dB (per polarization, relative to the
                               # baseline passes) before comparing: removes a scene-wide wet / dry or calibration shift
    hold: bool = False         # a pixel counts only if every one of the last n_late passes is beyond threshold_db
                               # in the same direction, not just their median: a wet spell over 2 of 3 passes is out


@dataclass
class Region:
    label: int        # value in ChangeResult.labels
    type: str         # "clearing" | "structure" | "earthworks" | "other"
    area_ha: float
    first_date: date  # first pass where the change shows (5th percentile of the pixel dates)
    last_date: date   # last pass where pixels of this region were still newly changing (95th percentile)
    signal: dict      # {"metric": "HV_dB", "before": float, "after": float, "delta": float}
    confidence: str   # "low" | "medium" | "high"
    series: dict      # {"dates": [date, ...], "<POL>_dB": [float, ...]} region-mean series; NaN = no usable pixel
    bbox: tuple       # (row0, col0, row1, col1), half-open


@dataclass
class ChangeResult:
    delta_db: dict                # per polarization: late median - early median, in dB, (y, x) float32, NaN = invalid
    first_change_idx: np.ndarray  # (y, x) int16 index into dates; -1 where no change (set only inside regions)
    labels: np.ndarray            # (y, x) int32, 0 = background
    regions: list                 # list[Region], sorted by area descending; regions[i].label == i + 1


def _usable(power: np.ndarray) -> np.ndarray:
    return np.isfinite(power) & (power > 0)


def _nanmedian(a: np.ndarray) -> np.ndarray:
    """Median over axis 0, skipping NaN; NaN where nothing is left. Faster than np.nanmedian on short axes."""
    s = np.sort(a, axis=0)  # NaN sorts last, so the k usable values come first
    k = np.count_nonzero(~np.isnan(a), axis=0)
    lo = np.take_along_axis(s, np.expand_dims(np.maximum(k - 1, 0) // 2, 0), axis=0)[0]
    hi = np.take_along_axis(s, np.expand_dims(k // 2, 0), axis=0)[0]
    return (lo + hi) / 2


def _smooth_db(arr, valid: np.ndarray, size: int) -> np.ndarray:
    """Boxcar mean of each pass in linear power, skipping unusable pixels, in dB. Unusable -> NaN."""
    out = np.empty(np.shape(arr), dtype=np.float32)
    for t in range(out.shape[0]):
        img = np.asarray(arr[t], dtype=np.float64)
        ok = _usable(img) & valid
        total = ndimage.uniform_filter(np.where(ok, img, 0.0), size=size, mode="constant")
        weight = ndimage.uniform_filter(ok.astype(np.float64), size=size, mode="constant")
        ok &= total > 0  # the filter's running sum can round to <= 0 next to very bright pixels
        res = out[t]
        res.fill(np.nan)
        np.log10(total / np.where(ok, weight, 1.0), out=res, where=ok)
        res *= 10
    return out


def _pass_offsets(arr, valid: np.ndarray, n_early: int) -> np.ndarray:
    """Per pass: median dB over the window's usable pixels, minus the median of that over the baseline passes."""
    med = np.array([np.median(10 * np.log10(img[_usable(img) & valid])) if (_usable(img) & valid).any() else 0.0
                    for img in (np.asarray(a, dtype=np.float64) for a in arr)])
    return med - np.median(med[:n_early])


def _date_pixels(db: np.ndarray, early: np.ndarray, sign: np.ndarray, level: float, persist: int,
                 fallback: int) -> np.ndarray:
    """First pass t >= 1 from which each changed pixel stays beyond `level` for `persist` passes.

    db is (time, n_pixels). Near the end of the stack the run only has to last until the final pass.
    A pixel with no such run gets `fallback`, the first pass of the late window.
    """
    with np.errstate(invalid="ignore"):
        beyond = (db - early) * sign >= level  # NaN compares False
    run = beyond.copy()
    for k in range(1, persist):
        run[:-k] &= beyond[k:]
    run[0] = False  # pass 0 is baseline by definition
    return np.where(run.any(axis=0), run.argmax(axis=0), fallback).astype(np.int16)


def _region_series(arr, window: tuple, member: np.ndarray) -> np.ndarray:
    """Region mean per pass in dB: mean in linear power over the region's usable pixels, then dB."""
    block = np.asarray(arr[(slice(None), *window)], dtype=np.float64)[:, member]
    ok = _usable(block)
    count = ok.sum(axis=1)
    mean = np.where(ok, block, 0.0).sum(axis=1) / np.maximum(count, 1)
    with np.errstate(divide="ignore"):
        return np.where(count > 0, 10 * np.log10(mean), np.nan)


def _classify(delta: dict, mixed: bool, jitter: float, thr: float) -> tuple:
    """Region type and the polarization that carries the evidence. delta: {pol: region-mean change in dB}."""
    strongest = max(delta, key=lambda p: abs(delta[p]))
    cross = min((p for p in delta if p.upper() in CROSSPOL), key=delta.get, default=None)
    co = max((p for p in delta if p.upper() in COPOL), key=delta.get, default=None)
    if mixed or jitter >= EARTHWORKS_JITTER_DB:
        return "earthworks", strongest
    if cross is not None and delta[cross] <= -thr:
        return "clearing", cross
    if co is not None and delta[co] >= thr:
        return "structure", co
    return "other", strongest


def detect_changes(stack: dict, dates: list, pixel_size_m: tuple, params: ChangeParams = ChangeParams(),
                   valid=None) -> ChangeResult:
    """Find dated change regions in a time-sorted stack {pol: (time, y, x) linear power}. See module docstring."""
    shapes = {np.shape(a) for a in stack.values()}
    if len(shapes) != 1 or len(next(iter(shapes))) != 3:
        raise ValueError("stack needs at least one polarization, all arrays (time, y, x) of the same shape")
    n_t, ny, nx = next(iter(shapes))
    if n_t != len(dates) or n_t < 2:
        raise ValueError("need one date per pass and at least two passes")
    valid = np.ones((ny, nx), dtype=bool) if valid is None else np.asarray(valid, dtype=bool)
    if valid.shape != (ny, nx):
        raise ValueError("valid must be (y, x)")
    n_early = max(1, min(params.n_early, n_t - 1))
    n_late = max(1, min(params.n_late, n_t - n_early))  # the two windows never overlap
    thr = params.threshold_db

    offsets = {p: _pass_offsets(a, valid, n_early) if params.normalize else np.zeros(n_t) for p, a in stack.items()}
    delta_db = {}
    first = np.full((ny, nx), -1, dtype=np.int16)
    for pol, arr in stack.items():
        db = _smooth_db(arr, valid, max(1, params.boxcar))
        db -= offsets[pol].astype(np.float32)[:, None, None]
        early = _nanmedian(db[:n_early])
        delta = _nanmedian(db[n_t - n_late:]) - early
        delta_db[pol] = delta
        with np.errstate(invalid="ignore"):
            if params.hold:  # the late pass closest to the baseline must still be beyond the threshold
                late = db[n_t - n_late:] - early
                hit = (np.fmin.reduce(late, axis=0) >= thr) | (np.fmax.reduce(late, axis=0) <= -thr)
            else:
                hit = np.abs(delta) >= thr  # NaN compares False, so unusable pixels never count as changed
        idx = _date_pixels(db[:, hit], early[hit], np.sign(delta[hit]), thr * DATING_FRACTION,
                           max(1, params.persist), n_t - n_late)
        seen = first[hit]
        first[hit] = np.where(seen < 0, idx, np.minimum(seen, idx))  # earliest over polarizations
        del db

    components, n = ndimage.label(ndimage.binary_opening(first >= 0, structure=SQUARE3), structure=SQUARE3)
    px_ha = abs(pixel_size_m[0] * pixel_size_m[1]) / 1e4
    sizes = np.bincount(components.ravel(), minlength=n + 1)
    sizes[0] = 0  # background
    keep = [i for i in np.argsort(-sizes, kind="stable") if sizes[i] > 0 and sizes[i] * px_ha >= params.min_area_ha]
    remap = np.zeros(n + 1, dtype=np.int32)
    remap[keep] = np.arange(1, len(keep) + 1)
    labels = remap[components]
    first[labels == 0] = -1

    regions = []
    for label, window in enumerate(ndimage.find_objects(labels), start=1):
        member = labels[window] == label
        n_px = int(member.sum())
        lo, hi = (int(i) for i in np.percentile(first[window][member], DATE_PERCENTILES, method="nearest"))
        series, level, mixed, jitter = {"dates": list(dates)}, {}, False, 0.0
        for pol, arr in stack.items():
            mean_db = _region_series(arr, window, member) - offsets[pol]
            series[f"{pol}_dB"] = mean_db.tolist()
            before, after = float(_nanmedian(mean_db[:n_early])), float(_nanmedian(mean_db[n_t - n_late:]))
            if np.isfinite(after - before):
                level[pol] = (before, after)
            steps = np.abs(np.diff(mean_db[lo:]))  # pass-to-pass moves after the change started
            steps = steps[np.isfinite(steps)]
            if steps.size >= JITTER_MIN_STEPS:
                jitter = max(jitter, float(np.median(steps)))
            d = delta_db[pol][window][member]
            up, down = np.count_nonzero(d >= thr), np.count_nonzero(d <= -thr)
            mixed |= min(up, down) >= MIXED_SIGN_FRACTION * n_px
        kind, pol = _classify({p: a - b for p, (b, a) in level.items()}, mixed, jitter, thr)
        before, after = level[pol]
        area_ha = n_px * px_ha
        points = int(abs(after - before) - thr >= CONF_MARGIN_DB) + int(area_ha >= CONF_AREA_FACTOR * params.min_area_ha)
        regions.append(Region(
            label=label, type=kind, area_ha=area_ha, first_date=dates[lo], last_date=dates[hi],
            signal={"metric": f"{pol}_dB", "before": before, "after": after, "delta": after - before},
            confidence=("low", "medium", "high")[points], series=series,
            bbox=(window[0].start, window[1].start, window[0].stop, window[1].stop),
        ))
    return ChangeResult(delta_db=delta_db, first_change_idx=first, labels=labels, regions=regions)
