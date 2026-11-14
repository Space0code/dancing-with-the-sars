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
    water_db: float | None = None  # co-pol baseline below this (dB) = open water, left out of detection
    water_grow: int = 1            # pixels of shore masked around the water
    drop_baseline_dated: bool = False  # as S1Settings: a region dated inside the baseline passes is left out


@dataclass
class S1Settings:
    start: date
    end: date | None = None
    max_dates: int | None = None     # thin to at most this many dates, spread over the period
    min_gap_days: int | None = None  # or keep scenes at least this far apart
    months: tuple | None = None      # keep only scenes from these months (1-12) of every year: the same season is
                                     # compared across years, so farmland's yearly wet / dry cycle cancels out
    params: ChangeParams = field(default_factory=lambda: ChangeParams(boxcar=3))  # 30 m pixels: smaller window
    water_db: float | None = None  # co-pol baseline below this (dB) = open water, left out of detection
    water_grow: int = 1            # pixels of shore masked around the water
    drop_baseline_dated: bool = False  # drop regions dated inside the baseline passes: for a short baseline that
                                       # defines "before" (Muhos), such a date is an artefact, not a change

    def __post_init__(self):
        if self.months is not None and (not self.months or not all(isinstance(m, int) and 1 <= m <= 12
                                                                   for m in self.months)):
            raise ValueError(f"S1Settings.months must be a non-empty tuple of months 1-12, got {self.months!r}")


@dataclass
class Site:
    id: str                       # = folder under app/data and entry in sites.json
    bbox: tuple                   # (west, south, east, north), degrees
    nisar: NisarSettings | None
    s1: S1Settings | None = None
    use_s1: bool = True
    skip_dates: tuple[str, ...] = ()  # "YYYY-MM-DD" or "YYYY-MM-DD..YYYY-MM-DD" (inclusive) passes left out of
                                      # detection (frozen ground, snow, ...), for every sensor; they stay cached
    params: dict = field(default_factory=dict)  # ChangeParams overrides for every sensor of this site
    optical: OpticalSettings | None = None  # optical alerts merged with the radar (needs `sources`)
    sources: tuple = ()           # merge.SiteSource per source: with them, detections become one change per place
    primary_scope: str | None = None  # GeoJSON outline (repo path): inside it the optical alerts are the primary
                                      # source, one change per month of first detection, radar attached as sources


@dataclass
class OpticalSettings:
    """OPERA DIST-ALERT optical alerts over the site window, as monthly regions (sarwatch.distregions)."""
    start: date                   # first month-end alert state read
    since: date                   # only alerts first detected from this day on
    min_ha: float = 2.0           # smallest monthly region kept
    blind: tuple[str, ...] = ()   # spans (as skip_dates) when the optical alerts cannot see the ground (snow, dark):
                                  # a state inside them is not a look that showed the old state


# Muhos tuning (#27; quick-looks and the clearing outline in explore/muhos/). Window: the whole clearing with a margin.
# NISAR: 4 Nov 2026 is a frozen pass (HV 2 dB lower over the whole window, forest most); 23 Oct looks normal. The
# summer felling lowers L-band HV by only 1.5-3 dB (slash and stumps stay), so 2.5 dB with a 7 x 7 boxcar. Water and
# 3 pixels of shore are masked (HH baseline below -11 dB; GCOV water sits at -12 to -13 dB here); normalize + hold
# drop the August wetland and lake-shore rises (HH up 4-6 dB around the NW lake, all from one pass).
# Sentinel-1: the baseline is the 21 snow-free passes of 2 Jun - 30 Sep 2025 (n_early), the end state the last 10
# passes (2 Sep - 26 Oct 2026). Oct 2025 - Mar 2026 (wet autumn, frozen ground, dry snow) and Nov 2026 (frozen, like
# NISAR's 4 Nov) are left out: the clearing outline is unchanged against its surroundings up to 23 Mar and darkens from
# 4 Apr, so everything cut over the winter is dated "between 30 Sep 2025 and 4 Apr 2026", never to one March day.
# normalize removes the scene-wide wet-snow drop of April (window VH -18 dB on 4 Apr); 1.5 dB finds the felling, which
# lowers C-band VH by only 1.5-3 dB. The river is masked (summer VV below -16 dB). Regions under 5 ha were VV rises on
# farm fields at the window's south edge (summer 2026 against summer 2025), so 5 ha; the optical alerts carry the small cuts.
# Both: no building is expected here, so only a co-pol rise of 6 dB or more is called a structure (harvested fields
# and logging slash raise it by 2-5 dB); regions are cut into dated parts (NISAR by pass, Sentinel-1 by month).
MUHOS_SKIP = ("2025-05-01..2025-05-31", "2025-10-01..2026-03-31", "2026-11-01..2026-11-30")
MUHOS_PARAMS: dict = {}  # all Muhos tuning is per sensor, below

