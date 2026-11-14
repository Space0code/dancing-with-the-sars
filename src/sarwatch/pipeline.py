"""Site runner: one command from real radar data to a site folder the web app reads.

    python -m sarwatch.pipeline muhos                          # NISAR + Sentinel-1 -> app/data/muhos/
    python -m sarwatch.pipeline muhos --no-s1 --max-dates 2    # cautious first try: two NISAR dates

Steps: search the archive -> one NISAR track / one Sentinel-1 burst (one pixel grid, one scene per date) -> read the
site's window one date at a time into data/stacks/<site>/<sensor>/<YYYY-MM-DD>.npz -> stack the cache (grids checked)
-> sarwatch.change.detect_changes per sensor -> sarwatch.export.write_site -> mark the site ready in sites.json ->
placeholder story.json if there is none -> sarwatch.contract.validate -> summary.

A cached date is never fetched again: an interrupted run resumes, and reruns with other thresholds (--offline) cost no
data. New dates are fetched ends first (first, last, second, second-to-last, ...), so a partial cache still has an early
and a late window to compare. Costs per date: kb/data-nisar-gcov.md ("Measured cost").

The Earthdata Login token comes from $EARTHDATA_TOKEN, else from the repo's .env (EARTHDATA_TOKEN or
EARTH_DATA_TOKEN). It is passed to the readers and never printed or logged.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import numpy as np

from .change import ChangeParams, detect_changes
from .contract import validate

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]  # src/sarwatch/pipeline.py -> repo root
if not (REPO_ROOT / "pyproject.toml").is_file():  # installed elsewhere: assume we run from the repo root
    REPO_ROOT = Path.cwd()
TOKEN_KEYS = ("EARTHDATA_TOKEN", "EARTH_DATA_TOKEN")  # spellings accepted in .env
NISAR, S1 = "nisar", "s1"  # cache folder names
SENSOR_NAMES = {NISAR: "NISAR L-band", S1: "Sentinel-1 C-band"}
POLS = {NISAR: ("HH", "HV"), S1: ("VV", "VH")}
STORY_PLACEHOLDER = ("The written story of this site is coming soon. Until then, the map shows the changes the "
                     "radar found, and each card says what was seen and when.")


class PipelineError(Exception):
    """A problem the person running the command can fix; printed as one line, without a traceback."""


class GridMismatch(PipelineError, ValueError):
    """Two dates of one sensor's stack are not on the same pixel grid."""


# ---------------------------------------------------------------- site definitions


@dataclass
class NisarSettings:
    start: date
    end: date | None = None        # None = up to today
    track: int | None = None       # fix the stack instead of letting pick_track choose
    frame: int | None = None
    direction: str | None = None   # "ASCENDING" | "DESCENDING"
    min_maturity: str = "PROVISIONAL"
    params: ChangeParams = field(default_factory=ChangeParams)  # 20 m pixels: the change-core defaults


@dataclass
class S1Settings:
    start: date
    end: date | None = None
    max_dates: int | None = None     # thin to at most this many dates, spread over the period
    min_gap_days: int | None = None  # or keep scenes at least this far apart
    months: tuple | None = None      # keep only scenes from these months (1-12) of every year: the same season is
                                     # compared across years, so farmland's yearly wet / dry cycle cancels out
    params: ChangeParams = field(default_factory=lambda: ChangeParams(boxcar=3))  # 30 m pixels: smaller window


@dataclass
class Site:
    id: str                       # = folder under app/data and entry in sites.json
    bbox: tuple                   # (west, south, east, north), degrees
    nisar: NisarSettings | None
    s1: S1Settings | None = None
    use_s1: bool = True


