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
from datetime import date
from pathlib import Path

BIG_HA = 5.0  # clearing / earthworks at least this big, on non-buildable land, with no record -> high concern
MID_HA = 2.0  # at least this big with no matching record -> needs review
NON_BUILDABLE_SHARE = 0.25  # share of the polygon on non-buildable land that makes the zoning count as non-buildable
PLANNED_SHARE = 0.5  # share on developable land needed to count as a planned development area
EDGE_SHARE = 0.01  # a protected-area overlap smaller than this share (when the lookup says how big) is an edge touch
SOLAR_MIN_SHARE = 0.5  # a listed solar plant explains a change only if it covers at least this share of its area
SOLAR_NOT_COUNTED = ("no autoritzat", "desistit")  # plant statuses that do not count as a record
RECORD_TYPES = ("clearing", "earthworks", "structure")  # change types a solar-plant listing can explain
FIRE_TYPES = ("fire", "clearing", "other")  # change types a recorded wildfire can explain
KEYS = ("protected", "cadastre", "zoning", "solar", "fire", "official")

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


def _area_name(area: dict) -> str:
    return area.get("name") or area.get("kind") or "a protected area"


def _zoning(zon) -> tuple[str | None, bool]:
    """(effective zone, is a planned development area). Mixed polygons use the shares the lookup returns: a
    substantial non-buildable part makes the whole change count as non-buildable. ``zone: None`` with ``checked``
    true means no zoning polygon there (e.g. the sea): unknown, not a failure."""
    if not _ok(zon):
        return None, False
    shares = zon.get("shares") or {}
    zone = zon.get("zone")
    if shares.get("non_buildable", 0) >= NON_BUILDABLE_SHARE:
        zone = "non_buildable"
    planned = zone == "developable" and shares.get("developable", 1.0) >= PLANNED_SHARE
    return zone, planned


def _solar(sol, area: float, ctype) -> tuple[list, list]:
    """(plants that explain the change, plants listed but not matching): authorised and at least half as large."""
    if not _ok(sol) or ctype not in RECORD_TYPES:
        return [], []
    good, other = [], []
    for plant in sol.get("plants") or []:
        status = str(plant.get("status") or "").strip().lower()
        ha = plant.get("ha_in_municipality")
        ha = plant.get("ha") if ha is None else ha
        refused = status.startswith(SOLAR_NOT_COUNTED)
        (other if refused or ha is None or ha < SOLAR_MIN_SHARE * area else good).append(plant)
    return good, other


