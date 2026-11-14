"""One change, several sensors: merge detections from different sources into one change per place.

Pure function, no files, no network. Implements sections 1-4 and 6 of `kb/multi-sensor-design.md`:
detections from different sources are the same change when they overlap (mutual 30 %) and their time
windows meet; changes are connected groups. Each change gets a union outline, the type of its most
confident detection, honest dates (`first_date` = first positive sighting of one source, `not_before`
from that same source), a confidence adjusted for independent agreement and risky seasons, and a
`sources` list saying who saw it, who did not, and who was not yet watching.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .export import GEOD, _span

MIN_OVERLAP = 0.30        # intersection must cover this share of EACH polygon (mutual overlap)
TIME_SLACK_DAYS = 24      # each window is widened by this at both ends (two radar revisits)
LATE_START_DAYS = 120     # a late start may sit this long after the real start
SHARE_AGREES = 0.30       # a nested detection covering at least this share of a change counts as agreeing

GRADES = ("low", "medium", "high")
TYPE_RANK = {"structure": 0, "earthworks": 1, "clearing": 2, "other": 3}  # tie-break, lower wins
KIND_WORD = {"optical": "optical alert", "radar": "radar"}


@dataclass(frozen=True)
class Detection:
    """One region from one source. `first_date` is the day the source first showed the new state (not_after)."""
    source: str
    kind: str                       # "optical" | "radar"
    polygon: BaseGeometry           # lon/lat
    type: str                       # "clearing" | "structure" | "earthworks" | "other"
    first_date: date
    last_date: date
    confidence: str                 # "low" | "medium" | "high"
    not_before: date | None = None
    late_start: bool = False
    area_ha: float | None = None    # own area; computed (geodesic) when None


@dataclass(frozen=True)
class SiteSource:
    """A source's record over the site."""
    name: str
    kind: str
    start: date
    end: date | None = None
    revisit_days: int | None = None
    sees: frozenset = frozenset()   # change types it can detect; empty = all
    risky_months: frozenset = frozenset()


@dataclass
class MergedChange:
    geometry: BaseGeometry
    area_ha: float
    type: str
    first_date: date
    not_before: date | None
    last_date: date
    confidence: str
    sensor: str                     # the source that set first_date
    when: str                       # "between 2 and 20 May 2026" | "on or before ..." | "already under way ..."
    confidence_note: str            # the "card adds" sentence of design section 3
    sources: list = field(default_factory=list)   # dicts in the shape of design section 6
    late_start_only: bool = False


# ---------------------------------------------------------------- geometry

def area_ha(geom: BaseGeometry) -> float:
    """Geodesic area in hectares (WGS84), as the exporter computes it."""
    if geom.is_empty:
        return 0.0
    return abs(GEOD.geometry_area_perimeter(geom)[0]) / 1e4


def _clean(poly) -> BaseGeometry:
    if isinstance(poly, dict):
        poly = shape(poly)
    return poly if poly.is_valid else poly.buffer(0)


def _overlap_ok(a: BaseGeometry, b: BaseGeometry) -> bool:
    """Space test: the intersection covers >= MIN_OVERLAP of each polygon (ratios in lon/lat degrees: local, so fine)."""
    if a.is_empty or b.is_empty or a.area == 0 or b.area == 0:
        return False
    inter = a.intersection(b).area
    return inter / a.area >= MIN_OVERLAP and inter / b.area >= MIN_OVERLAP


# ---------------------------------------------------------------- time

def _window(d: Detection, sites: dict) -> tuple:
    """(lo, hi) before widening. Unknown not_before: 24 days before first_date; late start: 120 days before
    the record began (the source's `start`, else the detection's own first_date)."""
    if d.late_start:
        site = sites.get(d.source)
        began = site.start if site else d.first_date
        return began - timedelta(days=LATE_START_DAYS), d.last_date
    if d.not_before is not None:
        return d.not_before, d.last_date
    return d.first_date - timedelta(days=TIME_SLACK_DAYS), d.last_date


def _windows_meet(w1: tuple, w2: tuple) -> bool:
    slack = timedelta(days=TIME_SLACK_DAYS)
    return w1[0] - slack <= w2[1] + slack and w2[0] - slack <= w1[1] + slack


