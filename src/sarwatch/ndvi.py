"""NDVI, snow and water share per change, from NASA's HLS (Harmonized Landsat Sentinel-2) product.

    python -m sarwatch.ndvi <site> [--cache <dir>] [--offline]

For every change of app/data/<site>/changes.geojson it reads small HLS windows (30 m, one granule per date), takes the
**mean NDVI inside the change's polygon** on every clear date and writes two optional blocks into the change's series
file (app/data/<site>/series/<id>.json); everything else in the file is left as it was:

    "ndvi":    {"sensor": ..., "dates": [...], "values": [...], "before": 0.71, "after": 0.28}
    "surface": {"snow_share": 0.0-1.0 | null, "water_share": 0.0-1.0 | null, "dates_checked": [...]}

NDVI = (NIR - red) / (NIR + red). HLS bands (reflectance x 10000, int16, -9999 = no data): red = B04 in both products;
near-infrared = B8A in HLSS30 (Sentinel-2, ESA) and B05 in HLSL30 (Landsat 8/9, NASA/USGS).

Fmask (uint8, from the HLS User Guide v2.0, table of the quality layer; 255 = no data):
bit 0 cirrus (reserved) - bit 1 cloud - bit 2 adjacent to cloud / cloud shadow - bit 3 cloud shadow - bit 4 snow / ice -
bit 5 water - bits 6-7 aerosol level. Used here: "cloud-free" = has data and bits 1, 2, 3 all 0; snow = bit 4; water = bit 5.

Rules (all shares are shares of the polygon's pixels inside the read window):
- A date counts only if >= 60 % of the polygon's pixels are cloud-free. NDVI is the mean over the cloud-free pixels that
  are not snow / ice (snow would read as bare, low NDVI); the date also needs >= 60 % of the polygon to be such pixels.
- before / after = median NDVI of the counted dates before first_date / after last_date, within 365 days (else null).
- snow_share = largest snow / ice share (of the cloud-free pixels) on counted-cloud-free dates within 16 days of
  first_date; water_share = median water share (of the cloud-free pixels) on cloud-free dates after last_date, within 120 days.
- Dates are preselected from the catalogue's scene cloud cover before any mask is read (at most --max-dates, spread over
  the period, plus the clearest scene near each first_date), so downloads stay small.

Cache: <primary checkout>/data/hls/<site>/ndvi/ (gitignored): the search answer and one .npz per granule window.
--offline reads only from there and reproduces the output. The Earthdata token is read by hls / pipeline.load_token from
the environment or the primary checkout's .env; it is never printed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from . import distalert, hls

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SENSOR = "HLS (Landsat, Sentinel-2)"
NIR = {"S30": "B8A", "L30": "B05"}
RED = "B04"
CLOUD_BITS = (1, 2, 3)
SNOW_BIT, WATER_BIT = 4, 5
MIN_CLEAR = 0.6
SNOW_DAYS, WATER_DAYS, NDVI_DAYS = 16, 120, 365
MAX_CLOUD = 60.0          # catalogue scene cloud cover (%) above which a date is not considered
CLUSTER_DEG = 0.4         # windows are shared by changes that fit in a box this wide
MARGIN_DEG = 0.001
SITE_DEFAULTS = {         # period start, first_date filter, max dates
    "muhos": dict(start="2025-06-01", first_from=None, max_dates=30),
    "barcelona": dict(start="2022-01-01", first_from="2023-01-01", max_dates=20),
}


# ------------------------------------------------------------------ pure pieces

def cloud_free(fmask: np.ndarray) -> np.ndarray:
    bad = np.zeros(fmask.shape, bool)
    for bit in CLOUD_BITS:
        bad |= ((fmask >> bit) & 1) == 1
    return (fmask != hls.FMASK_NODATA) & ~bad


def flag(fmask: np.ndarray, bit: int) -> np.ndarray:
    return (fmask != hls.FMASK_NODATA) & (((fmask >> bit) & 1) == 1)


def ndvi_of(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """NDVI float32 per pixel, NaN where a band has no data or red + nir <= 0."""
    r = red.astype(np.float32) / hls.SCALE
    n = nir.astype(np.float32) / hls.SCALE
    ok = (red != hls.NODATA) & (nir != hls.NODATA) & (r + n > 0)
    out = np.full(red.shape, np.nan, np.float32)
    out[ok] = (n[ok] - r[ok]) / (n[ok] + r[ok])
    return np.clip(out, -1.0, 1.0)


def polygon_mask(geometry: dict, grid: dict, shape: tuple) -> np.ndarray:
    """Boolean raster of the pixels whose centre lies in the lon/lat geometry (all touched pixels if none do)."""
    from rasterio.features import geometry_mask
    from rasterio.transform import Affine
    from rasterio.warp import transform_geom

    geom = transform_geom("EPSG:4326", f"EPSG:{grid['epsg']}", geometry)
    tr = Affine(grid["a"], 0, grid["x0"], 0, grid["e"], grid["y0"])
    m = ~geometry_mask([geom], out_shape=shape, transform=tr, all_touched=False)
    if not m.any():
        m = ~geometry_mask([geom], out_shape=shape, transform=tr, all_touched=True)
    return m


def measure(mask: np.ndarray, fmask: np.ndarray, ndvi: np.ndarray | None) -> dict | None:
    """One date, one polygon: clear share, snow / water share of the cloud-free pixels, mean NDVI (or None)."""
    n = int(mask.sum())
    if n == 0:
        return None
    free = mask & cloud_free(fmask)
    nfree = int(free.sum())
    out = {"clear": nfree / n, "snow": None, "water": None, "ndvi": None}
    if nfree == 0:
        return out
    out["snow"] = float((free & flag(fmask, SNOW_BIT)).sum()) / nfree
    out["water"] = float((free & flag(fmask, WATER_BIT)).sum()) / nfree
    if ndvi is not None:
        use = free & ~flag(fmask, SNOW_BIT) & np.isfinite(ndvi)
        if use.sum() / n >= MIN_CLEAR:
            out["ndvi"] = float(ndvi[use].mean())
    return out


def select_granules(granules: list, first_dates: list, max_dates: int) -> list:
    """At most max_dates granules, one per day: the clearest per time bin over the period, then swap in the clearest
    scene within SNOW_DAYS of each first_date that has none. Uses only the catalogue's cloud cover."""
    best = {}
    for g in granules:
        c = g.extra.get("cloud")
        if c is None or c > MAX_CLOUD:
            continue
        d = g.start.date()
        if d not in best or (c, g.name) < (best[d].extra["cloud"], best[d].name):
            best[d] = g
    days = sorted(best)
    if not days:
        return []
    if len(days) <= max_dates:
        return [best[d] for d in days]
    t0, span = days[0].toordinal(), max(days[-1].toordinal() - days[0].toordinal(), 1)
    bins = {}
    for d in days:
        b = min(int((d.toordinal() - t0) / span * max_dates), max_dates - 1)
        if b not in bins or (best[d].extra["cloud"], d) < (best[bins[b]].extra["cloud"], bins[b]):
            bins[b] = d
    chosen = sorted(bins.values())
    for fd in sorted(set(first_dates)):
        if any(abs((d - fd).days) <= SNOW_DAYS for d in chosen):
            continue
        near = [d for d in days if abs((d - fd).days) <= SNOW_DAYS]
        if not near:
            continue
        pick = min(near, key=lambda d: (best[d].extra["cloud"], d))
        if len(chosen) >= max_dates:   # drop the date with the smallest gap to its neighbour
            gaps = [(min([abs(chosen[i].toordinal() - chosen[j].toordinal()) for j in (i - 1, i + 1)
                          if 0 <= j < len(chosen)] or [10 ** 9]), i) for i in range(len(chosen))]
            chosen.pop(min(gaps)[1])
        chosen = sorted(chosen + [pick])
    return [best[d] for d in chosen]