SITES = {
    # Google's reported clear-cut; NISAR stack measured on 14 Nov: 11 dates 25 Jun -> 4 Nov 2026, grid EPSG:3413.
    "muhos": Site(
        id="muhos", bbox=(26.02, 64.795, 26.20, 64.875),
        nisar=NisarSettings(start=date(2026, 6, 1), track=157, frame=35, direction="ASCENDING",
                            water_db=-11.0, water_grow=3, drop_baseline_dated=True,
                            params=ChangeParams(boxcar=7, threshold_db=2.5, min_area_ha=2.0, normalize=True,
                                                hold=True, split="pass", structure_db=6.0)),
        s1=S1Settings(start=date(2025, 5, 1), end=date(2026, 11, 10), water_db=-16.0, drop_baseline_dated=True,
                      params=ChangeParams(boxcar=5, n_early=21, n_late=10, threshold_db=1.5, persist=3,
                                          min_area_ha=5.0, normalize=True, split="month", structure_db=6.0)),
        skip_dates=MUHOS_SKIP, params=MUHOS_PARAMS,
        optical=OpticalSettings(start=date(2025, 10, 1), since=date(2026, 1, 1), min_ha=2.0,
                                blind=("2025-11-01..2026-03-31",)),
        sources=(
            ("OPERA DIST-ALERT", "optical", "2023-01-01", None, 3, ("clearing", "fire", "other"), (11, 12, 1, 2, 3)),
            ("Sentinel-1 C-band", "radar", "2025-06-02", None, 6, ("clearing", "structure", "earthworks", "other"),
             (11, 12, 1, 2, 3, 4)),
            ("NISAR L-band", "radar", "2026-06-25", None, 12, ("clearing", "structure", "earthworks", "other"),
             (11, 12, 1, 2, 3, 4)),
        ),
        # The clearing: three sources' small parts merged into a confusing patchwork (58 changes) and the radars date
        # the block's edges early (150 m boxcar, spring wet snow), so inside the optical outline the 30 m optical
        # alerts carry the outlines and dates, one change per month; Sentinel-1 and NISAR are attached with shares.
        primary_scope="explore/muhos/clearing_scope.geojson",
    ),
    # Agroparc Penedes; farmland and vineyards all round, so both sensors run with the seasonal guards (#36).
    # NISAR: Jun -> Nov 2026, the late passes include October rain: normalize + hold.
    # Sentinel-1: about one scene a month since 2016, compared summer (Jun-Sep) against summer: the first two
    # summers are the baseline (2016: 3 passes, 2017: 4), the 2026 summer (4) the end state; a change is dated from
    # the pass after which it holds to the end (persist larger than the stack), so a dry year cannot date it early.
    "agroparc": Site(
        id="agroparc", bbox=(1.79, 41.41, 1.91, 41.49),
        nisar=NisarSettings(start=date(2026, 6, 1), track=130, frame=22, direction="ASCENDING",
                            params=ChangeParams(threshold_db=3.0, min_area_ha=1.0, normalize=True, hold=True)),
        s1=S1Settings(start=date(2016, 4, 1), min_gap_days=28, months=(6, 7, 8, 9),
                      params=ChangeParams(boxcar=3, n_early=7, n_late=4, persist=99, threshold_db=3.0,
                                          min_area_ha=1.0, normalize=True, hold=True)),
    ),
}


def _params(site: Site, sensor: str, threshold_db=None, min_area_ha=None, **flags) -> ChangeParams:
    """The sensor's defaults, then the site's overrides, then the command line's."""
    params = (site.nisar if sensor == NISAR else site.s1).params
    known = {f.name for f in dataclasses.fields(ChangeParams)}
    if set(site.params) - known:
        raise PipelineError(f"{site.id}: unknown change parameter(s) {sorted(set(site.params) - known)}; "
                            f"known: {sorted(known)}")
    cli = {k: v for k, v in (("threshold_db", threshold_db), ("min_area_ha", min_area_ha), *flags.items())
           if v is not None}
    return dataclasses.replace(params, **{**site.params, **cli})


def _skip_spans(site: Site, skip_dates=None) -> list:
    """The passes to leave out as inclusive (first, last) spans: the command line's list if given (even empty), else
    the site's. Each entry is "YYYY-MM-DD" or "YYYY-MM-DD..YYYY-MM-DD"."""
    names = site.skip_dates if skip_dates is None else skip_dates
    spans = []
    try:
        for name in (str(n).strip() for n in names):
            if name:
                lo, _, hi = name.partition("..")
                lo, hi = date.fromisoformat(lo.strip()), date.fromisoformat((hi or lo).strip())
                if lo > hi:
                    raise ValueError(f"{name!r} ends before it starts")
                spans.append((lo, hi))
    except ValueError as exc:
        raise PipelineError(f"skip dates must be YYYY-MM-DD or YYYY-MM-DD..YYYY-MM-DD: {exc}") from None
    return spans


