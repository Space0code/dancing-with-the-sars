"""Export detected changes to the files the web app reads (kb/data-contract.md).

Input: one or more detection runs over one site, one sensor each: the radar image stack, its grid
georeferencing and the ChangeResult from sarwatch.change. Output, under the site folder:

- changes.geojson                  one outline per detected region, lon/lat, with its evidence
- layers.json + layers/*.png       a "before" and an "after" false-colour radar picture per run
- evidence/<id>_before.png, _after.png   crops of those pictures around each change, outline drawn
- series/<id>.json                 the region's signal over time, plus other sensors' signal over
                                   the same ground (a NISAR change can show its Sentinel-1 history)

story.json (written by the verdict track) and anything else in the folder are never touched.

How to read the pictures (background: kb/sar-primer.md). Each is the per-pixel median of a few
passes in linear power, shown in dB. Red = co-pol (HH / VV, the "surface echo": strong from bare
rough ground and buildings), green = cross-pol (HV / VH, the "vegetation echo": strong from tree
canopies), blue = co-pol minus cross-pol (high where there is little vegetation). Each channel maps
a fixed dB range (COLOUR_DB, per radar band) to 0..255, so pictures of different dates and sites
compare directly: woodland comes out green-yellow, bare or farmed ground purple-blue, buildings
light pink to white, water dark blue. A run with one polarization gives a grey picture.
"""
from __future__ import annotations

import json
import math
import re
import warnings
from collections import Counter
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
import shapely
from PIL import Image
from pyproj import Geod, Transformer
from rasterio import features
from rasterio.transform import Affine
from scipy import ndimage
from shapely.geometry import mapping, shape
from shapely.geometry.polygon import orient

from .change import COPOL, CROSSPOL, SQUARE3, ChangeResult, _nanmedian

# False-colour scaling: channel -> (dB shown black, dB shown at full brightness), per radar band.
# Picked so typical land cover sits mid-range: L-band forest HH ~ -8, HV ~ -13 dB; bare soil HH ~ -14,
# HV ~ -24 dB (cross-pol sits 6-12 dB under co-pol). C-band cross-pol is a little stronger relative to
# co-pol (VV ~ -8 / VH ~ -14 dB over forest), hence its narrower blue range.
COLOUR_DB = {
    "L": {"co": (-20.0, 0.0), "cross": (-28.0, -8.0), "ratio": (0.0, 16.0)},  # NISAR (HH, HV)
    "C": {"co": (-20.0, 0.0), "cross": (-26.0, -6.0), "ratio": (0.0, 14.0)},  # Sentinel-1 (VV, VH)
}
MAX_LAYER_PX = 2048              # long side of a site picture; bigger grids are block-averaged in linear power
MAX_PNG_BYTES = 8 * 1024 * 1024  # a site picture above this is re-saved with a 256-colour palette (contract: 10 MB)
EVIDENCE_SHORT_MIN = 240         # evidence crops: short side at least this (when the grid allows) ...
EVIDENCE_LONG_MAX = 640          # ... and long side at most this, in output pixels
EVIDENCE_MARGIN_PX = 8           # margin around the region's bbox: at least this many grid pixels ...
EVIDENCE_MARGIN_FRAC = 0.25      # ... or this fraction of the bbox's longer side
OUTLINE_PX = 2                   # outline drawn just outside the region, in output pixels
OUTLINE_RGBA = (255, 221, 0, 255)  # yellow: stands out on every false colour above
SIMPLIFY_PX = 0.5                # outline simplification tolerance, in grid pixels
MIN_FOOTPRINT_PX = 3             # another run's series needs at least this many of its pixels under the change

GEOD = Geod(ellps="WGS84")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
PATTERNS = {
    "clearing": "the pattern left when trees are removed",
    "structure": "the pattern of new walls, roofs or metal structures",
    "earthworks": "the pattern of ground being dug, moved or levelled",
    "fire": "the pattern left when vegetation burns",
    "other": "a change that does not match a known pattern",
}


@dataclass
class Run:
    """One detection run: one sensor over one site."""
    sensor: str            # "NISAR L-band" | "Sentinel-1 C-band"
    result: ChangeResult   # from sarwatch.change.detect_changes
    dates: list            # list[date], as passed to detect_changes
    stack: dict            # polarization -> (time, y, x) linear power, the arrays given to detect_changes
    transform: tuple       # affine (a, b, c, d, e, f): x = a*col + b*row + c ; y = d*col + e*row + f,
                           # pixel-corner convention, e < 0 for north-up
    epsg: int              # projected CRS of the grid (UTM)


