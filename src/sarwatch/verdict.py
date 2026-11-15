"""Verdict step: turn "what the public records say" into a label for every detected change.

Labels (contract enum): ``expected`` / ``review`` (shown as "needs review") / ``high_concern``.
The app flags places for a human to look at; it never accuses anyone, so no text here says "illegal".
Rules in plain words: ``kb/verdict-rules.md``. The pure part is ``judge``; the command line runs the lookups
and writes the result back into ``changes.geojson``:

    python -m sarwatch.verdict app/data/<site>/changes.geojson [--records records.json] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from .ndvi import same_season

SCOPE_MAIN_SHARE = 0.5  # a change counts as part of the record's outline when at least this much of it lies inside
BIG_HA = 5.0 # clearing / earthworks at least this big, on non-buildable land, with no record -> high concern
MID_HA = 2.0  # at least this big with no matching record -> needs review
NON_BUILDABLE_SHARE = 0.25  # share of the polygon on non-buildable land that makes the zoning count as non-buildable
PLANNED_SHARE = 0.5  # share on developable land needed to count as a planned development area
EDGE_SHARE = 0.10  # a protected-area overlap below this share (when the lookup says how big) only borders the area
SOLAR_MIN_SHARE = 0.5  # a listed solar plant matters only if it covers at least this share of the change's area
SOLAR_AUTHORISED = ("autoritzat", "en servei", "aprovat")  # plant statuses that count as a record
SOLAR_PENDING = ("en tramitaci",)  # "En tramitació": an application still being processed is not an authorisation
RECORD_TYPES = ("clearing", "earthworks", "structure")  # change types a solar-plant listing can explain
FIRE_TYPES = ("fire", "clearing", "other")  # change types a recorded wildfire can explain
KEYS = ("protected", "cadastre", "zoning", "solar", "fire", "official", "system", "surface", "ndvi")
SNOW_CAUTION = 0.25   # share of the change under snow or ice around its first date that makes snow a plausible cause
WATER_CAUTION = 0.25  # share of the change under water after it (median of the clear scenes) that is worth saying
SURFACE_SOURCE = "NASA HLS quality mask (Landsat and Sentinel-2)"
SURFACE_URL = "https://lpdaac.usgs.gov/products/hlss30v002/"
NDVI_SOURCE = "NASA HLS (Harmonized Landsat and Sentinel-2; Landsat by NASA/USGS, Sentinel-2 by ESA)"
NDVI_FELL = 0.15      # a drop in NDVI (median before minus median after) of at least this confirms vegetation loss
NDVI_FLAT = 0.05      # a drop below this (or a rise) means the photos show no vegetation loss; in between is "slightly"
NDVI_BARE = 0.2       # a before-median under this: little vegetation to lose, NDVI cannot show the change
NDVI_GREEN = 0.4      # before-value from which the ground counts as "was green" (a crop or field cycle is then plausible)
CONFIDENCE_STEPS = ("low", "medium", "high")
LATE_START_LEAD_YEARS = 3  # a late start may be this many years older than the sensor's first pass
SYSTEM_SHARE = 0.8  # a change counts as on port or airport land when at least this much of it lies on it (the rest of
                    # it would otherwise skip the zoning rules)

# record key -> name shown when that service could not be checked
LABELS = {
    "protected": "protected-areas map",
    "cadastre": "land registry",
    "zoning": "urban-planning map",
    "solar": "solar-plant list",
}


def _ok(record) -> bool:
    return isinstance(record, dict) and record.get("checked") is True


def _reason(code, text, effect, record=None, source=None, url=None):
    record = record if isinstance(record, dict) else {}
    return {
        "code": code,
        "text": text,
        "source": record.get("source") or source or "Public records",
        "url": record.get("url") or url,
        "effect": effect,
    }


def _first_sentence(text) -> str:
    """The radar track writes one sentence into `explain`; the verdict step appends to it. Keeping only the first
    sentence makes re-running idempotent (the sentence from the last run is dropped, then added again)."""
    if not isinstance(text, str):
        return ""
    match = re.match(r"(.+?[.!?])(\s|$)", text.strip(), flags=re.S)
    return match.group(1) if match else text.strip()


def _day(value) -> str:
    try:
        d = date.fromisoformat(value)
        return f"{d.day} {d.strftime('%b')} {d.year}"
    except (TypeError, ValueError):
        return str(value or "On record")


def _fire_text(fire: dict, explains: bool) -> str:
    """Names the fire (commune, date, hectares) so a reader can find it on the EFFIS map: the record's link is only the
    general viewer. A fire can be followed by salvage logging or building, so the text says "most likely"."""
    fires = fire.get("fires") or []
    top = fires[0] if fires and isinstance(fires[0], dict) else None
    where = ""
    if top:
        ha = top.get("area_ha")
        bits = [top.get("name"), top.get("date"), f"{ha:g} ha" if isinstance(ha, (int, float)) and ha else None]
        label = "EFFIS burnt areas" if str(fire.get("source", "")).startswith("EFFIS") else "records"
        where = f" ({label}: {', '.join(str(b) for b in bits if b)})"
    if explains:
        return f"A recorded wildfire burned here{where}, so this is most likely a burn scar and not new construction."
    return f"A recorded wildfire burned here{where}, but it does not explain a new building or ground movement."


SENSOR_NAMES = {"OPERA DIST-ALERT": "Optical alerts (NASA OPERA product, from Landsat by NASA/USGS and Sentinel-2 by ESA)"}  # Landsat is NASA/USGS, Sentinel-2 is ESA, the OPERA product is NASA's


def _detector(change: dict) -> str:
    """Who saw the change, for the source line of the size reasons: its own sensor in plain words, else a generic name."""
    sensor = str(change.get("sensor") or "").strip()
    return SENSOR_NAMES.get(sensor, sensor) or "Satellite detection"


def _area_name(area: dict) -> str:
    return area.get("name") or area.get("kind") or "a protected area"


def _is_late_start(change: dict) -> bool:
    """Already under way when the sensor began watching, and no source dated it: the date is the sensor's first pass,
    not the change's, so no rule may compare it with a record's date."""
    roles = [src.get("role") for src in change.get("sources") or [] if isinstance(src, dict)]
    return "late_start" in roles and "detected" not in roles


def _zoning(zon) -> tuple[str | None, bool, dict]:
    """(effective zone, is a planned development area). Mixed polygons use the shares the lookup returns: a
    substantial non-buildable part makes the whole change count as non-buildable. ``zone: None`` with ``checked``
    true means no zoning polygon there (e.g. the sea): unknown, not a failure."""
    if not _ok(zon):
        return None, False, {}
    shares = zon.get("shares") or {}
    zone = zon.get("zone")
    # "planned development area" is judged on its own share, before a non-buildable part overrides the zone: a place
    # that is 51 % developable and 49 % non-buildable is both (and the label stays "needs review": rule row 5)
    planned = shares.get("developable", 1.0 if zone == "developable" and not shares else 0.0) >= PLANNED_SHARE
    if shares.get("non_buildable", 0) >= NON_BUILDABLE_SHARE:
        zone = "non_buildable"
    return zone, planned, shares


def _zoning_text(shares: dict, key: str, whole: str, part: str) -> str:
    """``whole`` when (almost) all of the polygon is in that class (or the share is unknown), else "About 49 % of the
    place …": the card must not call a half-and-half place plain non-buildable."""
    share = shares.get(key)
    if share is None or share >= 0.9:
        return whole
    return f"About {round(100 * share)} % of the place {part}"