def _water_mask(stack: dict, sensor: str, n_early: int, water_db: float, grow: int = 1) -> np.ndarray:
    """valid mask for detect_changes: False on open water (co-pol baseline median below water_db), plus `grow`
    pixels around it (the shore, where the boxcar mixes water into land)."""
    from scipy import ndimage

    arr = stack[POLS[sensor][0]]
    copol = np.nanmedian(arr[:max(1, min(n_early, len(arr) - 1))], axis=0)  # the baseline, as detect_changes takes it
    with np.errstate(divide="ignore", invalid="ignore"):
        water = ndimage.median_filter(10 * np.log10(copol), size=3) < water_db  # NaN compares False
    if grow <= 1:
        return ~ndimage.binary_dilation(water)
    return ~ndimage.binary_dilation(water, structure=np.ones((3, 3), bool), iterations=grow)


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
    on_burst = s1.pick_burst(found, site.bbox)
    burst = [sc for sc in on_burst if s.months is None or _day_of(sc).month in s.months]
    if s.months is not None and len(burst) < 2 <= len(on_burst):
        raise PipelineError(f"{site.id}: s1 months {s.months} keep {len(burst)} of {len(on_burst)} dates; "
                            "nothing to compare")
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


def _drop_baseline_dated(result, last_baseline):
    """Remove regions whose first_date lies in the baseline: a pass that defines "before" cannot be the date of a
    lasting change. Labels are renumbered so that regions[i].label == i + 1 still holds."""
    keep = [r for r in result.regions if r.first_date > last_baseline]
    if len(keep) == len(result.regions):
        return result
    log.info("dropped %d region(s) dated inside the baseline (up to %s)", len(result.regions) - len(keep),
             last_baseline)
    remap = np.zeros(len(result.regions) + 1, dtype=result.labels.dtype)
    for i, r in enumerate(keep, 1):
        remap[r.label] = i
    labels = remap[result.labels]
    first = np.where(labels > 0, result.first_change_idx, -1).astype(result.first_change_idx.dtype)
    regions = [dataclasses.replace(r, label=i) for i, r in enumerate(keep, 1)]
    return dataclasses.replace(result, labels=labels, first_change_idx=first, regions=regions)


def detect(sensor: str, site: Site, cache_root, days: list, params: ChangeParams):
    """Run the change core on the cached stack; an export Run, or None with fewer than two dates."""
    from .export import Run

    if len(days) < 2:
        log.warning("%s: %d date(s) cached, change detection needs at least 2: skipped", sensor, len(days))
        return None
    stack, dates, transform, epsg = load_stack(Path(cache_root) / site.id / sensor, days, site.bbox)
    a, b, _, d, e, _ = transform
    pixel = (math.hypot(a, d), math.hypot(b, e))
    settings = site.nisar if sensor == NISAR else site.s1
    water_db = settings.water_db
    valid = None if water_db is None else _water_mask(stack, sensor, params.n_early, water_db, settings.water_grow)
    if valid is not None:
        log.info("%s: %.1f%% of the window is water (co-pol below %.0f dB), left out", sensor,
                 100 * (1 - valid.mean()), water_db)
    n_early = max(1, min(params.n_early, len(dates) - 1))  # the windows detect_changes will use
    n_late = max(1, min(params.n_late, len(dates) - n_early))
    log.info("%s: baseline %s .. %s (%d passes), end state %s .. %s (%d passes)", sensor, dates[0],
             dates[n_early - 1], n_early, dates[-n_late], dates[-1], n_late)
    result = detect_changes(stack, dates, pixel, params, valid=valid)
    if settings.drop_baseline_dated:
        result = _drop_baseline_dated(result, dates[n_early - 1])
    log.info("%s: %d dates, %d change regions (threshold %.1f dB, min %.2f ha)", sensor, len(dates),
             len(result.regions), params.threshold_db, params.min_area_ha)
    return Run(sensor=SENSOR_NAMES[sensor], result=result, dates=dates, stack=stack, transform=transform, epsg=epsg)


# ---------------------------------------------------------------- several sources -> one change per place

OPTICAL = "OPERA DIST-ALERT"
SHORT = {SENSOR_NAMES[NISAR]: "NISAR", SENSOR_NAMES[S1]: "Sentinel-1", OPTICAL: "optical alert"}


def optical_cache(site_id: str) -> Path:
    return REPO_ROOT / "data" / "cache" / "optical" / f"{site_id}.npz"