def judge(change: dict, records: dict) -> tuple[str, list[dict], str]:
    """Pure function: ``change`` = one feature's properties, ``records`` = lookup results by key
    (``protected``, ``cadastre``, ``zoning``, ``solar``, ``fire``, ``official``; each ``{source, url, checked, ...}`` as
    returned by ``sarwatch.context`` or a hand-entered records file). Returns ``(verdict, reasons, explain)`` with the
    reason that decides the label first. No network."""
    records = records or {}
    area = float(change["area_ha"])
    ctype = change.get("type")
    prot, cad, zon, sol, fire, off = (records.get(k) for k in KEYS)

    # ---- facts
    areas = list(prot.get("areas") or []) if _ok(prot) else []
    inside = _ok(prot) and bool(prot.get("inside"))
    names = ", ".join(_area_name(a) for a in areas[:2]) or "a protected nature area"
    soft = inside and (
        (bool(areas) and all(str(a.get("kind", "")).endswith("buffer zone") for a in areas))
        or (prot.get("overlap_share") is not None and prot["overlap_share"] < EDGE_SHARE)
    )
    zone, planned = _zoning(zon)
    built = int(cad.get("built_since") or 0) if _ok(cad) else 0
    solar_good, solar_other = _solar(sol, area, ctype)
    matching = built > 0 or planned or bool(solar_good)
    fire_recorded = _ok(fire) and bool(fire.get("recorded"))
    fire_explains = fire_recorded and ctype in FIRE_TYPES
    assessment_missing = _ok(off) and bool(off.get("assessment_required")) and not off.get("assessment_completed")
    actions = list(off.get("actions") or []) if _ok(off) else []

    # ---- the verdict, and the code of the reason that decides it
    if fire_explains:
        verdict, decisive = "expected", "fire_recorded"
    elif inside and not soft:
        verdict, decisive = "high_concern", "protected_area"
    elif assessment_missing and area >= BIG_HA and ctype in ("clearing", "earthworks"):
        verdict, decisive = "high_concern", "assessment_missing"
    elif zone == "non_buildable":
        big = area >= BIG_HA and ctype in ("clearing", "earthworks") and not matching
        verdict, decisive = ("high_concern" if big else "review"), "zoning_non_buildable"
    elif assessment_missing and area >= MID_HA:
        verdict, decisive = "review", "assessment_missing"
    elif matching:
        verdict = "expected"
        decisive = "cadastre_building_found" if built > 0 else "planned_sector" if planned else "solar_plant_listed"
    elif area >= MID_HA:
        verdict, decisive = "review", ("no_record_found" if _ok(cad) else "size_only")
    else:
        verdict, decisive = "expected", "small_area"
    if soft and verdict == "expected" and not fire_explains:
        verdict, decisive = "review", "protected_buffer"

    # ---- every reason that applies, then the deciding one goes first
    facts: dict[str, dict] = {}
    if fire_recorded:
        facts["fire_recorded"] = _reason(
            "fire_recorded",
            "A wildfire is on record here, so this is a natural change, not construction." if fire_explains
            else "A wildfire is on record here, but it does not explain a new building or ground movement.",
            "lowers" if fire_explains else "neutral", fire, source="Wildfire records")
    if inside and not soft:
        facts["protected_area"] = _reason(
            "protected_area",
            f"The place lies inside a protected area ({names})." if not fire_explains
            else f"The place lies inside {names}; a recorded wildfire is a natural event.",
            "neutral" if fire_explains else "raises", prot)
    elif soft:
        facts["protected_buffer"] = _reason(
            "protected_buffer", f"The place only touches the edge or buffer zone of a protected area ({names}).",
            "neutral" if fire_explains else "raises", prot)
    if assessment_missing:
        facts["assessment_missing"] = _reason(
            "assessment_missing",
            "No completed environmental assessment is on record for this site, although one is required.",
            "raises", off, source="Official records")
    if zone == "non_buildable":
        facts["zoning_non_buildable"] = _reason(
            "zoning_non_buildable", "The land is zoned as non-buildable.", "raises", zon)
    elif zone == "urban":
        facts["zoning_urban"] = _reason("zoning_urban", "The land is zoned as urban.", "lowers", zon)
    if planned:
        facts["planned_sector"] = _reason(
            "planned_sector", "The land is inside a planned development area.", "lowers", zon)
    if built > 0:
        facts["cadastre_building_found"] = _reason(
            "cadastre_building_found", f"{built} new building(s) are registered here since the change.", "lowers", cad)
    if solar_good:
        ha = solar_good[0].get("ha_in_municipality") or solar_good[0].get("ha")
        facts["solar_plant_listed"] = _reason(
            "solar_plant_listed",
            f"A solar plant of about {ha:g} ha is listed for this municipality (the list gives no exact location).",
            "lowers", sol)
    elif solar_other:
        facts["solar_plant_other"] = _reason(
            "solar_plant_other",
            "Solar plants are listed for this municipality, but none is authorised and about as large as this "
            "change, so none explains it.", "neutral", sol)
    if not matching and _ok(cad):
        facts["no_record_found"] = _reason(
            "no_record_found",
            "No registered building, listed solar plant or planned development area matches this change.",
            "raises", cad)
    if decisive == "size_only":
        facts["size_only"] = _reason(
            "size_only", "The land registry could not be checked, so a change of this size is flagged for review.",
            "raises", source="Radar detection")
    if area < MID_HA and verdict != "high_concern":
        facts["small_area"] = _reason(
            "small_area", f"The change is small ({area:g} ha).", "lowers", source="Radar detection")
    for action in actions:
        kind = action.get("kind")
        code = {"stop_order": "official_stop_order", "investigation": "official_investigation"}.get(kind, "official_action")
        facts[f"{code}:{action.get('date')}"] = _reason(
            code, f"{_day(action.get('date'))}: {action.get('text', 'An official step is on record.')}", "raises",
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
        if not _ok(records.get(key))
    ]
    reasons = [facts[decisive]] + [r for k, r in facts.items() if k != decisive] + unavailable
    return verdict, reasons, _explain(change, verdict, reasons)