def _plant_ha(plant: dict) -> float | None:
    """Area of a listed plant: the part in this municipality if given, else the total; None if unknown or not a number
    (the list stores numbers as text; ``0`` is a value, not "missing")."""
    for key in ("ha_in_municipality", "ha"):
        try:
            value = float(plant[key])
        except (KeyError, TypeError, ValueError):
            continue
        if value == value:  # not NaN
            return value
    return None


def _solar(sol, area: float, ctype) -> tuple[list, list, list]:
    """(authorised plants that explain the change, pending applications of a matching size, every other listed
    plant). Only plants with a known area of at least half the change count; refused, withdrawn and unknown statuses
    fall in the last list."""
    if not _ok(sol) or ctype not in RECORD_TYPES:
        return [], [], []
    good, pending, other = [], [], []
    # A plant counts only when the list says WHERE it is (``located``: a map position). The Catalan list gives a
    # municipality and no position, so it cannot say that a plant has anything to do with this change: no reason at all.
    for plant in (p for p in sol.get("plants") or [] if p.get("located")):
        status = str(plant.get("status") or "").strip().lower()
        ha = _plant_ha(plant)
        fits = ha is not None and ha >= SOLAR_MIN_SHARE * area
        if fits and status.startswith(SOLAR_AUTHORISED):
            good.append(plant)
        elif fits and status.startswith(SOLAR_PENDING):
            pending.append(plant)
        else:
            other.append(plant)
    return good, pending, other


def _action_code(kind) -> str:
    return {"stop_order": "official_stop_order", "investigation": "official_investigation"}.get(kind, "official_action")