def median(values: list):
    return float(np.median(values)) if values else None


def build_blocks(change: dict, rows: list) -> tuple:
    """(ndvi block or None, surface block) for one change from its per-date measurements
    rows = [{"date": date, "clear": ., "snow": ., "water": ., "ndvi": . or None}]."""
    first, last = date.fromisoformat(change["first_date"]), date.fromisoformat(change["last_date"])
    rows = sorted(rows, key=lambda r: r["date"])
    ok = [r for r in rows if r["ndvi"] is not None and r["clear"] >= MIN_CLEAR]
    block = None
    if ok:
        before = [r["ndvi"] for r in ok if first - timedelta(days=NDVI_DAYS) <= r["date"] < first]
        after = [r["ndvi"] for r in ok if last < r["date"] <= last + timedelta(days=NDVI_DAYS)]
        block = {"sensor": SENSOR, "dates": [r["date"].isoformat() for r in ok],
                 "values": [round(r["ndvi"], 2) for r in ok],
                 "before": None if not before else round(median(before), 2),
                 "after": None if not after else round(median(after), 2)}
    free = [r for r in rows if r["clear"] >= MIN_CLEAR and r["snow"] is not None]
    near = [r for r in free if abs((r["date"] - first).days) <= SNOW_DAYS]
    later = [r for r in free if last < r["date"] <= last + timedelta(days=WATER_DAYS)]
    surface = {"snow_share": None if not near else round(max(r["snow"] for r in near), 2),
               "water_share": None if not later else round(median([r["water"] for r in later]), 2),
               "dates_checked": sorted({r["date"].isoformat() for r in near + later})}
    return block, surface