SITES = {
    # Google's reported clear-cut; NISAR stack measured on 14 Nov: 11 dates 25 Jun -> 4 Nov 2026, grid EPSG:3413.
    "muhos": Site(
        id="muhos", bbox=(25.94, 64.80, 26.15, 64.89),
        nisar=NisarSettings(start=date(2026, 6, 1), track=157, frame=35, direction="ASCENDING"),
        s1=S1Settings(start=date(2026, 1, 1), end=date(2026, 11, 10), max_dates=30),
    ),
    # Agroparc Penedes; farmland and vineyards all round, so both sensors run with the seasonal guards (#36).
    # NISAR: Jun -> Nov 2026, the late passes include October rain: normalize + hold.
    # Sentinel-1: about one scene a month since 2016, compared summer (Jun-Sep) against summer: the first two
    # summers are the baseline, the 2026 summer the end state, a change is dated where it holds for a whole summer.
    "agroparc": Site(
        id="agroparc", bbox=(1.79, 41.41, 1.91, 41.49),
        nisar=NisarSettings(start=date(2026, 6, 1), track=130, frame=22, direction="ASCENDING",
                            params=ChangeParams(threshold_db=3.0, min_area_ha=1.0, normalize=True, hold=True)),
        s1=S1Settings(start=date(2016, 4, 1), min_gap_days=28, months=(6, 7, 8, 9),
                      params=ChangeParams(boxcar=3, n_early=8, n_late=4, persist=4, threshold_db=3.0,
                                          min_area_ha=1.0, normalize=True, hold=True)),
    ),
}


def _params(site: Site, sensor: str, threshold_db=None, min_area_ha=None, **flags) -> ChangeParams:
    params = (site.nisar if sensor == NISAR else site.s1).params
    pairs = (("threshold_db", threshold_db), ("min_area_ha", min_area_ha), *flags.items())
    changes = {k: v for k, v in pairs if v is not None}
    return dataclasses.replace(params, **changes)


# ---------------------------------------------------------------- token


def load_token(root=None) -> str | None:
    """$EARTHDATA_TOKEN, else EARTHDATA_TOKEN or EARTH_DATA_TOKEN from <repo root>/.env; None if neither is set."""
    token = os.environ.get("EARTHDATA_TOKEN", "").strip()
    if token:
        return token
    path = Path(root or REPO_ROOT) / ".env"
    if not path.is_file():
        return None
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        key = key.removeprefix("export ").strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return next((values[k] for k in TOKEN_KEYS if values.get(k)), None)


# ---------------------------------------------------------------- cache: one .npz per date


@dataclass
class Frame:
    """One date of one sensor over the site window."""
    day: date
    data: dict          # polarization -> (y, x) float32 linear power, NaN = invalid
    transform: tuple    # (a, b, c, d, e, f), pixel corners, as the readers return it
    epsg: int
    bbox: tuple         # the site bbox the window was read for
    source: str         # granule / scene name
    mb: float | None    # MB fetched (1 MB = 1e6 bytes); None if the reader does not report it
    seconds: float


def cache_path(cache_dir, day: date) -> Path:
    return Path(cache_dir) / f"{day.isoformat()}.npz"


def cached_days(cache_dir) -> list[date]:
    paths = Path(cache_dir).glob("*.npz") if Path(cache_dir).is_dir() else []
    return sorted(date.fromisoformat(p.stem) for p in paths if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem))