def optical_alerts(site: Site, offline: bool):
    """(combined Alerts, month-end state dates) for the site window; read once (under 1 MB) into data/cache/optical.
    None when offline and not cached."""
    from . import distalert as da

    s, path = site.optical, optical_cache(site.id)
    if not path.is_file():
        if offline:
            log.warning("optical alerts: not cached in %s and --offline: left out", path)
            return None
        granules = da.search(site.bbox, s.start)
        tile = da.pick_tile(granules, site.bbox)
        token = load_token()
        reads = [da.read_window(g, site.bbox, token=token, workers=2) for g in da.month_ends(granules, tile)]
        since = np.datetime64(s.since, "D")
        reads = [dataclasses.replace(a, status=np.where(a.first_date >= since, a.status, 0).astype(a.status.dtype),
                                     first_date=np.where(a.first_date >= since, a.first_date, np.datetime64("NaT", "D")),
                                     layers={}) for a in reads]
        alerts = da.combine(reads)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, status=alerts.status, first_date=alerts.first_date.astype("datetime64[D]"),
                            transform=np.asarray(alerts.transform, float), epsg=np.int64(alerts.epsg),
                            granule=np.str_(alerts.granule), acquired=np.str_(alerts.acquired.isoformat()),
                            states=np.array([a.acquired.isoformat() for a in reads]), tile=np.str_(tile))
        log.info("optical alerts: %d month-end states of tile %s read, cached in %s", len(reads), tile, path)
    with np.load(path, allow_pickle=False) as z:
        alerts = da.Alerts(status=z["status"], first_date=z["first_date"], transform=tuple(float(v) for v in z["transform"]),
                           epsg=int(z["epsg"]), granule=str(z["granule"]), acquired=date.fromisoformat(str(z["acquired"])))
        states = [date.fromisoformat(str(d)) for d in z["states"]]
    return alerts, states


def _site_sources(site: Site) -> list:
    from .merge import SiteSource

    return [SiteSource(name=n, kind=k, start=date.fromisoformat(a), end=None if b is None else date.fromisoformat(b),
                       revisit_days=r, sees=frozenset(sees), risky_months=frozenset(risky))
            for n, k, a, b, r, sees, risky in site.sources]


def site_sources_json(site: Site) -> list:
    """sites.json `sources` (kb/data-contract.md)."""
    return [{"sensor": n, "kind": k, "start": a, "end": b, "revisit_days": r, "sees": list(sees),
             "risky_months": list(risky)} for n, k, a, b, r, sees, risky in site.sources]


def _last_look(states: list, day: date, blind: list):
    """The last optical state before `day` that could see the ground (not inside a blind span); None if none."""
    looks = [s for s in states if s < day and not any(lo <= s <= hi for lo, hi in blind)]
    return max(looks) if looks else None


def _say_day(d) -> str:
    from .export import _span

    return _span(d, d, "")


def _sentence(group: list, change, best, sites: dict) -> str:
    """One sentence for the card (the verdict step keeps the first sentence): who saw it first, then who else
    saw the same change (design: kb/multi-sensor-design.md, section 4)."""
    from .export import PATTERNS, _echo, _signal

    setter = change.sensor
    by_source: dict = {}
    for d in group:
        by_source.setdefault(d.source, []).append(d)
    if change.late_start_only:
        began = sites[setter].start if setter in sites else change.first_date
        head = (f"{SHORT.get(setter, setter)} began watching on {_say_day(began)} and shows the ground already changed, "
                f"{PATTERNS.get(change.type, PATTERNS['other'])}; the start date is not known")
    elif by_source[setter][0].kind == "optical":
        head = f"An optical alert found vegetation loss here {change.when}"
    else:
        signal = _signal(best[1].signal) if best and best[1] is not None and best[0].source == setter else None
        delta = signal.get("delta") if signal else None
        pattern = PATTERNS.get(change.type, PATTERNS["other"])
        name = f"{SHORT.get(setter, setter)} radar"
        if delta:
            amount = f"{abs(delta):.0f}" if abs(delta) >= 1.5 else f"{abs(delta):.1f}"
            echo = _echo(signal["metric"].split("_")[0])
            head = f"{name} saw the {echo} {'drop' if delta < 0 else 'rise'} by {amount} dB {change.when}, {pattern}"
        else:
            head = f"{name} saw the ground change {change.when}, {pattern}"
    tails = []
    first_kind = by_source[setter][0].kind
    for name in sorted(by_source, key=lambda n: min(d.first_date for d in by_source[n])):
        if name == setter:
            continue
        ds = by_source[name]
        day = _say_day(min(d.first_date for d in ds))
        if all(d.late_start for d in ds):
            began = sites[name].start if name in sites else ds[0].first_date
            tails.append(f"{SHORT.get(name, name)}, which began watching on {_say_day(began)}, shows it already "
                         "under way")
        elif ds[0].kind == "optical":
            tails.append(f"an optical alert confirmed vegetation loss here by {day}")
        else:
            through = " through clouds" if first_kind == "optical" else ""
            tails.append(f"{SHORT.get(name, name)} radar confirmed it{through} on {day}")
    return "; ".join([head] + tails) + "."