def write_blocks(path: Path, ndvi_block: dict | None, surface: dict) -> None:
    """Add or replace the two blocks in a series file; every other key and its order stay as they are."""
    raw = path.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    data = json.loads(raw)
    data.pop("ndvi", None)
    data.pop("surface", None)
    if ndvi_block is not None:
        data["ndvi"] = ndvi_block
    data["surface"] = surface
    text = json.dumps(data, indent=1, ensure_ascii=False)
    path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))


# ------------------------------------------------------------------ geography and cache

def primary_root() -> Path:
    """The primary checkout (the worktrees share its data/ and .env)."""
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO_ROOT,
                                capture_output=True, text=True, check=True).stdout.strip()
        return Path(common).parent
    except Exception:
        return REPO_ROOT


def clusters(boxes: list) -> list:
    """Greedy groups of box indices whose union stays within CLUSTER_DEG on both sides."""
    groups = []
    for i in sorted(range(len(boxes)), key=lambda k: (boxes[k][0], boxes[k][1])):
        for grp in groups:
            u = union([boxes[k] for k in grp] + [boxes[i]])
            if u[2] - u[0] <= CLUSTER_DEG and u[3] - u[1] <= CLUSTER_DEG:
                grp.append(i)
                break
        else:
            groups.append([i])
    return groups


def union(boxes: list) -> tuple:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def granule_to_json(g) -> dict:
    return {"name": g.name, "tile": g.tile, "start": g.start.isoformat(), "sensor": g.sensor, "urls": g.urls,
            "footprint": g.footprint, "cloud": g.extra.get("cloud")}


def granule_from_json(d: dict):
    return distalert.Granule(name=d["name"], tile=d["tile"], start=datetime.fromisoformat(d["start"]),
                             sensor=d["sensor"], urls=d["urls"], footprint=d["footprint"],
                             extra={"produced": "", "cloud": d["cloud"]})


def window_file(cache: Path, granule, bbox) -> Path:
    key = hashlib.sha1(",".join(f"{v:.5f}" for v in bbox).encode()).hexdigest()[:10]
    return cache / f"{granule.name}_{key}.npz"