def judge(change: dict, records: dict) -> tuple[str, list[dict], str]:
    """Pure function: ``change`` = one feature's properties, ``records`` = lookup results by key
    (``protected``, ``cadastre``, ``zoning``, ``solar``, ``fire``, ``official``; each ``{source, url, checked, ...}`` as
    returned by ``sarwatch.context`` or a hand-entered records file). Returns ``(verdict, reasons, explain)`` with the
    reason that decides the label first. No network."""
    records = records or {}
    try:
        area = float(change["area_ha"])
    except (KeyError, TypeError, ValueError):
        area = float("nan")
    if not area > 0:  # also catches NaN
        raise ValueError(f"change {change.get('id')!r}: area_ha must be a positive number")
    ctype = change.get("type")
    prot, cad, zon, sol, fire, off, sysl, sfc, ndvi = (records.get(k) for k in KEYS)

    # ---- facts
    areas = list(prot.get("areas") or []) if _ok(prot) else []
    inside = _ok(prot) and bool(prot.get("inside"))
    core_areas = [a for a in areas if not str(a.get("kind", "")).endswith("buffer zone")]
    names = ", ".join(dict.fromkeys(_area_name(a) for a in (core_areas or areas)))[:200] or "a protected nature area"
    # only a buffer zone raises; a thin overlap (a share below EDGE_SHARE) just borders the area and stays neutral. A
    # buffer zone is not a protected area, so it never counts toward the share (``core_overlap_share``). An overlap
    # whose size is unknown (no outline from the service) counts as a real one: the safe side.
    buffer_only = inside and bool(areas) and not core_areas
    share = prot.get("core_overlap_share", prot.get("overlap_share")) if inside else None
    edge = inside and not buffer_only and share is not None and share < EDGE_SHARE
    real_inside = inside and not buffer_only and not edge
    zone, planned, zshares = _zoning(zon)
    # a late start was already under way when the sensor began watching: the record cannot date it, so the registry is
    # asked for buildings of any year (undated) instead of "built since the change"
    late_start = _is_late_start(change)
    built = int(cad.get("built_since") or 0) if _ok(cad) else 0  # dated buildings only: no year, no explanation
    system_kind = None
    if _ok(sysl) and ctype in RECORD_TYPES:
        shares = {k: v for k, v in (sysl.get("shares") or {}).items() if isinstance(v, (int, float))}
        best = max(shares, key=shares.get) if shares else None
        system_kind = best if best and shares[best] >= SYSTEM_SHARE else None
    system_land = system_kind is not None
    solar_good, solar_pending, solar_other = _solar(sol, area, ctype)
    matching = built > 0 or planned or bool(solar_good) or system_land
    fire_recorded = _ok(fire) and bool(fire.get("recorded"))
    fire_explains = fire_recorded and ctype in FIRE_TYPES
    assessment_missing = _ok(off) and bool(off.get("assessment_required")) and not off.get("assessment_completed")
    # a change inside the record's own outline is part of what the record is about: the size limits do not apply
    in_scope = assessment_missing and bool(off.get("in_scope"))
    big_enough = area >= BIG_HA or in_scope
    # no land registry for this country: a small ordinary clearing is not flagged by size alone
    small_forestry = (isinstance(cad, dict) and bool(cad.get("not_applicable")) and ctype == "clearing"
                      and area < BIG_HA and not _ok(off))  # an official record that applies here is never "no records"
    actions = [a for a in (off.get("actions") or []) if isinstance(a, dict)] if _ok(off) else []
    action_keys = [f"{_action_code(a.get('kind'))}:{i}" for i, a in enumerate(actions)]
    small_uncertain = area < MID_HA and change.get("confidence") == "low"
    change_year = str(change.get("first_date") or "")[:4]
    change_year = change_year if change_year.isdigit() else ""

    # ---- the verdict, and the code of the reason that decides it
    if fire_explains:
        verdict, decisive = "expected", "fire_recorded"
    elif real_inside:
        verdict, decisive = "high_concern", "protected_area"
    elif assessment_missing and big_enough and ctype in ("clearing", "earthworks"):
        verdict, decisive = "high_concern", "assessment_missing"
    elif zone == "non_buildable" and not small_uncertain and not system_land:  # port land is often classed non-buildable
        big = area >= BIG_HA and ctype in ("clearing", "earthworks") and not matching
        verdict, decisive = ("high_concern" if big else "review"), "zoning_non_buildable"
    elif assessment_missing and (area >= MID_HA or in_scope):
        verdict, decisive = "review", "assessment_missing"
    elif matching:
        verdict = "expected"
        decisive = ("cadastre_building_found" if built > 0 else "planned_sector" if planned
                    else "system_land" if system_land else "solar_plant_listed")  # the plant list is per municipality
    elif small_forestry and not solar_pending:
        verdict, decisive = "expected", "small_no_records"
    elif area >= MID_HA:
        verdict = "review"
        decisive = "solar_application_pending" if solar_pending else ("no_record_found" if _ok(cad) else "size_only")
    else:
        verdict, decisive = "expected", ("small_uncertain" if small_uncertain else "small_area")
    # something that should be looked at lifts an "expected" to "needs review" (a fire that explains the change
    # stays expected): the buffer zone of a protected area, an application still being processed, an official step
    if verdict == "expected" and not fire_explains:
        if buffer_only:
            verdict, decisive = "review", "protected_buffer"
        elif solar_pending and not matching:
            verdict, decisive = "review", "solar_application_pending"
        elif actions:
            verdict, decisive = "review", action_keys[0]

    # ---- every reason that applies, then the deciding one goes first
    facts: dict[str, dict] = {}
    if fire_recorded:
        facts["fire_recorded"] = _reason(
            "fire_recorded", _fire_text(fire, fire_explains),
            "lowers" if fire_explains else "neutral", fire, source="Wildfire records")
    if real_inside:
        facts["protected_area"] = _reason(
            "protected_area",
            f"The place lies inside a protected area ({names})." if not fire_explains
            else f"The place lies inside {names}; a recorded wildfire burned here.",
            "neutral" if fire_explains else "raises", prot)
    elif buffer_only:
        facts["protected_buffer"] = _reason(
            "protected_buffer", f"The place only touches the buffer zone of a protected area ({names}).",
            "neutral" if fire_explains else "raises", prot)
    elif edge:
        facts["protected_edge"] = _reason(
            "protected_edge", f"The place borders a protected area ({names}).", "neutral", prot)
    if assessment_missing:
        noun = {"clearing": "this clearing", "earthworks": "these earthworks"}.get(ctype, "this change")
        facts["assessment_missing"] = _reason(
            "assessment_missing",
            f"The required environmental assessment was not finished when {noun} happened."
            + (" This record covers the whole site, not only this spot." if off.get("site_wide") else ""),
            "raises", off, source="Official records")
    if zone == "non_buildable":
        facts["zoning_non_buildable"] = _reason(
            "zoning_non_buildable",
            _zoning_text(zshares, "non_buildable", "The land is zoned as non-buildable.",
                         "is zoned as non-buildable."), "raises", zon)
    elif zone == "urban":
        facts["zoning_urban"] = _reason("zoning_urban", "The land is zoned as urban.", "lowers", zon)
    if planned:
        facts["planned_sector"] = _reason(
            "planned_sector",
            _zoning_text(zshares, "developable", "The land is inside a planned development area.",
                         "is inside a planned development area."), "lowers", zon)
    if built > 0:
        facts["cadastre_building_found"] = _reason(
            "cadastre_building_found",
            f"{built} building(s) registered here date from {int(change_year) - LATE_START_LEAD_YEARS} or later (this "
            "change was already under way when the sensor began watching)." if late_start and change_year
            else f"{built} building(s) are registered here (this change was already under way when the sensor began "
            "watching)." if late_start
            else f"{built} building(s) registered here date from {change_year} or later, the year the change was first seen "
            "(the registry gives construction years only)." if change_year
            else f"{built} building(s) are registered here since the change.", "lowers", cad)
    if system_land:
        noun = "port" if system_kind == "port" else "airport"
        facts["system_land"] = _reason(
            "system_land",
            f"The land is {noun} system land in the urban plan (MUC), where works like this are part of its use.",
            "lowers", sysl)
    if solar_good and decisive != "system_land":  # the plant list is per municipality: port land already explains it
        ha = _plant_ha(solar_good[0])
        facts["solar_plant_listed"] = _reason(
            "solar_plant_listed",
            f"A solar plant of about {ha:g} ha is listed for this municipality (the list gives no exact location).",
            "lowers", sol)
    if solar_pending and not matching:
        facts["solar_application_pending"] = _reason(
            "solar_application_pending",
            "An application for a solar plant in this municipality (the list gives no exact location) is being "
            "processed; it is not authorised yet.", "raises", sol)
    if solar_other and not solar_good:
        facts["solar_plant_other"] = _reason(
            "solar_plant_other",
            "Solar plants are listed for this municipality, but none is authorised and about as large as this "
            "change, so none explains it.", "neutral", sol)
    if not matching and _ok(cad):
        facts["no_record_found"] = _reason(
            "no_record_found",
            ("No building registered here is from the years the change could have started in, and no planned development "
             "area matches it. The record cannot date this change."
             if late_start else
             "No building registered since the change (the land registry often records new buildings months late), "
             "no authorised solar plant and no planned development area match this change."),
            "raises", cad)
    detector = _detector(change)
    if decisive == "small_no_records":
        facts["small_no_records"] = _reason(
            "small_no_records",
            f"The change is small ({area:g} ha), too small to flag on its own. No land registry or zoning records are "
            "connected for this country yet, and no official record we have covers this spot.",
            "lowers", source=detector)
    if decisive == "size_only":
        no_records = (cad or {}).get("not_applicable")  # outside Spain the Catalan registry does not apply
        facts["size_only"] = _reason(
            "size_only",
            "No public land records are connected for this country yet, so a change of this size is flagged for review."
            if no_records
            else "The land registry could not be checked, so a change of this size is flagged for review.",
            "raises", source=detector)
    if verdict != "high_concern" and decisive != "small_no_records":  # that reason already says the change is small
        if small_uncertain:
            facts["small_uncertain"] = _reason(
                "small_uncertain", f"The change is too small ({area:g} ha) and too uncertain to flag on its own.",
                "lowers", source=detector)
        elif area < MID_HA:
            facts["small_area"] = _reason(
                "small_area", f"The change is small ({area:g} ha).", "lowers", source=detector)
    for key, action in zip(action_keys, actions):
        facts[key] = _reason(
            _action_code(action.get("kind")),
            f"{_day(action.get('date'))}: {action.get('text', 'An official step is on record.')}", "raises",
            action, source=(off or {}).get("source"), url=(off or {}).get("url"))
    unavailable = [
        _reason(
            "records_unavailable",
            f"The {LABELS[key]} could not be checked, so this part of the label rests on size alone.",
            "neutral",
            records.get(key),
            source=LABELS[key].capitalize(),
        )
        for key in LABELS
        if not _ok(records.get(key)) and not (records.get(key) or {}).get("not_applicable")
    ]
    # snow and water around the change (the series file's `surface` block): notes only, they never move the label
    if _ok(sfc):
        snow, water = sfc.get("snow_share"), sfc.get("water_share")
        snow = snow if isinstance(snow, (int, float)) else None
        water = water if isinstance(water, (int, float)) else None
        calm = []
        if snow is not None and snow >= SNOW_CAUTION:
            facts["snow_caution"] = _reason(
                "snow_caution",
                f"Snow or ice covered {round(100 * snow)} % of the area around the date it was first seen, so snow can "
                "explain this signal.", "neutral", sfc)
        elif snow is not None:
            calm.append("no snow")
        if water is not None and water >= WATER_CAUTION:
            facts["water_after"] = _reason(
                "water_after",
                f"{round(100 * water)} % of the area is under water after the change (possible flood or new water body).",
                "neutral", sfc)
        elif water is not None:
            calm.append("no standing water")
        if calm:
            facts["surface_clear"] = _reason(
                "surface_clear", f"Clear scenes around its dates show {' and '.join(calm)} over the area.", "neutral", sfc)
    # the vegetation index (the series file's `ndvi` block, NASA HLS): compared between photos from the same time of
    # year; a note, it never moves the label (the confidence is adjusted afterwards by ``ndvi_confidence``)
    cmp_ = ndvi_compare(ndvi)
    if cmp_ and cmp_["state"] == "few":
        facts["ndvi_few"] = _reason("ndvi_few", "Not enough comparable clear photos to compare the vegetation index.", "neutral", ndvi)
    elif cmp_ and cmp_["state"] == "ok":
        kind, before, after = cmp_["kind"], cmp_["before"], cmp_["after"]
        pair = f"{before:.2f} → {after:.2f}"
        head = "Between photos from the same time of year, the vegetation index (NDVI)"
        optical = _optical_saw(change)
        if kind == "fell":
            text = f"{head} fell from {before:.2f} to {after:.2f}, which fits vegetation loss."
        elif kind == "bare":
            what = "a clearing" if ctype == "clearing" else "this change"
            text = (f"There was little vegetation here before the change (NDVI {before:.2f} in photos from the same time "
                    f"of year), so the vegetation index cannot show {what}.")
        else:
            if kind == "flat":
                text = f"{head} did not fall ({pair})."
            else:
                text = f"{head} fell slightly ({pair}), not enough on its own to show vegetation loss."
            if optical:
                text += (" NDVI often stays high after a thinning, or when ground plants grow back in the first summer, "
                         "so this does not contradict the optical alert.")
            elif kind == "flat":
                text += " This does not confirm vegetation loss."
            if kind == "flat" and ctype in ("structure", "earthworks") and before >= NDVI_GREEN:
                text += " The ground was green before, so the radar signal may come from a crop or field cycle."
        facts[f"ndvi_{kind}"] = _reason(f"ndvi_{kind}", text, "neutral", ndvi)
    # a port / airport lookup that failed is reported; an absent one was simply not asked
    if isinstance(sysl, dict) and not _ok(sysl) and not sysl.get("not_applicable"):
        unavailable.append(_reason(
            "records_unavailable",
            "The port and airport land map could not be checked, so works there may be flagged.",
            "neutral", sysl, source="Port and airport land map"))
    # a fire lookup that failed is reported; an absent one was simply not asked
    if isinstance(fire, dict) and not _ok(fire) and not fire.get("not_applicable"):
        unavailable.append(_reason(
            "records_unavailable",
            "The wildfire map could not be checked, so a burn scar may be mistaken for a clearing.",
            "neutral", fire, source="Wildfire map"))
    reasons = [facts[decisive]] + [r for k, r in facts.items() if k != decisive] + unavailable
    return verdict, reasons, _explain(change, verdict, reasons)