PRIMARY_INSIDE = 0.5  # a detection belongs to the primary scope when this share of its area lies inside it
ATTACH_MIN = 0.10     # an attached source covering less of a part than this did not flag it


def _part_signal(run, outline: dict) -> dict | None:
    """{metric, before, after, delta} of the run's cross-pol mean under the outline: median of the baseline passes
    (as the run's pictures: first 3) and of the last 3 passes."""
    from .export import _outline_centres, _sample

    x, y = _outline_centres(run, outline)
    sampled = _sample(run, x, y, run.epsg)
    if not sampled:
        return None
    pol = next(iter(sampled))  # cross-pol first
    v = np.asarray(sampled[pol], dtype=float)
    before, after = float(np.nanmedian(v[:3])), float(np.nanmedian(v[-3:]))
    return {"metric": f"{pol}_dB", "before": before, "after": after, "delta": after - before}


def _part_mask(run, outline: dict) -> np.ndarray:
    """The run's grid pixels whose centre lies inside a lon/lat outline."""
    import shapely
    from rasterio import features
    from rasterio.transform import Affine
    from shapely.geometry import shape

    from .export import _transformer

    tr = _transformer(4326, run.epsg)
    geom = shapely.transform(shape(outline), lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1])))
    return features.rasterize([geom], out_shape=run.result.labels.shape, transform=Affine(*run.transform),
                              dtype="uint8") > 0


def _part_drop(run, part: np.ndarray, n_early: int, params: ChangeParams):
    """Index of the first pass after the baseline from which the part's mean cross-pol echo, relative to the window
    median of that pass (scene-wide wet or frozen shifts removed), stays at least threshold_db below its baseline
    for `persist` passes (all inside the record: one last odd pass is not a date); None if it never does."""
    from .change import CROSSPOL

    pol = next((p for p in run.stack if p.upper() in CROSSPOL), next(iter(run.stack)))
    arr = run.stack[pol]
    rel = []
    for k in range(len(run.dates)):
        img = np.asarray(arr[k], dtype=np.float64)
        ok = np.isfinite(img) & (img > 0)
        inside = ok & part
        if not inside.any():
            rel.append(np.nan)
            continue
        rel.append(10 * np.log10(img[inside].mean()) - np.median(10 * np.log10(img[ok])))
    rel = np.array(rel)
    dev = rel - np.nanmedian(rel[:n_early])
    down = dev <= -params.threshold_db
    persist = max(1, params.persist)
    for t in range(n_early, len(rel) - persist + 1):
        if down[t:t + persist].all():
            return t
    return None


def _primary_parts(dets: list, runs: list, n_early: dict, params: dict, site_list: list) -> list:
    """Inside the primary scope: one change per month of first optical detection (union of that month's optical
    regions), every radar source attached with the share of the part it flagged and its own date there (_part_drop).
    The change keeps the optical date: the radars' 150-300 m boxcars and spring snow date the block's edges early."""
    from shapely.ops import unary_union

    from . import merge
    from .distregions import to_geojson
    from .export import Merged

    optical = [d for d in dets if d.kind == "optical"]
    by_day: dict = {}
    for d in optical:
        by_day.setdefault(d.first_date, []).append(d)
    out = []
    for day, ds in sorted(by_day.items()):
        geom = unary_union([d.polygon for d in ds])
        total = merge.area_ha(geom)
        not_before = ds[0].not_before
        entries = [dict(sensor=OPTICAL, kind="optical", role="detected", first_date=day.isoformat(),
                        last_date=day.isoformat(), not_before=None if not_before is None else not_before.isoformat(),
                        confidence="medium", area_ha=round(total, 2), share=1.0,
                        note=f"An optical alert found vegetation loss here {merge._when(day, not_before)}.")]
        gj = to_geojson(geom)
        clauses, agree, best = [], False, None
        for s in site_list:
            i = next((k for k, r in enumerate(runs) if r.sensor == s.name), None)
            watching = s.start <= (not_before or day)  # watching over the whole window
            if s.kind != "radar" or (i is None and watching):
                continue
            short = SHORT.get(s.name, s.name)
            share = 0.0
            if i is not None:
                run = runs[i]
                part = _part_mask(run, gj)
                hit = part & (run.result.labels > 0)
                share = hit.sum() / max(part.sum(), 1)
            if share < ATTACH_MIN:
                note = f"{short} radar did not flag it." if watching else (
                    f"{s.name} was not flying yet." if s.name.startswith("NISAR") else f"{s.name} starts in {s.start.year}.")
                entries.append(dict(sensor=s.name, kind="radar", role="not_seen" if watching else "not_watching",
                                    first_date=None, last_date=None, not_before=None, confidence=None, area_ha=None,
                                    share=None, note=note))
                continue
            # the radar's own date for the part: its mean vegetation echo must drop by the detector's threshold
            t = _part_drop(run, part, n_early[run.sensor], params[run.sensor])
            if t is None:
                entries.append(dict(sensor=s.name, kind="radar", role="not_seen", first_date=None, last_date=None,
                                    not_before=None, confidence=None, area_ha=round(share * total, 2),
                                    share=round(float(share), 3),
                                    note=f"{short} radar flagged {share:.0%} of it, but its echo over the whole part "
                                         "did not drop enough to date it."))
                continue
            first = run.dates[t]
            labels, counts = np.unique(run.result.labels[hit], return_counts=True)
            grade = {r.label: r.confidence for r in run.result.regions}[int(labels[np.argmax(counts)])]
            if not_before is not None and first <= not_before:
                text = f"{short} radar saw its vegetation echo drop earlier, by {_say_day(first)}"
            elif first < day:
                text = f"{short} radar saw its vegetation echo drop by {_say_day(first)}"
            else:
                text = f"{short} radar confirmed it through clouds on {_say_day(first)}"
            clauses.append((first, text))
            agree |= share >= merge.SHARE_AGREES
            entries.append(dict(sensor=s.name, kind="radar", role="detected", first_date=first.isoformat(),
                                last_date=first.isoformat(), not_before=run.dates[t - 1].isoformat(), confidence=grade,
                                area_ha=round(share * total, 2), share=round(float(share), 3),
                                note=text[0].upper() + text[1:] + f" (it flagged {share:.0%} of the area)."))
            if best is None or share > best:
                best, run_i = share, i
        if best is None:
            run_i = next((i for i, r in enumerate(runs) if r.sensor == SENSOR_NAMES[S1]), 0)
        head = f"An optical alert found vegetation loss here {merge._when(day, not_before)}"
        explain = "; ".join([head] + [t for _, t in sorted(clauses, key=lambda c: c[0])]) + "."
        out.append(Merged(
            geometry=gj, type="clearing", first_date=day, last_date=day, not_before=not_before,
            confidence="high" if agree else "medium", sensor=OPTICAL, explain=explain, sources=entries, run=run_i,
            region=None, signal=_part_signal(runs[run_i], gj)))
    return out