def save_frame(path, frame: Frame) -> None:
    """Write atomically (temp file + rename), so an interrupted run never leaves a half-written date behind."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    arrays = {f"pol_{p}": np.asarray(a, np.float32) for p, a in frame.data.items()}
    with open(tmp, "wb") as f:
        np.savez_compressed(
            f, transform=np.asarray(frame.transform, float), epsg=np.int64(frame.epsg),
            bbox=np.asarray(frame.bbox, float), source=np.str_(frame.source),
            mb=np.float64(np.nan if frame.mb is None else frame.mb), seconds=np.float64(frame.seconds), **arrays,
        )
    os.replace(tmp, path)


def load_frame(path) -> Frame:
    path = Path(path)
    with np.load(path, allow_pickle=False) as z:
        mb = float(z["mb"])
        return Frame(
            day=date.fromisoformat(path.stem),
            data={k[4:]: z[k] for k in z.files if k.startswith("pol_")},
            transform=tuple(float(v) for v in z["transform"]), epsg=int(z["epsg"]),
            bbox=tuple(float(v) for v in z["bbox"]), source=str(z["source"]),
            mb=None if math.isnan(mb) else mb, seconds=float(z["seconds"]),
        )


def _grid(frame: Frame) -> str:
    shapes = {p: a.shape for p, a in frame.data.items()}
    return f"EPSG {frame.epsg}, shapes {shapes}, transform {frame.transform}"


def _same_grid(a: Frame, b: Frame) -> bool:
    if a.epsg != b.epsg or {p: x.shape for p, x in a.data.items()} != {p: x.shape for p, x in b.data.items()}:
        return False
    return np.allclose(a.transform, b.transform, rtol=0, atol=1e-6 * abs(a.transform[0]))


def _check_bbox(frame: Frame, bbox, where) -> None:
    if not np.allclose(frame.bbox, bbox):
        raise PipelineError(
            f"{where} was read for bbox {frame.bbox}, but the site now uses {tuple(bbox)}: "
            "move that cache folder away to fetch the new window"
        )


def load_stack(cache_dir, days=None, bbox=None) -> tuple[dict, list, tuple, int]:
    """Cached dates as one stack: ({pol: (time, y, x)}, dates, transform, epsg). All dates must share one grid."""
    cache_dir = Path(cache_dir)
    days = cached_days(cache_dir) if days is None else sorted(days)
    if not days:
        raise PipelineError(f"no cached dates in {cache_dir}")
    frames = []
    for day in days:
        frame = load_frame(cache_path(cache_dir, day))
        if bbox is not None:
            _check_bbox(frame, bbox, cache_path(cache_dir, day))
        if frames and not _same_grid(frames[0], frame):
            raise GridMismatch(
                f"{cache_path(cache_dir, day)} is on another grid than {frames[0].day}: {_grid(frame)} vs "
                f"{_grid(frames[0])}. One stack needs one track / frame (NISAR) or one burst (Sentinel-1); "
                "delete the odd date's file (or the folder) and rerun."
            )
        frames.append(frame)
    stack = {p: np.stack([f.data[p] for f in frames]) for p in frames[0].data}
    return stack, [f.day for f in frames], frames[0].transform, frames[0].epsg


# ---------------------------------------------------------------- readers (imported lazily)


def _day_of(item) -> date:
    """Acquisition day of a granule or scene: its start / date / datetime attribute."""
    for attr in ("start", "date", "datetime", "start_time", "time"):
        value = getattr(item, attr, None)
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str) and re.match(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value[:10])
    raise TypeError(f"cannot tell the date of {item!r}")


def _name_of(item) -> str:
    for attr in ("name", "granule", "id", "url"):
        value = getattr(item, attr, None)
        if isinstance(value, str) and value:
            return value
    return repr(item)[:200]


def _nisar_items(site: Site) -> list:
    from . import nisar

    s = site.nisar
    found = nisar.search(site.bbox, s.start, s.end)
    keep = [g for g in found if (s.track is None or g.track == s.track) and (s.frame is None or g.frame == s.frame)
            and (s.direction is None or g.direction == s.direction.upper())]
    picked = nisar.pick_track(keep, s.min_maturity)
    if picked:
        g = picked[0]
        mix = Counter(x.maturity for x in picked)  # a maturity switch inside a stack can fake a step
        log.info("nisar: %d granules found, %d on track %d / frame %d %s -> %d dates (%s)", len(found), len(keep),
                 g.track, g.frame, g.direction.lower(), len(picked), ", ".join(f"{n} {m}" for m, n in mix.items()))
    return [(g.start.date(), g) for g in picked]


def _nisar_fetch(granule, bbox, token) -> Frame:
    from . import nisar

    crop = nisar.read_crop(granule.url, bbox, POLS[NISAR], token)
    return Frame(day=granule.start.date(), data=crop.data, transform=tuple(crop.transform), epsg=int(crop.epsg),
                 bbox=tuple(bbox), source=granule.name, mb=crop.bytes_read / 1e6, seconds=crop.seconds)


def _s1_items(site: Site) -> list:
    from . import s1

    s = site.s1
    found = s1.search(site.bbox, s.start, s.end)
    burst = [sc for sc in s1.pick_burst(found, site.bbox) if s.months is None or _day_of(sc).month in s.months]
    picked = s1.thin(burst, max_dates=s.max_dates, min_gap_days=s.min_gap_days)
    log.info("s1: %d scenes found, %d on the chosen burst, %d after thinning", len(found), len(burst), len(picked))
    return [(_day_of(scene), scene) for scene in picked]


def _s1_fetch(scene, bbox, token) -> Frame:
    from . import s1

    stats = getattr(s1, "last_read_stats", None)  # the reader's own byte estimate for its last read
    if isinstance(stats, dict):
        stats.clear()
    t0 = time.perf_counter()
    stack, dates, transform, epsg = s1.read_stack([scene], bbox, pols=POLS[S1], token=token)
    nbytes = stats.get("bytes") if isinstance(stats, dict) else None
    return Frame(day=_day_of(scene), data={p: a[0] for p, a in stack.items()}, transform=tuple(transform),
                 epsg=int(epsg), bbox=tuple(bbox), source=_name_of(scene),
                 mb=None if nbytes is None else nbytes / 1e6, seconds=time.perf_counter() - t0)


def _in_season(site: Site, sensor: str, days: list) -> list:
    """The cache can hold more dates than the site compares (offline reads them all): keep the S1 months."""
    months = site.s1.months if sensor == S1 and site.s1 else None
    return days if months is None else [d for d in days if d.month in months]


ITEMS = {NISAR: _nisar_items, S1: _s1_items}
FETCH = {NISAR: _nisar_fetch, S1: _s1_fetch}


# ---------------------------------------------------------------- fetch with cache


@dataclass
class Meter:
    """What this run fetched over the network."""
    dates: int = 0
    mb: float = 0.0
    seconds: float = 0.0
    unsized: int = 0  # dates whose reader did not report MB

    def add(self, frame: Frame) -> None:
        self.dates += 1
        self.seconds += frame.seconds
        if frame.mb is None:
            self.unsized += 1
        else:
            self.mb += frame.mb


def _ends_first(items: list) -> list:
    """first, last, second, second-to-last, ...: any prefix keeps an early and a late window."""
    out, lo, hi = [], 0, len(items) - 1
    while lo <= hi:
        out.append(items[lo])
        if hi != lo:
            out.append(items[hi])
        lo, hi = lo + 1, hi - 1
    return out


def collect(sensor: str, site: Site, cache_root, *, offline=False, max_new=None, token=None,
            meter: Meter | None = None) -> list[date]:
    """Make sure the site's dates for one sensor are cached; return the cached dates to use, oldest first.

    Online: search, keep one grid, fetch the dates not cached yet (at most max_new). Offline: every cached date.
    """
    cache_dir = Path(cache_root) / site.id / sensor
    meter = meter if meter is not None else Meter()
    if offline:
        days = cached_days(cache_dir)
        log.info("%s: %d cached dates in %s (offline)", sensor, len(days), cache_dir)
        return days

    items, seen = [], set()
    for day, item in ITEMS[sensor](site):
        if day in seen:
            log.warning("%s: second scene on %s ignored (%s)", sensor, day, _name_of(item))
            continue
        seen.add(day)
        items.append((day, item))
    items.sort(key=lambda it: it[0])
    if not items:
        log.warning("%s: nothing found for %s", sensor, site.id)
        return []
    todo = _ends_first([(d, it) for d, it in items if not cache_path(cache_dir, d).exists()])
    log.info("%s: %d dates (%s .. %s), %d cached, %d to fetch", sensor, len(items), items[0][0], items[-1][0],
             len(items) - len(todo), len(todo))
    if max_new is not None and max_new < len(todo):
        log.info("%s: fetching %d of them now (--max-dates)", sensor, max(max_new, 0))
        todo = todo[:max(max_new, 0)]
    if todo and not token:
        raise PipelineError("fetching needs an Earthdata Login token: set EARTHDATA_TOKEN, or put "
                            "EARTHDATA_TOKEN=... in the .env file at the repo root")

    cached = cached_days(cache_dir)
    ref = load_frame(cache_path(cache_dir, cached[0])) if cached else None
    if ref is not None:
        _check_bbox(ref, site.bbox, cache_path(cache_dir, ref.day))
    for k, (day, item) in enumerate(todo, 1):
        try:
            frame = FETCH[sensor](item, site.bbox, token)
        except (KeyError, ValueError) as exc:  # this granule lacks the band / window: skip the date
            log.warning("%s %s: skipped (%s)", sensor, day, exc)
            continue
        frame.day = day
        if ref is not None and not _same_grid(ref, frame):
            raise GridMismatch(f"{sensor} {day} ({frame.source}) is on another grid than the cached {ref.day}: "
                               f"{_grid(frame)} vs {_grid(ref)}. Not saved.")
        save_frame(cache_path(cache_dir, day), frame)
        ref = ref or frame
        meter.add(frame)
        size = "? MB" if frame.mb is None else f"{frame.mb:.1f} MB"
        log.info("%s %s (%d/%d): %s in %.1f s | this run: %d dates, %.1f MB, %.0f s", sensor, day, k, len(todo),
                 size, frame.seconds, meter.dates, meter.mb, meter.seconds)
    return [d for d, _ in items if cache_path(cache_dir, d).exists()]


# ---------------------------------------------------------------- detect, export, index


def detect(sensor: str, site: Site, cache_root, days: list, params: ChangeParams):
    """Run the change core on the cached stack; an export Run, or None with fewer than two dates."""
    from .export import Run

    if len(days) < 2:
        log.warning("%s: %d date(s) cached, change detection needs at least 2: skipped", sensor, len(days))
        return None
    stack, dates, transform, epsg = load_stack(Path(cache_root) / site.id / sensor, days, site.bbox)
    a, b, _, d, e, _ = transform
    pixel = (math.hypot(a, d), math.hypot(b, e))
    result = detect_changes(stack, dates, pixel, params)
    log.info("%s: %d dates, %d change regions (threshold %.1f dB, min %.2f ha)", sensor, len(dates),
             len(result.regions), params.threshold_db, params.min_area_ha)
    return Run(sensor=SENSOR_NAMES[sensor], result=result, dates=dates, stack=stack, transform=transform, epsg=epsg)


def _site_entry(index_path: Path, site_id: str) -> dict:
    if not index_path.is_file():
        raise PipelineError(f"{index_path} not found (use --out to point at app/data)")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    entry = next((s for s in index.get("sites", []) if s.get("id") == site_id), None)
    if entry is None:
        raise PipelineError(f"{site_id} is not in {index_path}: add its entry (name, center, zoom, bbox) first")
    return entry


SITE_LINES = (("id", "name", "country", "ready", "fixture"), ("center", "zoom", "bbox"), ("time_range",))


def _format_sites(index: dict, nl: str) -> str:
    """sites.json in its hand-written style: one site per block, keys grouped on three lines."""
    blocks = []
    for site in index["sites"]:
        groups = [[k for k in keys if k in site] for keys in SITE_LINES]
        groups[-1] += [k for k in site if not any(k in keys for keys in SITE_LINES)]
        lines = [", ".join(f"{json.dumps(k)}: {json.dumps(site[k], ensure_ascii=False)}" for k in g)
                 for g in groups if g]
        blocks.append("  {" + f",{nl}   ".join(lines) + "}")
    head = [k for k in index if k != "sites"]
    out = ["{"] + [f" {json.dumps(k)}: {json.dumps(index[k])}," for k in head] + [' "sites": [']
    return nl.join(out + [f",{nl}".join(blocks), " ]", "}"]) + nl


def update_sites_index(index_path, site_id: str, time_range: tuple) -> dict:
    """Set the site's ready = true and time_range; every other site and field stays as it was (text included)."""
    index_path = Path(index_path)
    _site_entry(index_path, site_id)
    text = index_path.read_bytes().decode("utf-8")
    index = json.loads(text)
    entry = next(s for s in index["sites"] if s.get("id") == site_id)
    entry["ready"] = True
    entry["time_range"] = [str(time_range[0]), str(time_range[1])]
    new = None
    m = re.search(r'\{[^{}]*"id":\s*' + re.escape(json.dumps(site_id)) + r"[^{}]*\}", text)
    if m:  # edit the two values in place, so the hand-written layout survives
        block, n1 = re.subn(r'"ready":\s*(?:true|false)', '"ready": true', m.group(0))
        block, n2 = re.subn(r'"time_range":\s*\[[^\]]*\]', '"time_range": ' + json.dumps(entry["time_range"]), block)
        if n1 == n2 == 1:
            new = text[:m.start()] + block + text[m.end():]
    if new is None or json.loads(new) != index:
        new = _format_sites(index, "\r\n" if "\r\n" in text else "\n")
    index_path.write_bytes(new.encode("utf-8"))
    return entry


