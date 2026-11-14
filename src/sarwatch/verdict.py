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
from pathlib import Path

BIG_HA = 5.0  # clearing / earthworks at least this big, on non-buildable land, with no record -> high concern
MID_HA = 2.0  # at least this big with no matching record -> needs review
RECORD_TYPES = ("clearing", "earthworks", "structure")  # change types a solar-plant listing can explain

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


def judge(change: dict, records: dict) -> tuple[str, list[dict], str]:
    """Pure function: ``change`` = one feature's properties, ``records`` = lookup results by key
    (``protected``, ``cadastre``, ``zoning``, ``solar``, ``fire``; each ``{source, url, checked, ...}`` as returned by
    ``sarwatch.context``). Returns ``(verdict, reasons, explain)``. No network."""
    records = records or {}
    area = float(change["area_ha"])
    ctype = change.get("type")
    prot, cad, zon, sol, fire = (records.get(k) for k in ("protected", "cadastre", "zoning", "solar", "fire"))

    inside = _ok(prot) and bool(prot.get("inside"))
    zone = zon.get("zone") if _ok(zon) else None
    built = int(cad.get("built_since") or 0) if _ok(cad) else 0
    planned = zone == "developable"
    solar_listed = _ok(sol) and bool(sol.get("plants")) and ctype in RECORD_TYPES
    matching = built > 0 or planned or solar_listed
    names = ", ".join(a.get("name", "?") for a in (prot.get("areas") or [])[:2]) if inside else ""
    area_text = f"{names}" if names else "a protected nature area"

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

    reasons: list[dict] = []
    if _ok(fire) and fire.get("recorded"):
        verdict = "expected"
        reasons.append(_reason(
            "fire_recorded", "A wildfire is on record here, so this is a natural change, not construction.",
            "lowers", fire, source="Wildfire records"))
        if inside:
            reasons.append(_reason(
                "protected_area", f"The place lies inside {area_text}; a recorded wildfire is a natural event.",
                "neutral", prot))
        return verdict, reasons + unavailable, _explain(change, reasons + unavailable)

    # 1) decisive reason(s)
    if inside:
        verdict = "high_concern"
        reasons.append(_reason("protected_area", f"The place lies inside a protected area ({area_text}).", "raises", prot))
    elif zone == "non_buildable":
        big = area >= BIG_HA and ctype in ("clearing", "earthworks") and not matching
        verdict = "high_concern" if big else "review"
        reasons.append(_reason("zoning_non_buildable", "The land is zoned as non-buildable.", "raises", zon))
    elif matching:
        verdict = "expected"
    elif area >= MID_HA:
        verdict = "review"
    else:
        verdict = "expected"

    # 2) supporting reasons
    if zone == "urban":
        reasons.append(_reason("zoning_urban", "The land is zoned as urban.", "lowers", zon))
    if planned:
        reasons.append(_reason("planned_sector", "The land is inside a planned development area.", "lowers", zon))
    if built > 0:
        reasons.append(_reason(
            "cadastre_building_found", f"{built} new building(s) are registered here since the change.", "lowers", cad))
    if solar_listed:
        reasons.append(_reason(
            "solar_plant_listed",
            "A solar plant is listed for this municipality (the list gives no exact location).", "lowers", sol))
    if not matching and _ok(cad):
        reasons.append(_reason(
            "no_record_found",
            "No registered building, listed solar plant or planned development area matches this change.",
            "raises", cad))
    if area < MID_HA and verdict != "high_concern":
        reasons.append(_reason(
            "small_area", f"The change is small ({area:g} ha).", "lowers", source="Radar detection"))
    reasons += unavailable
    return verdict, reasons, _explain(change, reasons)


def _explain(change: dict, reasons: list[dict]) -> str:
    base = _first_sentence(change.get("explain"))
    texts = [r["text"] for r in reasons if r["code"] != "small_area"][:2] or [r["text"] for r in reasons][:1]
    return " ".join([base] + texts).strip()