# ---------------------------------------------------------------- small helpers

def _iso(d) -> str:
    return str(d)[:10]  # date, datetime and numpy datetime64 all start with YYYY-MM-DD


def _day(d) -> date:
    return date.fromisoformat(_iso(d))


def _span(d0, d1, sep: str) -> str:
    """'3 and 15 Sep 2026', '25 Jun and 7 Jul 2026', '28 Dec 2025 and 9 Jan 2026'; one date if equal."""
    a, b = _day(d0), _day(d1)
    right = f"{b.day} {MONTHS[b.month - 1]} {b.year}"
    if a == b:
        return right
    if a.year != b.year:
        left = f"{a.day} {MONTHS[a.month - 1]} {a.year}"
    elif a.month != b.month:
        left = f"{a.day} {MONTHS[a.month - 1]}"
    else:
        left = str(a.day)
    return f"{left}{sep}{right}"


def _echo(pol: str) -> str:
    p = pol.upper()
    return "vegetation echo" if p in CROSSPOL else "surface echo" if p in COPOL else "radar echo"


def _ordered(pols) -> list:
    """Cross-pol first (the clearing signal), then co-pol, then anything else; stable otherwise."""
    return sorted(pols, key=lambda p: 0 if p.upper() in CROSSPOL else 1 if p.upper() in COPOL else 2)


def _num(v, ndigits: int):
    return None if v is None or not math.isfinite(v) else round(float(v), ndigits)