def ensure_story(site_dir, headline: str) -> bool:
    """Write a minimal story.json if there is none; never touch an existing one (the verdict track owns it)."""
    path = Path(site_dir) / "story.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    story = {"headline": headline, "story": [STORY_PLACEHOLDER], "events": [], "sources": []}
    try:
        with open(path, "x", encoding="utf-8") as f:
            f.write(json.dumps(story, indent=1, ensure_ascii=False) + "\n")
    except FileExistsError:
        return False
    return True


def _tally(site_dir: Path, key: str) -> dict:
    """{value of property `key`: [changes, hectares]} over the site's changes.geojson."""
    path = site_dir / "changes.geojson"
    out = defaultdict(lambda: [0, 0.0])
    for feature in json.loads(path.read_text(encoding="utf-8")).get("features", []) if path.is_file() else []:
        p = feature.get("properties", {})
        out[p.get(key, "?")][0] += 1
        out[p.get(key, "?")][1] += float(p.get("area_ha") or 0)
    return dict(sorted(out.items()))


# ---------------------------------------------------------------- the run


def run(site_id: str, out="app/data", cache="data/stacks", *, sensors=(NISAR, S1), offline=False, fetch_only=False,
        max_new=None, threshold_db=None, min_area_ha=None, normalize=None, hold=None) -> int:
    """The whole site run; prints a summary. Returns 0 if the data passes the contract, 1 if not."""
    site = SITES[site_id]
    out, cache = Path(out), Path(cache)
    use = [s for s in sensors if (s == NISAR and site.nisar) or (s == S1 and site.s1 and site.use_s1)]
    if not use:
        raise PipelineError(f"{site_id}: no sensor left to run")
    entry = None if fetch_only else _site_entry(out / "sites.json", site_id)  # fail before spending data
    token = None if offline else load_token()
    meter, days = Meter(), {}
    for sensor in use:
        left = None if max_new is None else max_new - meter.dates
        days[sensor] = _in_season(site, sensor, collect(sensor, site, cache, offline=offline, max_new=left,
                                                        token=token, meter=meter))
    if offline and not any(days.values()):
        raise PipelineError(f"--offline: nothing cached for {site_id} under {cache / site_id}; "
                            "run once without --offline to fetch the dates")

    def summary(per_sensor=None) -> list:
        lines = [f"{site_id}: {'fetched' if fetch_only else 'done'}"]
        for sensor in use:
            d, name = days[sensor], SENSOR_NAMES[sensor]
            span = f"{d[0]} .. {d[-1]}" if d else "-"
            found = "" if per_sensor is None else f"  {per_sensor.get(name, [0])[0]} changes"
            lines.append(f"  {name:<18} {len(d):>3} dates  {span}{found}")
        unsized = f" ({meter.unsized} of them not in the MB: their reader does not report size)" if meter.unsized else ""
        return lines + [f"  fetched this run: {meter.dates} dates, {meter.mb:.1f} MB, {meter.seconds:.0f} s{unsized}"]

    if fetch_only:
        print("\n".join(summary()))
        return 0

    flags = {"normalize": normalize, "hold": hold}
    runs = [r for r in (detect(s, site, cache, days[s], _params(site, s, threshold_db, min_area_ha, **flags))
                        for s in use) if r]
    if not runs:
        raise PipelineError(f"{site_id}: no sensor has two cached dates, nothing to detect")
    from .export import write_site

    site_dir = out / site_id
    write_site(site_dir, site_id, runs)
    first, last = min(r.dates[0] for r in runs), max(r.dates[-1] for r in runs)
    update_sites_index(out / "sites.json", site_id, (first, last))
    if ensure_story(site_dir, entry.get("name") or site_id):
        log.info("wrote a placeholder %s", site_dir / "story.json")
    problems = validate(out)

    by_type = _tally(site_dir, "type")
    total = sum(n for n, _ in by_type.values())
    kinds = ", ".join(f"{k} {n} = {ha:.1f} ha" for k, (n, ha) in by_type.items())
    lines = summary(_tally(site_dir, "sensor"))
    lines.append(f"  changes: {total}" + (f"  ({kinds})" if kinds else ""))
    lines.append(f"  sites.json: {site_id} ready, time_range {first} .. {last}")
    lines.append("  contract: OK" if not problems else f"  contract: {len(problems)} problem(s)")
    lines += [f"    {p}" for p in problems]
    print("\n".join(lines))
    return 1 if problems else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m sarwatch.pipeline", description=__doc__.split("\n\n")[0])
    p.add_argument("site", choices=sorted(SITES))
    p.add_argument("--out", default=str(REPO_ROOT / "app" / "data"), help="app data folder (default: app/data)")
    p.add_argument("--cache", default=str(REPO_ROOT / "data" / "stacks"), help="date cache (default: data/stacks)")
    p.add_argument("--fetch-only", action="store_true", help="fill the cache, then stop")
    p.add_argument("--offline", action="store_true", help="use cached dates only, no network")
    p.add_argument("--max-dates", type=int, metavar="N", help="fetch at most N new dates this run (all sensors)")
    p.add_argument("--no-s1", action="store_true", help="skip Sentinel-1")
    p.add_argument("--no-nisar", action="store_true", help="skip NISAR")
    p.add_argument("--threshold-db", type=float, help="change threshold in dB (default 3.0 for both sensors)")
    p.add_argument("--min-area-ha", type=float, help="smallest change kept, hectares (default 0.5)")
    p.add_argument("--normalize", action="store_true", default=None,
                   help="remove each pass's scene-wide dB shift (rain, drought) before comparing")
    p.add_argument("--hold", action="store_true", default=None,
                   help="a change must show in every one of the last passes, not just their median")
    args = p.parse_args(argv)
    if args.fetch_only and args.offline:
        p.error("--fetch-only and --offline exclude each other")
    sensors = tuple(s for s, off in ((NISAR, args.no_nisar), (S1, args.no_s1)) if not off)
    if not sensors:
        p.error("--no-nisar and --no-s1 leave nothing to run")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log.setLevel(logging.INFO)
    try:
        return run(args.site, args.out, args.cache, sensors=sensors, offline=args.offline,
                   fetch_only=args.fetch_only, max_new=args.max_dates, threshold_db=args.threshold_db,
                   min_area_ha=args.min_area_ha, normalize=args.normalize, hold=args.hold)
    except (PipelineError, PermissionError) as exc:  # PermissionError: the archive refused the token
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