def _explain(change: dict, verdict: str, reasons: list[dict]) -> str:
    """The radar sentence + the deciding reason + the next reason that points the same way (so the sentence never
    contradicts the label)."""
    direction = "lowers" if verdict == "expected" else "raises"
    texts = [reasons[0]["text"]]
    for r in reasons[1:]:
        if r["effect"] == direction and r["code"] not in ("small_area", "records_unavailable"):
            texts.append(r["text"])
            break
    return " ".join([_first_sentence(change.get("explain"))] + texts).strip()


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
    return shape(geometry).intersects(shape(scope))


def records_for(doc: dict, change_id: str, geometry: dict | None = None) -> dict:
    """The hand-entered records that apply to one change (``default`` overridden by the change's own entries; a
    record whose ``scope`` does not touch ``geometry`` is left out)."""
    merged = {**doc.get("default", {}), **doc.get("changes", {}).get(change_id, {})}
    out = {}
    for key, rec in merged.items():
        scope = rec.get("scope")
        if scope and geometry is not None and not _in_scope(geometry, scope):
            continue
        out[key] = {"checked": True, "source": "Hand-entered records", "url": None,
                    **{k: v for k, v in rec.items() if k != "scope"}}
    return out


# ---- network lookups (sarwatch.context) --------------------------------------------------------------------------

def run_lookups(geometry: dict, change: dict) -> dict:
    from sarwatch.context import lookup_all  # needs the "verdict" extra (requests, shapely, pyproj)

    try:
        return lookup_all(geometry, since=change["first_date"])
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
    offline = hand is not None or _site_country(path) not in (None, "ES")
    before, after, failed = Counter(), Counter(), Counter()
    asked = 0
    for feature in doc["features"]:
        props = feature["properties"]
        before[props.get("verdict") or "unjudged"] += 1
        if hand is not None:
            records = records_for(hand, props["id"], feature["geometry"])
        elif offline:
            records = {}
        else:
            records = lookup(feature["geometry"], props)
            for key, rec in records.items():
                asked += 1
                if not _ok(rec):
                    failed[key] += 1
        props["verdict"], props["reasons"], props["explain"] = judge(props, records)
        after[props["verdict"]] += 1
    if asked and sum(failed.values()) == asked and not allow_unchecked:
        raise SystemExit(
            f"All {asked} lookups failed (offline?), so every label would rest on size alone. Nothing written. "
            "Re-run online, or pass --allow-unchecked to write them anyway."
        )
    if not dry_run:
        path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return before, after, failed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Label every change in a changes.geojson (see kb/verdict-rules.md).")
    parser.add_argument("changes", help="app/data/<site>/changes.geojson")
    parser.add_argument("--records", help="hand-entered records file (skips the live lookups)")
    parser.add_argument("--dry-run", action="store_true", help="print the label counts, write nothing")
    parser.add_argument("--allow-unchecked", action="store_true", help="write labels even if every lookup failed")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    before, after, failed = apply_file(args.changes, args.records, args.dry_run, allow_unchecked=args.allow_unchecked)
    fmt = lambda c: ", ".join(f"{k} {v}" for k, v in sorted(c.items())) or "none"  # noqa: E731
    print(f"labels before: {fmt(before)}\nlabels after:  {fmt(after)}" + ("  (dry run, nothing written)" if args.dry_run else ""))
    if failed:
        print(f"WARNING lookups that failed (those parts rest on size alone): {fmt(failed)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