def merged_changes(runs: list, site: Site, n_early: dict, optical=None, params: dict | None = None) -> tuple:
    """Every radar region and optical monthly region as a detection (sarwatch.merge), grouped into one change per
    place. Returns (list of export.Merged, optical state dates used as first dates)."""
    from shapely.geometry import box, shape

    from . import merge
    from .distregions import regions_by_month, to_geojson
    from .export import Merged, _outlines, _pass_before

    dets, owner = [], {}
    for i, run in enumerate(runs):
        outlines = _outlines(run)
        last_base = run.dates[n_early[run.sensor] - 1]
        for r in run.result.regions:
            late = r.first_date <= last_base  # already changing while the record began: a late start
            d = merge.Detection(source=run.sensor, kind="radar", polygon=shape(outlines[r.label]), type=r.type,
                                first_date=r.first_date, last_date=r.last_date, confidence=r.confidence,
                                not_before=None if late else _pass_before(run.dates, r.first_date), late_start=late)
            dets.append(d)
            owner[id(d)] = (i, r)
    used_states = set()
    if optical is not None:
        alerts, states = optical
        blind = _skip_spans(site, site.optical.blind)
        for reg in regions_by_month(alerts, states, min_ha=0.0):  # small ones count inside the primary scope only
            dets.append(merge.Detection(source=OPTICAL, kind="optical", polygon=shape(reg.polygon), type="clearing",
                                        first_date=reg.first_date, last_date=reg.first_date, confidence="medium",
                                        not_before=_last_look(states, reg.first_date, blind), area_ha=reg.area_ha))
    window = box(*site.bbox)  # a rotated radar grid reaches past the site window: changes outside it are left out
    dets = [d for d in dets if window.contains(d.polygon.centroid)]
    site_list = _site_sources(site)
    sites = {s.name: s for s in site_list}
    out = []
    if site.primary_scope and optical is not None:
        scope = shape(json.loads((REPO_ROOT / site.primary_scope).read_text(encoding="utf-8"))["geometry"])
        inside = [d for d in dets if d.polygon.intersection(scope).area >= PRIMARY_INSIDE * d.polygon.area]
        out = _primary_parts([d for d in inside if d.kind == "optical"], runs, n_early, params or {}, site_list)
        used_states.update(m.first_date for m in out)
        dets = [d for d in dets if not any(d is i for i in inside)]
    dets = [d for d in dets if d.kind != "optical" or d.area_ha >= site.optical.min_ha]
    for group in merge._groups(dets, sites):
        change = merge._build(group, dets, site_list, sites)
        radar = [d for d in group if id(d) in owner]
        best = None
        if radar:  # pictures, signal and series from the best radar detection: one that dated it, then confidence
            top = min(radar, key=lambda d: (d.late_start, -merge.GRADES.index(d.confidence), -d.polygon.area))
            best = (top, owner[id(top)][1])
            run_i = owner[id(top)][0]
        else:
            run_i = next((i for i, run in enumerate(runs) if run.sensor == SENSOR_NAMES[S1]), 0)
        if change.sensor == OPTICAL:
            used_states.add(change.first_date)
        out.append(Merged(
            geometry=to_geojson(change.geometry), type=change.type, first_date=change.first_date,
            last_date=change.last_date, not_before=change.not_before, confidence=change.confidence,
            sensor=change.sensor, explain=_sentence(group, change, best, sites), sources=change.sources, run=run_i,
            region=best[1] if best else None))
    return out, sorted(used_states)


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
        groups[-1] += [k for k in site if k != "snapshots" and not any(k in keys for keys in SITE_LINES)]
        lines = [", ".join(f"{json.dumps(k)}: {json.dumps(site[k], ensure_ascii=False)}" for k in g)
                 for g in groups if g]
        if "snapshots" in site:
            lines.append(_snapshots_text(site["snapshots"], nl))
        blocks.append("  {" + f",{nl}   ".join(lines) + "}")
    head = [k for k in index if k != "sites"]
    out = ["{"] + [f" {json.dumps(k)}: {json.dumps(index[k])}," for k in head] + [' "sites": [']
    return nl.join(out + [f",{nl}".join(blocks), " ]", "}"]) + nl