def _explain(change: dict, verdict: str, reasons: list[dict]) -> str:
    """The radar sentence + the deciding reason + the next reason that points the same way (so the sentence never
    contradicts the label)."""
    direction = "lowers" if verdict == "expected" else "raises"
    texts = [reasons[0]["text"]]
    for r in reasons[1:]:
        if r["effect"] == direction and r["code"] not in ("small_area", "small_uncertain", "records_unavailable"):
            texts.append(r["text"])
            break
    base = _first_sentence(change.get("explain"))
    previous = [r.get("text") for r in change.get("reasons") or [] if isinstance(r, dict)]
    if base in previous:  # a change judged before that had no radar sentence: its explain is our own text, not radar
        base = ""
    return " ".join([base] + texts).strip()


# ---- hand-entered records (sites outside Catalonia, offline runs, tests) ----------------------------------------

def load_records_file(path) -> dict:
    """Format: ``{"version": 1, "default": {<key>: record}, "changes": {"<change id>": {<key>: record}}}``.
    A record has the same shape as a lookup result; ``checked`` defaults to true and ``source`` to
    "Hand-entered records". Per-change entries override ``default`` key by key. A record may carry a ``scope``
    (GeoJSON Polygon or MultiPolygon, EPSG:4326): it then applies only to changes that intersect it."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("version") != 1:
        raise ValueError(f"{path}: version must be 1")
    return doc


def _in_scope(geometry: dict, scope: dict) -> bool:
    try:
        from shapely.geometry import shape
    except ImportError as exc:  # pragma: no cover - shapely is in the "verdict" extra
        raise SystemExit("records with a 'scope' need shapely: pip install -e '.[verdict]'") from exc
    if not isinstance(scope, dict) or scope.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError("a record's scope must be a GeoJSON Polygon or MultiPolygon")
    try:
        g, s = shape(geometry), shape(scope)
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise ValueError(f"a record's scope is not a valid GeoJSON polygon: {exc}") from exc
    return g.intersects(s) and not g.touches(s)  # sharing only a border is outside


def _scope_share(geometry: dict, scope: dict) -> float:
    """Share of the change's area that lies inside the scope (0 to 1; ratio of areas in degrees, fine for a ratio)."""
    from shapely.geometry import shape
    from shapely.validation import make_valid

    g, s = make_valid(shape(geometry)), make_valid(shape(scope))
    if g.area == 0:  # a point or a line: inside or not
        return 1.0 if g.intersects(s) else 0.0
    return g.intersection(s).area / g.area