def read_window(granule, bbox, cache: Path, offline: bool, token, stats: dict, budget) -> dict | None:
    """{"fmask", "red", "nir" (or None), "grid"} for one granule window, from the cache or remote; None if unavailable."""
    path = window_file(cache, granule, bbox)
    if path.is_file():
        with np.load(path, allow_pickle=False) as z:
            grid = json.loads(str(z["grid"]))
            return {"fmask": z["fmask"], "red": z["red"] if "red" in z else None,
                    "nir": z["nir"] if "nir" in z else None, "grid": grid}
    if offline or budget():
        return None
    try:
        fmask, grid = hls.read_band(granule, hls.FMASK, bbox, token, stats)
        out = {"fmask": fmask, "red": None, "nir": None, "grid": grid}
        return out
    except Exception as exc:
        log.warning("%s: unreadable (%s)", granule.name, exc)
        return None


def add_bands(granule, bbox, win: dict, cache: Path, token, stats: dict) -> None:
    """Read red and NIR into win and store the window in the cache."""
    try:
        win["red"], _ = hls.read_band(granule, RED, bbox, token, stats)
        win["nir"], _ = hls.read_band(granule, NIR[granule.sensor], bbox, token, stats)
    except Exception as exc:
        log.warning("%s: bands unreadable (%s)", granule.name, exc)
        win["red"] = win["nir"] = None


def save_window(cache: Path, granule, bbox, win: dict) -> None:
    arrays = {"fmask": win["fmask"], "grid": np.str_(json.dumps(win["grid"]))}
    if win["red"] is not None:
        arrays.update(red=win["red"], nir=win["nir"])
    np.savez_compressed(window_file(cache, granule, bbox), **arrays)


# ------------------------------------------------------------------ the run

def process_granule(granule, bbox, feats: list, cache, offline, token, stats, budget) -> dict:
    """{change id: measurement dict or None} for one granule window."""
    win = read_window(granule, bbox, cache, offline, token, stats, budget)
    if win is None:
        return {}
    fmask, grid = win["fmask"], win["grid"]
    grid = dict(grid)
    if not grid.get("epsg"):   # some files carry no EPSG code: the MGRS tile name gives the UTM zone
        grid["epsg"] = (32600 if granule.tile[2] >= "N" else 32700) + int(granule.tile[:2])
    masks = {f["properties"]["id"]: polygon_mask(f["geometry"], grid, fmask.shape) for f in feats}
    shares = {i: (float((m & cloud_free(fmask)).sum()) / max(int(m.sum()), 1)) for i, m in masks.items()}
    cached_bands = win["red"] is not None
    if not cached_bands and not offline and any(s >= MIN_CLEAR for s in shares.values()) and not budget():
        add_bands(granule, bbox, win, cache, token, stats)
    if not window_file(cache, granule, bbox).is_file() and (win["red"] is not None or not offline):
        save_window(cache, granule, bbox, win)
    ndvi = ndvi_of(win["red"], win["nir"]) if win["red"] is not None else None
    return {i: measure(m, fmask, ndvi if shares[i] >= MIN_CLEAR else None) for i, m in masks.items()}