def snapshot_list(runs) -> list:
    """The timeline's stops: one {"date", "sensor"} per image date used, oldest first. A date two sensors share
    becomes one stop naming both."""
    by_date: dict = {}
    for run in runs:
        for day in run.dates:
            names = by_date.setdefault(str(day), [])
            if run.sensor not in names:
                names.append(run.sensor)
    return [{"date": d, "sensor": " + ".join(sorted(names))} for d, names in sorted(by_date.items())]


def _snapshots_text(snapshots: list, nl: str) -> str:
    rows = [", ".join(json.dumps(s, ensure_ascii=False) for s in snapshots[i:i + 3]) for i in range(0, len(snapshots), 3)]
    return '"snapshots": [' + nl + f",{nl}".join("    " + r for r in rows) + "]"


def update_sites_index(index_path, site_id: str, time_range: tuple, bbox=None, snapshots=None, sources=None) -> dict:
    """Set the site's ready = true, time_range, (if given) bbox, snapshots and sources; every other site and field
    stays as it was (text included)."""
    index_path = Path(index_path)
    _site_entry(index_path, site_id)
    text = index_path.read_bytes().decode("utf-8")
    index = json.loads(text)
    entry = next(s for s in index["sites"] if s.get("id") == site_id)
    entry["ready"] = True
    entry["time_range"] = [str(time_range[0]), str(time_range[1])]
    if bbox is not None:
        entry["bbox"] = [float(v) for v in bbox]
    if snapshots is not None:
        entry["snapshots"] = snapshots
    if sources is not None:
        entry["sources"] = sources
    new = None
    nl = "\r\n" if "\r\n" in text else "\n"
    m = re.search(r'\{\s*"id":\s*' + re.escape(json.dumps(site_id)), text)
    if m:  # edit the values in place (this site's first of each key), so the hand-written layout survives
        head, block = text[:m.start()], text[m.start():]
        block, n1 = re.subn(r'"ready":\s*(?:true|false)', '"ready": true', block, count=1)
        block, n2 = re.subn(r'"time_range":\s*\[[^\]]*\]', lambda _: '"time_range": ' + json.dumps(entry["time_range"]),
                            block, count=1)
        n3 = 1
        if bbox is not None:
            block, n3 = re.subn(r'"bbox":\s*\[[^\]]*\]', lambda _: '"bbox": ' + json.dumps(entry["bbox"]), block, count=1)
        n4 = 1
        if snapshots is not None:
            line = _snapshots_text(snapshots, nl)
            block, n4 = re.subn(r'"snapshots":\s*\[[^\]]*\]', lambda _: line, block, count=1)
            if not n4:  # first time: right after time_range
                block, n4 = re.subn(r'("time_range":\s*\[[^\]]*\])', lambda g: g.group(1) + "," + nl + "   " + line,
                                    block, count=1)
        n5 = 1
        if sources is not None:
            line = '"sources": ' + json.dumps(sources, ensure_ascii=False)
            block, n5 = re.subn(r'"sources":\s*\[\{.*?\}\]', lambda _: line, block, count=1, flags=re.S)
            if not n5:  # first time: right after time_range
                block, n5 = re.subn(r'("time_range":\s*\[[^\]]*\])', lambda g: g.group(1) + "," + nl + "   " + line,
                                    block, count=1)
        if n1 == n2 == n3 == n4 == n5 == 1:
            new = head + block
    if new is None or json.loads(new) != index:
        new = _format_sites(index, nl)
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
        max_new=None, threshold_db=None, min_area_ha=None, skip_dates=None, normalize=None, hold=None) -> int:
    """The whole site run; prints a summary. Returns 0 if the data passes the contract, 1 if not."""
    site = SITES[site_id]
    out, cache = Path(out), Path(cache)
    use = [s for s in sensors if (s == NISAR and site.nisar) or (s == S1 and site.s1 and site.use_s1)]
    if not use:
        raise PipelineError(f"{site_id}: no sensor left to run")
    entry = None if fetch_only else _site_entry(out / "sites.json", site_id)  # fail before spending data
    spans = _skip_spans(site, skip_dates)  # typos in the settings fail here too, not after the downloads
    params = {s: _params(site, s, threshold_db, min_area_ha, normalize=normalize, hold=hold) for s in use}
    token = None if offline else load_token()
    meter, days = Meter(), {}
    for sensor in use:
        left = None if max_new is None else max_new - meter.dates
        found = collect(sensor, site, cache, offline=offline, max_new=left, token=token, meter=meter)
        days[sensor] = _in_season(site, sensor, found)
        if len(found) >= 2 and len(days[sensor]) < 2:
            raise PipelineError(f"{site_id}: {sensor} months {site.s1.months} keep {len(days[sensor])} of "
                                f"{len(found)} dates; nothing to compare")
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

    for sensor in use:  # skip dates stay cached; they are only left out of detection
        left_out = [d for d in days[sensor] if any(lo <= d <= hi for lo, hi in spans)]
        if left_out:
            log.info("%s: left out %d date(s), %s (skip dates)", sensor, len(left_out),
                     ", ".join(map(str, left_out)))
            days[sensor] = [d for d in days[sensor] if d not in left_out]
    runs = [r for r in (detect(s, site, cache, days[s], params[s]) for s in use) if r]
    if not runs:
        raise PipelineError(f"{site_id}: no sensor has two cached dates, nothing to detect")
    from .export import write_site

    site_dir = out / site_id
    merged, optical_days, sources = None, [], None
    if site.sources:  # one change per place across the sources (kb/multi-sensor-design.md)
        optical = optical_alerts(site, offline) if site.optical else None
        n_early = {SENSOR_NAMES[s]: max(1, min(params[s].n_early, len(days[s]) - 1)) for s in use}
        merged, optical_days = merged_changes(runs, site, n_early, optical, {SENSOR_NAMES[s]: params[s] for s in use})
        sources = site_sources_json(site)
        log.info("merged: %d changes from %s", len(merged), ", ".join(SHORT.get(r.sensor, r.sensor) for r in runs)
                 + (" and the optical alerts" if optical else ""))
    written = write_site(site_dir, site_id, runs, merged=merged)
    (first, last), bbox = written["time_range"], written["bbox"]  # first to last pass used; around all changes
    stops = snapshot_list(runs)
    if optical_days:  # the optical states that date a change are stops too
        by_date = {s["date"]: s["sensor"] for s in stops}
        for d in map(str, optical_days):
            by_date[d] = OPTICAL if d not in by_date else " + ".join(sorted({*by_date[d].split(" + "), OPTICAL}))
        stops = [{"date": d, "sensor": by_date[d]} for d in sorted(by_date) if first <= d <= last]
    update_sites_index(out / "sites.json", site_id, (first, last), bbox, stops, sources)
    if ensure_story(site_dir, entry.get("name") or site_id):
        log.info("wrote a placeholder %s", site_dir / "story.json")
    problems = validate(out)

    by_type = _tally(site_dir, "type")
    total = sum(n for n, _ in by_type.values())
    kinds = ", ".join(f"{k} {n} = {ha:.1f} ha" for k, (n, ha) in by_type.items())
    lines = summary(_tally(site_dir, "sensor"))
    lines.append(f"  changes: {total}" + (f"  ({kinds})" if kinds else ""))
    lines.append(f"  sites.json: {site_id} ready, time_range {first} .. {last}, bbox {bbox}")
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
    p.add_argument("--threshold-db", type=float, help="change threshold in dB (default: the site's, else 3.0)")
    p.add_argument("--min-area-ha", type=float, help="smallest change kept, hectares (default: the site's, else 0.5)")
    p.add_argument("--skip-dates", metavar="D1,D2", help="comma-separated YYYY-MM-DD or YYYY-MM-DD..YYYY-MM-DD "
                   "passes to leave out of detection; replaces the site's own list ('' = use every date)")
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
                   min_area_ha=args.min_area_ha, normalize=args.normalize, hold=args.hold,
                   skip_dates=None if args.skip_dates is None else tuple(args.skip_dates.split(",")))
    except (PipelineError, PermissionError) as exc:  # PermissionError: the archive refused the token
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