def records_for(doc: dict, change_id: str, geometry: dict | None = None) -> dict:
    """The hand-entered records that apply to one change (``default`` overridden by the change's own entries; a
    record whose ``scope`` does not reach ``geometry`` is left out). A record from ``default`` without a ``scope``
    gets ``site_wide: true``, so the reason can say it covers the whole site."""
    default, own = doc.get("default", {}), doc.get("changes", {}).get(change_id, {})
    out = {}
    for key in {**default, **own}:
        rec = own[key] if key in own else default[key]
        scope = rec.get("scope")
        if scope and geometry is not None and not _in_scope(geometry, scope):
            continue
        site_wide = key not in own and not scope
        out[key] = {"checked": True, "source": "Hand-entered records", "url": None,
                    **({"site_wide": True} if site_wide else {}),
                    # "part of the same clearing" only if most of the change lies inside the outline
                    **({"in_scope": True} if scope and geometry is not None
                       and _scope_share(geometry, scope) >= SCOPE_MAIN_SHARE else {}),
                    **{k: v for k, v in rec.items() if k != "scope"}}
    return out


# ---- network lookups (sarwatch.context) --------------------------------------------------------------------------

def run_lookups(geometry: dict, change: dict) -> dict:
    from sarwatch.context import lookup_all  # needs the "verdict" extra (requests, shapely, pyproj)

    try:
        # the cadastre asks "built since the change"; the wildfire map asks "a fire by then, at most a year before"
        since = change["first_date"]
        if _is_late_start(change) and since[:4].isdigit():
            since = f"{int(since[:4]) - LATE_START_LEAD_YEARS}-01-01"  # under way before the sensor began: some years of lead
        return lookup_all(geometry, since=since, until=change["first_date"])
    except Exception as exc:  # lookups should never raise; if they do, record it instead of crashing the run
        return {k: {"source": v.capitalize(), "url": None, "checked": False, "error": str(exc)} for k, v in LABELS.items()}