def run(site: str, cache: Path | None = None, offline: bool = False, max_dates: int | None = None,
        start: str | None = None, first_from: str | None = None, max_gb: float = 3.0, max_minutes: float = 40.0,
        root: Path | None = None) -> dict:
    root = root or REPO_ROOT
    site_dir = root / "app" / "data" / site
    defaults = SITE_DEFAULTS.get(site, dict(start=None, first_from=None, max_dates=30))
    sites = json.loads((root / "app" / "data" / "sites.json").read_text(encoding="utf-8"))["sites"]
    info = next(s for s in sites if s["id"] == site)
    start = start or defaults["start"] or info["time_range"][0]
    first_from = first_from or defaults["first_from"]
    max_dates = max_dates or defaults["max_dates"]
    end = info["time_range"][1]
    cache = (cache or primary_root() / "data" / "hls" / site / "ndvi")
    cache.mkdir(parents=True, exist_ok=True)

    feats = json.loads((site_dir / "changes.geojson").read_text(encoding="utf-8"))["features"]
    if first_from:
        feats = [f for f in feats if f["properties"]["first_date"] >= first_from]
    from shapely.geometry import shape
    boxes = [tuple(shape(f["geometry"]).bounds) for f in feats]
    boxes = [(b[0] - MARGIN_DEG, b[1] - MARGIN_DEG, b[2] + MARGIN_DEG, b[3] + MARGIN_DEG) for b in boxes]

    token = None
    if not offline:
        token = _token_from(primary_root()) or distalert._token(None)   # raises a clear error when missing
    stats = {"bytes": 0}
    t0 = time.time()

    def over_budget() -> bool:
        return stats["bytes"] > max_gb * 1e9 or time.time() - t0 > max_minutes * 60

    rows = {f["properties"]["id"]: [] for f in feats}
    used_dates = set()
    search_file = cache / "search.json"
    searches = json.loads(search_file.read_text(encoding="utf-8")) if search_file.is_file() else {}
    for grp in clusters(boxes):
        bbox = union([boxes[i] for i in grp])
        members = [feats[i] for i in grp]
        key = f"{bbox[0]:.5f},{bbox[1]:.5f},{bbox[2]:.5f},{bbox[3]:.5f}|{start}|{end}"
        if key in searches:
            granules = [granule_from_json(d) for d in searches[key]]
        elif offline:
            log.warning("offline and no cached search for this area: skipped")
            continue
        else:
            granules = hls.search(bbox, datetime.fromisoformat(start + "T00:00:00"),
                                  datetime.fromisoformat(end + "T23:59:59"))
            searches[key] = [granule_to_json(g) for g in granules]
            search_file.write_text(json.dumps(searches), encoding="utf-8")
        tile = hls.pick_tile(granules, bbox)
        granules = [g for g in granules if g.tile == tile]
        chosen = select_granules(granules, [date.fromisoformat(f["properties"]["first_date"]) for f in members],
                                 max_dates)
        log.info("cluster of %d changes, tile %s: %d of %d granules chosen", len(members), tile, len(chosen),
                 len(granules))
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda g: (g, process_granule(g, bbox, members, cache, offline, token, stats,
                                                                  over_budget)), chosen))
        for g, res in results:
            d = g.start.date()
            for cid, m in res.items():
                if m is not None:
                    rows[cid].append({"date": d, **m})
                    used_dates.add(d)
        if over_budget():
            log.warning("budget reached (%.2f GB, %.1f min): stopping", stats["bytes"] / 1e9, (time.time() - t0) / 60)
            break

    summary = {}
    for f in feats:
        p = f["properties"]
        per_day = {}
        for r in rows[p["id"]]:   # two granules of the same day: keep the clearer one
            if r["date"] not in per_day or r["clear"] > per_day[r["date"]]["clear"]:
                per_day[r["date"]] = r
        block, surface = build_blocks(p, list(per_day.values()))
        write_blocks(site_dir / "series" / f"{p['id']}.json", block, surface)
        summary[p["id"]] = (block, surface)
    log.info("%d changes written; %.2f GB read in %.1f min", len(feats), stats["bytes"] / 1e9, (time.time() - t0) / 60)
    return {"summary": summary, "bytes": stats["bytes"], "seconds": time.time() - t0, "dates": sorted(used_dates)}


def _token_from(root: Path):
    from .pipeline import load_token
    return load_token(root)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("site")
    ap.add_argument("--cache", type=Path, help="cache folder (default: <primary checkout>/data/hls/<site>/ndvi)")
    ap.add_argument("--offline", action="store_true", help="read only from the cache")
    ap.add_argument("--max-dates", type=int)
    ap.add_argument("--start", help="first day of the period searched (YYYY-MM-DD)")
    ap.add_argument("--first-from", help="only changes first seen on or after this date")
    ap.add_argument("--max-gb", type=float, default=3.0)
    ap.add_argument("--max-minutes", type=float, default=40.0)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = run(a.site, a.cache, a.offline, a.max_dates, a.start, a.first_from, a.max_gb, a.max_minutes)
    print(f"{len(out['summary'])} changes, {len(out['dates'])} dates used, {out['bytes'] / 1e9:.2f} GB, "
          f"{out['seconds'] / 60:.1f} min")


if __name__ == "__main__":
    main()