def _db(power: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(power > 0, 10 * np.log10(power), np.nan).astype(np.float32)


@lru_cache(maxsize=None)
def _transformer(src: int, dst: int) -> Transformer:
    return Transformer.from_crs(src, dst, always_xy=True)


def _write_json(path: Path, obj, indent=1) -> None:
    path.write_text(json.dumps(obj, indent=indent, allow_nan=False), encoding="utf-8")


def _save_png(rgba: np.ndarray, path: Path, max_bytes: int | None = None) -> None:
    img = Image.fromarray(rgba)
    img.save(path)
    if max_bytes and path.stat().st_size > max_bytes:
        img.quantize(colors=256, method=Image.Quantize.FASTOCTREE).save(path)


# ---------------------------------------------------------------- outlines

def _orient(geom):
    """Exterior rings counter-clockwise, holes clockwise (RFC 7946)."""
    if geom.geom_type == "Polygon":
        return orient(geom, 1.0)
    return shapely.MultiPolygon([orient(p, 1.0) for p in geom.geoms])


def _round_ring(ring) -> list:
    pts = []
    for x, y in ring:
        p = [round(float(x), 6), round(float(y), 6)]
        if not pts or p != pts[-1]:
            pts.append(p)
    if pts[0] != pts[-1]:
        pts.append(list(pts[0]))
    return pts


def _lonlat_geojson(geom, epsg: int) -> dict:
    tr = _transformer(epsg, 4326)

    def to_lonlat(xy):
        lon, lat = tr.transform(xy[:, 0], xy[:, 1])
        return np.column_stack([lon, lat])

    ll = _orient(shapely.transform(geom, to_lonlat))
    coords = mapping(ll)["coordinates"]
    if ll.geom_type == "Polygon":
        return {"type": "Polygon", "coordinates": [_round_ring(r) for r in coords]}
    return {"type": "MultiPolygon", "coordinates": [[_round_ring(r) for r in poly] for poly in coords]}


def _geodesic_ha(geojson: dict) -> float:
    area_m2, _ = GEOD.geometry_area_perimeter(shape(geojson))
    return abs(area_m2) / 1e4


def _outline(geom, tolerance: float, epsg: int) -> dict:
    """Simplified outline in lon/lat; falls back to the exact pixel outline if simplifying breaks it."""
    simple = geom.simplify(tolerance, preserve_topology=True)
    for candidate in (simple, geom):
        if candidate.is_empty or not candidate.is_valid:
            continue
        gj = _lonlat_geojson(candidate, epsg)
        check = shape(gj)
        if check.is_valid and not check.is_empty:
            return gj
    return _lonlat_geojson(geom, epsg)


def _outlines(run: Run) -> dict:
    """Region label -> GeoJSON geometry (EPSG:4326) traced from the label raster, holes kept."""
    labels = np.asarray(run.result.labels, dtype=np.int32)
    parts: dict = {}
    for geom, value in features.shapes(labels, mask=labels > 0, transform=Affine(*run.transform)):
        parts.setdefault(int(value), []).append(shape(geom))
    a, b, _, d, e, _ = run.transform
    tolerance = SIMPLIFY_PX * min(math.hypot(a, d), math.hypot(b, e))
    return {label: _outline(shapely.union_all(polys), tolerance, run.epsg) for label, polys in parts.items()}


# ---------------------------------------------------------------- pictures

def _band(run: Run) -> str:
    s = run.sensor.upper()
    if "C-BAND" in s:
        return "C"
    if "L-BAND" in s:
        return "L"
    return "C" if any(p.upper() in ("VV", "VH") for p in run.stack) else "L"


def _co_cross(pols) -> tuple:
    co = next((p for p in pols if p.upper() in COPOL), None)
    cross = next((p for p in pols if p.upper() in CROSSPOL), None)
    return co, cross


def _scale(v: np.ndarray, lo: float, hi: float) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        out = np.clip((v - lo) * (255.0 / (hi - lo)), 0, 255)
    return np.nan_to_num(out, nan=0.0).round().astype(np.uint8)


def _colour(db: dict, band: str) -> np.ndarray:
    """{pol: (h, w) dB} -> (h, w, 4) uint8 RGBA, transparent where invalid. See the module docstring."""
    rng = COLOUR_DB[band]
    co, cross = _co_cross(db)
    if co is not None and cross is not None:
        c, x = db[co], db[cross]
        channels = (_scale(c, *rng["co"]), _scale(x, *rng["cross"]), _scale(c - x, *rng["ratio"]))
        ok = np.isfinite(c) & np.isfinite(x)
    else:
        pol = co or cross or next(iter(db))
        grey = _scale(db[pol], *rng["cross" if pol.upper() in CROSSPOL else "co"])
        channels, ok = (grey, grey, grey), np.isfinite(db[pol])
    rgba = np.zeros(ok.shape + (4,), dtype=np.uint8)
    for i, channel in enumerate(channels):
        rgba[..., i] = np.where(ok, channel, 0)
    rgba[..., 3] = np.where(ok, 255, 0)
    return rgba


def _median_power(arr, window: slice) -> np.ndarray:
    """Per-pixel median over the passes in `window`, linear power; NaN where no pass is usable."""
    block = np.array(arr[window], dtype=np.float32)
    block[~(np.isfinite(block) & (block > 0))] = np.nan
    return _nanmedian(block)


def _block_mean(power: np.ndarray, k: int) -> np.ndarray:
    """Mean over k x k blocks (linear power, NaN skipped); the grid is padded with NaN to a multiple of k."""
    ny, nx = power.shape
    padded = np.pad(power, ((0, -ny % k), (0, -nx % k)), constant_values=np.nan)
    blocks = padded.reshape(padded.shape[0] // k, k, padded.shape[1] // k, k)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN blocks
        return np.nanmean(blocks, axis=(1, 3))


@dataclass
class _Pictures:
    """A run's before / after composites at full grid resolution, in linear power."""
    band: str
    power: dict  # "before" | "after" -> {pol: (y, x)}
    dates: dict  # "before" | "after" -> list of the pass dates used

    def date(self, when: str) -> str:
        """The picture's date: the middle one of the passes it combines."""
        used = self.dates[when]
        return _iso(used[len(used) // 2])


def _pictures(run: Run, n_before: int, n_after: int) -> _Pictures:
    n_t = len(run.dates)
    n_b = max(1, min(n_before, n_t - 1))
    n_a = max(1, min(n_after, n_t - n_b))  # the two windows never overlap (same rule as change.py)
    windows = {"before": slice(0, n_b), "after": slice(n_t - n_a, n_t)}
    power = {when: {p: _median_power(arr, w) for p, arr in run.stack.items()} for when, w in windows.items()}
    dates = {when: list(run.dates[w]) for when, w in windows.items()}
    return _Pictures(_band(run), power, dates)


def _site_picture(power: dict, band: str, run: Run, path: Path) -> list:
    """Write the site picture; return its corners [lon, lat]: top-left, top-right, bottom-right, bottom-left."""
    ny, nx = next(iter(power.values())).shape
    k = max(1, math.ceil(max(ny, nx) / MAX_LAYER_PX))
    if k > 1:
        power = {p: _block_mean(v, k) for p, v in power.items()}
    rgba = _colour({p: _db(v) for p, v in power.items()}, band)
    _save_png(rgba, path, MAX_PNG_BYTES)
    h, w = rgba.shape[:2]
    cols, rows = w * k, h * k  # the picture's extent in grid pixels (includes any padding)
    a, b, c, d, e, f = run.transform
    corner_cols, corner_rows = np.array([0, cols, cols, 0]), np.array([0, 0, rows, rows])
    xs, ys = a * corner_cols + b * corner_rows + c, d * corner_cols + e * corner_rows + f
    lon, lat = _transformer(run.epsg, 4326).transform(xs, ys)
    return [[round(float(lo), 6), round(float(la), 6)] for lo, la in zip(lon, lat)]


def _layer_text(run: Run, pics: _Pictures, when: str) -> tuple:
    used = pics.dates[when]
    satellite = re.sub(r"\s+[A-Za-z]-band$", "", run.sensor.strip())
    title = f"{satellite} radar, {when} ({_span(used[0], used[-1], ' to ')})"
    passes = f"{len(used)} passes" if len(used) > 1 else "1 pass"
    head = f"Radar picture from {satellite}: the typical echo of {passes}, {_span(used[0], used[-1], ' to ')}."
    co, cross = _co_cross(run.stack)
    if co is not None and cross is not None:
        body = (f" Red = surface echo ({co.upper()}), strong from bare ground and buildings. Green = vegetation echo"
                f" ({cross.upper()}), strong from trees. Blue = how much stronger the surface echo is than the"
                " vegetation echo. Woodland looks green-yellow, bare or farmed ground purple-blue, buildings light"
                " pink to white, water dark blue.")
    else:
        pol = co or cross or next(iter(run.stack))
        source = "trees and bushes" if pol.upper() in CROSSPOL else "bare ground and buildings"
        body = f" Shades of grey: brighter = stronger {_echo(pol)} ({pol.upper()}), mostly from {source}."
    return title, head + body + " Transparent = no data."


# ---------------------------------------------------------------- evidence crops

def _fit(lo: int, hi: int, n: int) -> tuple:
    """Shift [lo, hi) inside [0, n) keeping its length where possible."""
    if lo < 0:
        hi, lo = hi - lo, 0
    if hi > n:
        lo, hi = max(0, lo - (hi - n)), n
    return lo, hi


def _crop_window(bbox: tuple, shape: tuple) -> tuple:
    r0, c0, r1, c1 = bbox
    margin = max(EVIDENCE_MARGIN_PX, round(EVIDENCE_MARGIN_FRAC * max(r1 - r0, c1 - c0)))
    r0, r1, c0, c1 = r0 - margin, r1 + margin, c0 - margin, c1 + margin
    max_aspect = EVIDENCE_LONG_MAX / EVIDENCE_SHORT_MIN  # widen the short side so both size limits can hold
    h, w = r1 - r0, c1 - c0
    if w > h * max_aspect:
        grow = math.ceil(w / max_aspect) - h
        r0, r1 = r0 - grow // 2, r1 + grow - grow // 2
    elif h > w * max_aspect:
        grow = math.ceil(h / max_aspect) - w
        c0, c1 = c0 - grow // 2, c1 + grow - grow // 2
    r0, r1 = _fit(r0, r1, shape[0])
    c0, c1 = _fit(c0, c1, shape[1])
    return slice(r0, r1), slice(c0, c1)


def _evidence_size(h: int, w: int) -> tuple:
    """Output (width, height): integer zoom so the short side reaches EVIDENCE_SHORT_MIN, capped by the long side."""
    zoom = max(1, math.ceil(EVIDENCE_SHORT_MIN / min(h, w)))
    if max(h, w) * zoom > EVIDENCE_LONG_MAX:
        zoom = EVIDENCE_LONG_MAX / max(h, w)
    return max(1, round(w * zoom)), max(1, round(h * zoom))


def _write_evidence(run: Run, pics: _Pictures, region, paths: dict) -> None:
    window = _crop_window(region.bbox, run.result.labels.shape)
    member = run.result.labels[window] == region.label
    size = _evidence_size(*member.shape)
    big = np.array(Image.fromarray(member.astype(np.uint8) * 255).resize(size, Image.Resampling.NEAREST)) > 0
    ring = ndimage.binary_dilation(big, structure=SQUARE3, iterations=OUTLINE_PX) & ~big
    for when in ("before", "after"):
        rgba = _colour({p: _db(v[window]) for p, v in pics.power[when].items()}, pics.band)
        out = np.array(Image.fromarray(rgba).resize(size, Image.Resampling.NEAREST))
        out[ring] = OUTLINE_RGBA
        _save_png(out, paths[when])


# ---------------------------------------------------------------- series

def _series(pol: str, sensor: str, dates, values) -> dict:
    return {"name": f"{_echo(pol).capitalize()} ({pol.upper()})", "unit": "dB", "sensor": sensor,
            "dates": [_iso(d) for d in dates], "values": [_num(v, 2) for v in values]}


def _pixel_centres(run: Run, region) -> tuple:
    r0, c0, r1, c1 = region.bbox
    rows, cols = np.nonzero(run.result.labels[r0:r1, c0:c1] == region.label)
    a, b, c, d, e, f = run.transform
    cc, rr = cols + c0 + 0.5, rows + r0 + 0.5
    return a * cc + b * rr + c, d * cc + e * rr + f


def _sample(other: Run, x: np.ndarray, y: np.ndarray, epsg: int):
    """Mean series of `other` over the pixels holding points (x, y) [CRS epsg]; None if fewer than MIN_FOOTPRINT_PX."""
    if other.epsg != epsg:
        x, y = _transformer(epsg, other.epsg).transform(x, y)
    inv = ~Affine(*other.transform)
    col_f, row_f = inv.a * x + inv.b * y + inv.c, inv.d * x + inv.e * y + inv.f
    _, ny, nx = np.shape(next(iter(other.stack.values())))
    ok = np.isfinite(col_f) & np.isfinite(row_f)
    col, row = np.floor(col_f[ok]).astype(np.int64), np.floor(row_f[ok]).astype(np.int64)  # pixel holding the point
    inside = (row >= 0) & (row < ny) & (col >= 0) & (col < nx)
    flat = np.unique(row[inside] * nx + col[inside])  # each of the other grid's pixels counts once
    if flat.size < MIN_FOOTPRINT_PX:
        return None
    rows, cols = np.divmod(flat, nx)
    r0, c0 = rows.min(), cols.min()
    out = {}
    for pol in _ordered(other.stack):
        block = np.asarray(other.stack[pol][:, r0:rows.max() + 1, c0:cols.max() + 1], dtype=np.float64)
        block = block[:, rows - r0, cols - c0]
        usable = np.isfinite(block) & (block > 0)
        count = usable.sum(axis=1)
        mean = np.where(usable, block, 0.0).sum(axis=1) / np.maximum(count, 1)  # mean in linear power, then dB
        with np.errstate(divide="ignore"):
            out[pol] = np.where(count > 0, 10 * np.log10(np.maximum(mean, 1e-30)), np.nan)
    return out


def _series_doc(runs: list, i: int, region) -> dict:
    run = runs[i]
    series = [_series(p, run.sensor, region.series["dates"], region.series[f"{p}_dB"]) for p in _ordered(run.stack)]
    if len(runs) > 1:
        x, y = _pixel_centres(run, region)
        for j, other in enumerate(runs):
            if j == i:
                continue
            sampled = _sample(other, x, y, run.epsg)
            if sampled is not None:
                series += [_series(p, other.sensor, other.dates, v) for p, v in sampled.items()]
    return {"series": series, "events": [{"date": _iso(region.first_date), "label": "Change first seen"}]}


# ---------------------------------------------------------------- changes

def _signal(sig) -> dict | None:
    if not sig:
        return None
    return {"metric": str(sig["metric"]), **{k: _num(sig.get(k), 1) for k in ("before", "after", "delta")}}


def _explain(kind: str, signal: dict | None, first, last) -> str:
    when = f"on {_span(first, first, '')}" if _iso(first) == _iso(last) else f"between {_span(first, last, ' and ')}"
    pattern = PATTERNS.get(kind, PATTERNS["other"])
    delta = signal.get("delta") if signal else None
    if not delta:  # None or 0
        return f"Radar saw the ground change {when}, {pattern}."
    amount = f"{abs(delta):.0f}" if abs(delta) >= 1.5 else f"{abs(delta):.1f}"
    echo = _echo(signal["metric"].split("_")[0])
    return f"Radar saw the {echo} {'drop' if delta < 0 else 'rise'} by {amount} dB {when}, {pattern}."


def _layer_ids(runs: list) -> list:
    ids, seen = [], Counter()
    for run in runs:
        base = re.sub(r"[^a-z0-9]+", "_", run.sensor.lower()).strip("_") or "radar"
        seen[base] += 1
        ids.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return ids


def write_site(site_dir, site_id: str, runs: list, n_before: int = 3, n_after: int = 3) -> dict:
    """Write changes.geojson, layers.json + layers/*.png, evidence/*.png, series/*.json under site_dir.

    Every region of every run becomes one change, ids `<site_id>-0001`... ordered by first_date, then
    area descending. Files left in layers/, evidence/ and series/ by an earlier export are removed;
    story.json and anything else in site_dir are left alone. Returns {"changes", "area_ha", "by_type"}.
    """
    site_dir = Path(site_dir)
    for sub in ("layers", "evidence", "series"):
        (site_dir / sub).mkdir(parents=True, exist_ok=True)
    written: set = set()
    pictures = [_pictures(run, n_before, n_after) for run in runs]

    layers = []
    for run, pics, base in zip(runs, pictures, _layer_ids(runs)):
        for when in ("before", "after"):
            rel = f"layers/{base}_{when}.png"
            corners = _site_picture(pics.power[when], pics.band, run, site_dir / rel)
            written.add(rel)
            title, caption = _layer_text(run, pics, when)
            layers.append({"id": f"{base}_{when}", "title": title, "date": pics.date(when),
                           "url": rel, "coordinates": corners, "caption": caption})
    _write_json(site_dir / "layers.json", {"layers": layers})

    # area from the final lon/lat outline on the ellipsoid: grid pixels are not equal-area in every projection
    outlines = [_outlines(run) for run in runs]
    items = [(i, region, max(round(_geodesic_ha(outlines[i][region.label]), 2), 0.01))
             for i, run in enumerate(runs) for region in run.result.regions]
    items.sort(key=lambda it: (_iso(it[1].first_date), -it[2], it[0], it[1].label))
    feats, by_type, total = [], Counter(), 0.0
    for n, (i, region, area) in enumerate(items, start=1):
        run, pics, cid = runs[i], pictures[i], f"{site_id}-{n:04d}"
        files = {"before": f"evidence/{cid}_before.png", "after": f"evidence/{cid}_after.png",
                 "series": f"series/{cid}.json"}
        _write_evidence(run, pics, region, {k: site_dir / files[k] for k in ("before", "after")})
        _write_json(site_dir / files["series"], _series_doc(runs, i, region))
        written.update(files.values())
        evidence = {**files, "before_date": pics.date("before"), "after_date": pics.date("after")}
        signal = _signal(region.signal)
        feats.append({"type": "Feature", "geometry": outlines[i][region.label], "properties": {
            "id": cid, "site": site_id, "type": region.type,
            "first_date": _iso(region.first_date), "last_date": _iso(region.last_date),
            "area_ha": area, "sensor": run.sensor, "signal": signal, "confidence": region.confidence,
            "verdict": None, "reasons": [],
            "explain": _explain(region.type, signal, region.first_date, region.last_date),
            "evidence": evidence,
        }})
        by_type[region.type] += 1
        total += area
    lines = ",\n".join(json.dumps(f, allow_nan=False) for f in feats)  # one change per line: small, diffable
    (site_dir / "changes.geojson").write_text(
        '{"type": "FeatureCollection", "features": [\n' + lines + "\n]}\n", encoding="utf-8")

    for sub, pattern in (("layers", "*.png"), ("evidence", "*.png"), ("series", "*.json")):
        for path in (site_dir / sub).glob(pattern):
            if f"{sub}/{path.name}" not in written:
                path.unlink()
    return {"changes": len(feats), "area_ha": round(total, 2), "by_type": dict(sorted(by_type.items()))}