def _site_country(path: Path):
    sites = path.parent.parent / "sites.json"
    try:
        for site in json.loads(sites.read_text(encoding="utf-8"))["sites"]:
            if site["id"] == path.parent.name:
                return site.get("country")
    except (OSError, ValueError, KeyError):
        pass
    return None


def _series_block(site_dir: Path, props: dict, key: str) -> dict | None:
    rel = (props.get("evidence") or {}).get("series") or f"series/{props.get('id')}.json"
    try:
        block = json.loads((Path(site_dir) / rel).read_text(encoding="utf-8")).get(key)
    except (OSError, ValueError):
        return None
    return block if isinstance(block, dict) else None


def surface_record(site_dir: Path, props: dict) -> dict | None:
    """The change's ``surface`` block (snow and water shares from the NASA HLS quality mask, written next to its
    series) as a record, or None when the change has no series file or no such block."""
    block = _series_block(site_dir, props, "surface")
    return {"source": SURFACE_SOURCE, "url": SURFACE_URL, **block, "checked": True} if block else None


def ndvi_record(site_dir: Path, props: dict) -> dict | None:
    """The change's ``ndvi`` block (the clear HLS dates and their mean NDVI) as a record, with the change's first and
    last date so the verdict can compare photos from the same time of year; None when the change has no series file
    or no such block."""
    block = _series_block(site_dir, props, "ndvi")
    if not block:
        return None
    return {"source": NDVI_SOURCE, "url": SURFACE_URL, "dates": block.get("dates"), "values": block.get("values"),
            "first_date": props.get("first_date"), "last_date": props.get("last_date"), "checked": True}