# ---- hand-entered records (sites outside Catalonia, offline runs, tests) ----------------------------------------

def load_records_file(path) -> dict:
    """Format: ``{"version": 1, "default": {<key>: record}, "changes": {"<change id>": {<key>: record}}}``.
    A record has the same shape as a lookup result; ``checked`` defaults to true and ``source`` to
    "Hand-entered records". Per-change entries override ``default`` key by key."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("version") != 1:
        raise ValueError(f"{path}: version must be 1")
    return doc


def records_for(doc: dict, change_id: str) -> dict:
    merged = {**doc.get("default", {}), **doc.get("changes", {}).get(change_id, {})}
    return {
        key: {"checked": True, "source": "Hand-entered records", "url": None, **rec}
        for key, rec in merged.items()
    }


# ---- network lookups (need #14: sarwatch.context) ---------------------------------------------------------------

def run_lookups(geometry: dict, change: dict) -> dict:
    try:
        from sarwatch.context import cadastre, protected, solar, zoning
    except ImportError as exc:  # pragma: no cover - depends on #14 being merged
        raise SystemExit(
            "sarwatch.context is missing (the public-record lookups, issue #14). Use --records <file> or merge #14."
        ) from exc
    calls = {
        "protected": lambda: protected.lookup(geometry),
        "cadastre": lambda: cadastre.lookup(geometry, since=change["first_date"]),
        "zoning": lambda: zoning.lookup(geometry),
        "solar": lambda: solar.lookup(geometry),
    }
    out = {}
    for key, call in calls.items():
        try:
            out[key] = call()
        except Exception as exc:  # lookups should never raise; if one does, record it instead of crashing the run
            out[key] = {"source": LABELS[key].capitalize(), "url": None, "checked": False, "error": str(exc)}
    return out


def _site_country(path: Path):
    sites = path.parent.parent / "sites.json"
    try:
        for site in json.loads(sites.read_text(encoding="utf-8"))["sites"]:
            if site["id"] == path.parent.name:
                return site.get("country")
    except (OSError, ValueError, KeyError):
        pass
    return None


def apply_file(path, records_path=None, dry_run=False, lookup=run_lookups) -> tuple[Counter, Counter]:
    """Judge every change in ``path`` and write verdict/reasons/explain back. Returns (labels before, labels after).
    Records come from ``records_path`` (or ``<site>/records.json`` if it exists, or when the site is outside Spain:
    no Catalan lookups there); otherwise from the live lookups."""
    path = Path(path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    if records_path is None and (path.parent / "records.json").is_file():
        records_path = path.parent / "records.json"
    hand = load_records_file(records_path) if records_path else None
    offline = hand is not None or _site_country(path) not in (None, "ES")
    before, after = Counter(), Counter()
    for feature in doc["features"]:
        props = feature["properties"]
        before[props.get("verdict") or "unjudged"] += 1
        if hand is not None:
            records = records_for(hand, props["id"])
        elif offline:
            records = {}
        else:
            records = lookup(feature["geometry"], props)
        props["verdict"], props["reasons"], props["explain"] = judge(props, records)
        after[props["verdict"]] += 1
    if not dry_run:
        path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return before, after


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Label every change in a changes.geojson (see kb/verdict-rules.md).")
    parser.add_argument("changes", help="app/data/<site>/changes.geojson")
    parser.add_argument("--records", help="hand-entered records file (skips the live lookups)")
    parser.add_argument("--dry-run", action="store_true", help="print the label counts, write nothing")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    before, after = apply_file(args.changes, args.records, args.dry_run)
    fmt = lambda c: ", ".join(f"{k} {v}" for k, v in sorted(c.items())) or "none"  # noqa: E731
    print(f"labels before: {fmt(before)}\nlabels after:  {fmt(after)}" + ("  (dry run, nothing written)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