def same_change(a: Detection, b: Detection, sites: dict | None = None) -> bool:
    """Pairwise test: different sources, mutual 30 % overlap, windows (widened by 24 days) meet. Type is not tested."""
    sites = sites or {}
    if a.source == b.source:
        return False
    return _overlap_ok(_clean(a.polygon), _clean(b.polygon)) and _windows_meet(_window(a, sites), _window(b, sites))


def _groups(dets: list, sites: dict) -> list:
    parent = list(range(len(dets)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(dets)):
        for j in range(i + 1, len(dets)):
            if same_change(dets[i], dets[j], sites):
                parent[find(i)] = find(j)
    out = {}
    for i in range(len(dets)):
        out.setdefault(find(i), []).append(dets[i])
    return list(out.values())


# ---------------------------------------------------------------- wording

def _day(d: date) -> str:
    return _span(d, d, "")


def _when(first: date, not_before: date | None) -> str:
    if not_before is None:
        return f"on or before {_day(first)}"
    if not_before >= first:
        return f"on {_day(first)}"
    return f"between {_span(not_before, first, ' and ')}"


def _step(grade: str, delta: int) -> str:
    return GRADES[max(0, min(2, GRADES.index(grade) + delta))]


def _best_grade(ds: list) -> str:
    return max((d.confidence for d in ds), key=GRADES.index)


def _entry(name: str, kind: str, role: str, ds: list, nb: date | None, own: float, share: float, note: str) -> dict:
    d0 = min(ds, key=lambda d: d.first_date)
    return dict(sensor=name, kind=kind, role=role, first_date=d0.first_date.isoformat(),
                last_date=max(d.last_date for d in ds).isoformat(), not_before=nb.isoformat() if nb else None,
                confidence=_best_grade(ds), area_ha=round(own, 2), share=round(share, 3), note=note)


# ---------------------------------------------------------------- one group -> one change

def _build(group: list, all_dets: list, site_list: list, sites: dict) -> MergedChange:
    outline = unary_union([_clean(d.polygon) for d in group])
    total = area_ha(outline)
    by_source: dict = {}
    for d in group:
        by_source.setdefault(d.source, []).append(d)

    # type: most confident detection; ties by structure > earthworks > clearing > other
    best = min(group, key=lambda d: (-GRADES.index(d.confidence), TYPE_RANK.get(d.type, 3)))

    # dating: first positive sighting by a source that is NOT a late start
    proper = [d for d in group if not d.late_start]
    last = max(d.last_date for d in group)
    if proper:
        # tie on first_date: the widest window (unknown / earliest not_before) is the conservative one
        setter = min(proper, key=lambda d: (d.first_date, date.min if d.not_before is None else d.not_before))
        first, not_before = setter.first_date, setter.not_before
        when = _when(first, not_before)
    else:
        setter = min(group, key=lambda d: d.first_date)
        site = sites.get(setter.source)
        # a late start: the record cannot date it, so the date shown is the sensor's first pass (never a later
        # date inside the baseline, which would contradict "already under way when it began watching")
        began = site.start if site else setter.first_date
        first, not_before = began, None
        when = f"already under way on {_day(began)}, when {setter.source} began watching; the start date is not known"

    # nested detections: other sources overlapping the outline without merging; cite them with their share
    cited: dict = {}
    if total > 0:
        lo = min(_window(d, sites)[0] for d in group)
        for d in all_dets:
            if d.source in by_source:
                continue
            if _windows_meet((lo, last), _window(d, sites)) and _clean(d.polygon).intersects(outline):
                cited.setdefault(d.source, []).append(d)
    nested = {}
    for name, ds in cited.items():
        u = unary_union([_clean(d.polygon) for d in ds])
        nested[name] = (ds, u, area_ha(u.intersection(outline)) / total)

    # ---- confidence: best own grade, then agreement / risky season
    agreeing = set(by_source)
    kinds = {d.kind for d in group}
    for name, (ds, _u, share) in nested.items():
        if share >= SHARE_AGREES:
            agreeing.add(name)
            kinds.add(ds[0].kind)
    grade = _best_grade(group)
    if len(kinds) == 2:
        grade, note = _step(grade, +1), "Two independent kinds of satellite saw it"
    elif any(sites[n].risky_months and first.month in sites[n].risky_months for n in agreeing if n in sites):
        grade = _step(grade, -1)
        note = ("Seen only by radar while the ground was probably frozen or snow-covered, which can look like a change"
                if "radar" in kinds else
                "Seen only by optical alerts in months when low sun or snow can look like a change")
    elif len(agreeing) >= 2:
        grade = _step(grade, +1)
        note = "Both radar satellites saw it" if kinds == {"radar"} else "Both optical sources saw it"
    else:
        note = ""

    # ---- sources list
    entries = []
    for name in sorted(by_source, key=lambda n: min(d.first_date for d in by_source[n])):
        ds = by_source[name]
        kind = ds[0].kind
        u = unary_union([_clean(d.polygon) for d in ds])
        own = ds[0].area_ha if len(ds) == 1 and ds[0].area_ha is not None else area_ha(u)
        share = area_ha(u.intersection(outline)) / total if total else 0.0
        d0 = min(ds, key=lambda d: d.first_date)
        late = all(d.late_start for d in ds)
        nb = None if d0.late_start else d0.not_before
        if late:
            began = sites[name].start if name in sites else d0.first_date
            sent = f"{name} began watching on {_day(began)} and shows the change already under way."
        elif name == setter.source:
            sent = (f"An optical alert found vegetation loss here {_when(d0.first_date, nb)}." if kind == "optical"
                    else f"{name} radar saw the ground change {_when(d0.first_date, nb)}.")
        elif kind == "optical":
            sent = f"An optical alert also found vegetation loss here on {_day(d0.first_date)}."
        else:
            through = ", through clouds," if setter.kind == "optical" else ""
            sent = f"{name} radar saw the same change{through} on {_day(d0.first_date)}."
        entries.append(_entry(name, kind, "late_start" if late else "detected", ds, nb, own, share, sent))
    for name, (ds, u, share) in nested.items():
        d0 = min(ds, key=lambda d: d.first_date)
        sent = (f"This change lies inside a larger {KIND_WORD[d0.kind]} area ({name})." if area_ha(u) > total
                else f"{name} saw {share:.0%} of it.")
        nb = None if d0.late_start else d0.not_before
        entries.append(_entry(name, d0.kind, "late_start" if d0.late_start else "detected", ds, nb,
                              area_ha(u), share, sent))

    window_lo = not_before or first
    for s in site_list:
        if s.name in by_source or s.name in nested:
            continue
        if s.start > last or (s.end is not None and s.end < window_lo):
            if s.end is not None and s.end < window_lo:
                sent = f"{s.name} stopped in {s.end.year}."
            elif s.kind == "optical":
                sent = f"Optical alerts start in {s.start.year}."
            elif s.name.startswith("NISAR"):
                sent = f"{s.name} was not flying yet."
            else:
                sent = f"{s.name} starts in {s.start.year}."
            role = "not_watching"
        else:
            sent = f"The optical alerts did not flag it." if s.kind == "optical" else f"{s.name} did not flag it."
            if s.sees and best.type not in s.sees:
                sent = sent[:-1] + f"; they only see {', '.join(sorted(s.sees))}."
            role = "not_seen"
        entries.append(dict(sensor=s.name, kind=s.kind, role=role, first_date=None, last_date=None,
                            not_before=None, confidence=None, area_ha=None, share=None, note=sent))

    if not note:  # one source, normal season
        only = setter.source
        others = [e for e in entries if e["sensor"] != only]
        label = f"{only} radar" if setter.kind == "radar" else only
        if others and all(e["role"] == "not_watching" for e in others):
            note = f"Only {label} was watching in {first.year}"
        else:
            note = f"Only {label} saw it"

    return MergedChange(
        geometry=outline, area_ha=total, type=best.type, first_date=first, not_before=not_before, last_date=last,
        confidence=grade, sensor=setter.source, when=when, confidence_note=note, sources=entries,
        late_start_only=not proper)


def merge_detections(detections: list, site_sources: list) -> list:
    """Detections from several sources in, one MergedChange per place out (ordered by first_date)."""
    sites = {s.name: s for s in site_sources}
    dets = list(detections)
    changes = [_build(g, dets, list(site_sources), sites) for g in _groups(dets, sites)]
    return sorted(changes, key=lambda c: (c.first_date, c.sensor))