def ndvi_compare(ndvi) -> dict | None:
    """Compare NDVI between photos from the same time of year, with ``ndvi.same_season`` (the same function writes the
    card's ``before`` / ``after``). From an ``ndvi`` record (``dates``, ``values``, ``first_date``, ``last_date``).
    Returns None without a usable series, ``{"state": "nodata"}`` when a side has no date at all, ``{"state": "few"}``
    when a side keeps fewer than two dates, else ``{"state": "ok", "kind": fell | slightly | flat | bare,
    "before", "after" (medians), "n_before", "n_after"}``. ``bare``: the before median is under ``NDVI_BARE``."""
    if not _ok(ndvi):
        return None
    try:
        first, last = date.fromisoformat(str(ndvi["first_date"])[:10]), date.fromisoformat(str(ndvi["last_date"])[:10])
        r = same_season(ndvi["dates"], ndvi["values"], first, last)
    except (KeyError, TypeError, ValueError):
        return None
    if r["state"] != "ok":
        return {"state": r["state"]}
    mb, ma = r["before"], r["after"]
    drop = round(mb - ma, 4)  # 0.60 - 0.45 must count as 0.15, not 0.1499999
    kind = "bare" if mb < NDVI_BARE else "fell" if drop >= NDVI_FELL else "flat" if drop < NDVI_FLAT else "slightly"
    return {"state": "ok", "kind": kind, "before": mb, "after": ma, "n_before": r["n_before"], "n_after": r["n_after"]}


def _optical_saw(change: dict) -> bool:
    """Did an optical source (an alert computed from the same HLS photos) detect this change?"""
    return any(s.get("kind") == "optical" and s.get("role") in ("detected", "late_start") for s in change.get("sources") or [])


def ndvi_confidence(change: dict, ndvi) -> tuple[str, str | None]:
    """The confidence after the NDVI check and the sentence that says why (None when it did not move). Only a
    clearing seen by radar alone moves, one step: up when the vegetation index fell and exactly one radar sensor saw
    it (a second, independent kind of satellite agrees; two radars already got their step from the exporter), down
    when the ground was bare before (nothing green to clear). Never lowered when an optical source saw the change:
    NDVI and the optical alert come from the same photos, so NDVI is no independent check.
    ``change["confidence"]`` must be the one from the exporter, not an adjusted one."""
    conf = change.get("confidence")
    cmp_ = ndvi_compare(ndvi)
    if conf not in CONFIDENCE_STEPS or not cmp_ or cmp_["state"] != "ok" or change.get("type") != "clearing":
        return conf, None
    if _optical_saw(change):
        return conf, None
    i = CONFIDENCE_STEPS.index(conf)
    saw = [s for s in change.get("sources") or [] if s.get("role") in ("detected", "late_start")]
    if cmp_["kind"] == "bare" and i > 0:
        return CONFIDENCE_STEPS[i - 1], "the ground had little vegetation before (NDVI under 0.2), so the vegetation index cannot confirm a clearing"
    if cmp_["kind"] == "fell" and i < 2 and len(saw) == 1 and saw[0].get("kind") == "radar":
        return CONFIDENCE_STEPS[i + 1], "photos from the same time of year show the vegetation index falling"
    return conf, None


def apply_file(
    path, records_path=None, dry_run=False, lookup=run_lookups, allow_unchecked=False
) -> tuple[Counter, Counter, Counter]:
    """Judge every change in ``path`` and write verdict/reasons/explain back. Returns (labels before, labels after,
    lookups that failed by service). Records come from ``records_path`` (or ``<site>/records.json`` if it exists, or
    when the site is outside Spain: no Catalan lookups there); otherwise from the live lookups. If every live lookup
    failed (offline?) nothing is written unless ``allow_unchecked``: the labels would rest on size alone."""
    path = Path(path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    if records_path is None and (path.parent / "records.json").is_file():
        records_path = path.parent / "records.json"
    hand = load_records_file(records_path) if records_path else None
    abroad = _site_country(path) not in (None, "ES")
    offline = hand is not None or abroad
    # the Catalan services do not apply outside Spain: say "not applicable" instead of "could not be checked"
    not_applicable = {k: {"checked": False, "not_applicable": True} for k in LABELS} if abroad else {}
    before, after, failed = Counter(), Counter(), Counter()
    asked = 0
    for feature in doc["features"]:
        props = feature["properties"]
        before[props.get("verdict") or "unjudged"] += 1
        if hand is not None:
            records = {**not_applicable, **records_for(hand, props["id"], feature["geometry"])}
        elif offline:
            records = dict(not_applicable)
        else:
            records = lookup(feature["geometry"], props)
            for key, rec in records.items():
                asked += 1
                if not _ok(rec):
                    failed[key] += 1
        surface = surface_record(path.parent, props)  # read after the lookups were counted: it is not a service
        if surface:
            records["surface"] = surface
        ndvi = ndvi_record(path.parent, props)
        if ndvi:
            records["ndvi"] = ndvi
        if "confidence_base" in props:  # undo an earlier run's NDVI step: the label rules see the exporter's confidence
            props["confidence"] = props.pop("confidence_base")
            props.pop("confidence_ndvi", None)
        props["verdict"], props["reasons"], props["explain"] = judge(props, records)
        conf, why = ndvi_confidence(props, ndvi)
        if why and conf != props.get("confidence"):
            props["confidence_base"], props["confidence"], props["confidence_ndvi"] = props["confidence"], conf, why
        after[props["verdict"]] += 1
    if asked and sum(failed.values()) == asked and not allow_unchecked:
        raise SystemExit(
            f"All {asked} lookups failed (offline?), so every label would rest on size alone. Nothing written. "
            "Re-run online, or pass --allow-unchecked to write them anyway."
        )
    if not dry_run:
        path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        _refresh_stages(path.parent / "stages.geojson", doc)
    return before, after, failed


def _refresh_stages(path: Path, changes: dict) -> None:
    """Give every stage of a growing outline (stages.geojson, if the site has one) the strongest verdict of its members."""
    if not path.is_file():
        return
    rank = {None: 0, "expected": 1, "review": 2, "high_concern": 3}
    verdicts = {f["properties"]["id"]: f["properties"].get("verdict") for f in changes["features"]}
    stages = json.loads(path.read_text(encoding="utf-8"))
    for stage in stages["features"]:
        stage["properties"]["verdict"] = max((verdicts.get(i) for i in stage["properties"]["members"]), key=rank.get)
    path.write_text(json.dumps(stages, separators=(",", ":")) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Label every change in a changes.geojson (see kb/verdict-rules.md).")
    parser.add_argument("changes", help="app/data/<site>/changes.geojson")
    parser.add_argument("--records", help="hand-entered records file (skips the live lookups)")
    parser.add_argument("--dry-run", action="store_true", help="print the label counts, write nothing")
    parser.add_argument("--allow-unchecked", action="store_true", help="write labels even if every lookup failed")
    parser.add_argument("--offline", action="store_true",
                        help="answer the lookups from the on-disk cache only (a miss counts as a failed lookup)")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.offline:
        from sarwatch.context import _common

        _common.OFFLINE = True
    before, after, failed = apply_file(args.changes, args.records, args.dry_run, allow_unchecked=args.allow_unchecked)
    fmt = lambda c: ", ".join(f"{k} {v}" for k, v in sorted(c.items())) or "none"  # noqa: E731
    print(f"labels before: {fmt(before)}\nlabels after:  {fmt(after)}" + ("  (dry run, nothing written)" if args.dry_run else ""))
    if failed:
        print(f"WARNING lookups that failed (those parts rest on size alone): {fmt(failed)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
