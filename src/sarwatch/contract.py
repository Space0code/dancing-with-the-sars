"""Validate app/data against the hand-off contract (kb/data-contract.md).

Standard library only, so every track can run it without the geo stack:

    python -m sarwatch.contract app/data
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

VERSION = 1
CHANGE_TYPES = {"clearing", "structure", "earthworks", "ground_motion", "fire", "other"}
VERDICTS = {"expected", "review", "high_concern"}
CONFIDENCE = {"low", "medium", "high"}
EFFECTS = {"raises", "lowers", "neutral"}
SOURCE_KINDS = {"optical", "radar"}
SOURCE_ROLES = {"detected", "late_start", "not_seen", "not_watching"}
NO_DETECTION_ROLES = {"not_seen", "not_watching"}
MAX_FILE_MB = 10


def _is_date(value) -> bool:
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_lonlat(value) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(_is_num(v) for v in value)
        and -180 <= value[0] <= 180
        and -90 <= value[1] <= 90
    )


def _load(path: Path, errors: list[str]):
    if not path.is_file():
        errors.append(f"{path}: missing")
        return None
    if path.stat().st_size > MAX_FILE_MB * 1024 * 1024:
        errors.append(f"{path}: larger than {MAX_FILE_MB} MB")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: invalid JSON ({exc})")
        return None


def _check_events(events, where: str, errors: list[str]) -> None:
    if not isinstance(events, list):
        errors.append(f"{where}: events must be a list")
        return
    for i, event in enumerate(events):
        if not isinstance(event, dict) or not _is_date(event.get("date")) or not isinstance(event.get("label"), str):
            errors.append(f"{where}: events[{i}] needs date (YYYY-MM-DD) and label")


def _check_rel_file(site_dir: Path, rel, where: str, errors: list[str], required: bool = False) -> None:
    if rel is None:
        if required:
            errors.append(f"{where}: path is required")
        return
    if not isinstance(rel, str) or rel.startswith(("/", "http")) or ".." in rel:
        errors.append(f"{where}: must be a path relative to the site folder, got {rel!r}")
    elif not (site_dir / rel).is_file():
        errors.append(f"{where}: file not found: {rel}")


def _check_site_meta(site, i: int, errors: list[str]) -> bool:
    where = f"sites.json: sites[{i}]"
    if not isinstance(site, dict):
        errors.append(f"{where}: must be an object")
        return False
    sid = site.get("id")
    if not isinstance(sid, str) or not sid or not sid.replace("-", "").isalnum() or sid != sid.lower():
        errors.append(f"{where}: id must be a lowercase slug")
        return False
    where = f"sites.json: {sid}"
    for key in ("name", "country"):
        if not isinstance(site.get(key), str) or not site[key]:
            errors.append(f"{where}: {key} must be a non-empty string")
    if not isinstance(site.get("ready"), bool):
        errors.append(f"{where}: ready must be true or false")
    if not _is_lonlat(site.get("center")):
        errors.append(f"{where}: center must be [lon, lat]")
    if not _is_num(site.get("zoom")):
        errors.append(f"{where}: zoom must be a number")
    bbox = site.get("bbox")
    if not (
        isinstance(bbox, list)
        and len(bbox) == 4
        and all(_is_num(v) for v in bbox)
        and bbox[0] < bbox[2]
        and bbox[1] < bbox[3]
    ):
        errors.append(f"{where}: bbox must be [west, south, east, north]")
    rng = site.get("time_range")
    if not (isinstance(rng, list) and len(rng) == 2 and all(_is_date(v) for v in rng) and rng[0] <= rng[1]):
        errors.append(f"{where}: time_range must be [start, end] dates")
    if "sources" in site:
        _check_site_sources(site["sources"], where, errors)
    if "snapshots" in site:
        _check_snapshots(site["snapshots"], rng, where, errors)
    return True


def _check_snapshots(snapshots, rng, where: str, errors: list[str]) -> None:
    """Optional `snapshots`: [{"date", "sensor"}, ...], dates strictly increasing and inside time_range."""
    if not isinstance(snapshots, list):
        errors.append(f"{where}: snapshots must be a list")
        return
    previous = None
    for j, snap in enumerate(snapshots):
        at = f"{where}: snapshots[{j}]"
        if not (isinstance(snap, dict) and _is_date(snap.get("date"))):
            errors.append(f"{at}: must be an object with a YYYY-MM-DD date")
            return
        if not isinstance(snap.get("sensor"), str) or not snap["sensor"].strip():
            errors.append(f"{at}: sensor must be a non-empty string")
        if previous is not None and snap["date"] <= previous:
            errors.append(f"{at}: dates must be sorted, one per date ({snap['date']} after {previous})")
        previous = snap["date"]
        if isinstance(rng, list) and len(rng) == 2 and all(_is_date(v) for v in rng) and not rng[0] <= snap["date"] <= rng[1]:
            errors.append(f"{at}: {snap['date']} is outside time_range")


def _is_date_or_null(value) -> bool:
    return value is None or _is_date(value)


def _check_site_sources(sources, where: str, errors: list[str]) -> None:
    """Optional: which satellites watch this site, and when."""
    if not isinstance(sources, list):
        errors.append(f"{where}: sources must be a list")
        return
    for i, s in enumerate(sources):
        w = f"{where}: sources[{i}]"
        if not isinstance(s, dict):
            errors.append(f"{w}: must be an object")
            continue
        if not isinstance(s.get("sensor"), str) or not s["sensor"]:
            errors.append(f"{w}: sensor must be a non-empty string")
        if s.get("kind") not in SOURCE_KINDS:
            errors.append(f"{w}: kind must be one of {sorted(SOURCE_KINDS)}")
        if not (_is_date(s.get("start")) and _is_date_or_null(s.get("end"))):
            errors.append(f"{w}: start must be YYYY-MM-DD and end YYYY-MM-DD or null")
        elif s["end"] is not None and s["start"] > s["end"]:
            errors.append(f"{w}: start must not be after end")
        if not (_is_num(s.get("revisit_days")) and s["revisit_days"] > 0):
            errors.append(f"{w}: revisit_days must be a positive number")
        sees = s.get("sees")
        if not (isinstance(sees, list) and all(t in CHANGE_TYPES for t in sees)):
            errors.append(f"{w}: sees must be a list of change types {sorted(CHANGE_TYPES)}")
        months = s.get("risky_months")
        if not (
            isinstance(months, list)
            and all(isinstance(m, int) and not isinstance(m, bool) and 1 <= m <= 12 for m in months)
        ):
            errors.append(f"{w}: risky_months must be a list of month numbers 1..12")


def _check_change_sources(sources, where: str, errors: list[str]) -> None:
    """Optional: what each satellite said about this change (kb/multi-sensor-design.md)."""
    if not isinstance(sources, list):
        errors.append(f"{where}: sources must be a list")
        return
    for i, s in enumerate(sources):
        w = f"{where}: sources[{i}]"
        if not isinstance(s, dict):
            errors.append(f"{w}: must be an object")
            continue
        if not isinstance(s.get("sensor"), str) or not s["sensor"]:
            errors.append(f"{w}: sensor must be a non-empty string")
        if s.get("kind") not in SOURCE_KINDS:
            errors.append(f"{w}: kind must be one of {sorted(SOURCE_KINDS)}")
        role = s.get("role")
        if role not in SOURCE_ROLES:
            errors.append(f"{w}: role must be one of {sorted(SOURCE_ROLES)}")
        dates = [s.get(k) for k in ("first_date", "last_date", "not_before")]
        if not all(_is_date_or_null(d) for d in dates):
            errors.append(f"{w}: first_date, last_date and not_before must be YYYY-MM-DD or null")
        elif role in NO_DETECTION_ROLES and any(d is not None for d in dates):
            errors.append(f"{w}: dates must be null for role {role}")
        elif None not in dates[:2] and dates[0] > dates[1]:
            errors.append(f"{w}: first_date must not be after last_date")
        elif dates[2] is not None and dates[0] is not None and dates[2] > dates[0]:
            errors.append(f"{w}: not_before must not be after first_date")
        conf = s.get("confidence")
        if conf is not None and conf not in CONFIDENCE:
            errors.append(f"{w}: confidence must be null or one of {sorted(CONFIDENCE)}")
        elif conf is not None and role in NO_DETECTION_ROLES:
            errors.append(f"{w}: confidence must be null for role {role}")
        if s.get("area_ha") is not None and not (_is_num(s["area_ha"]) and s["area_ha"] > 0):
            errors.append(f"{w}: area_ha must be null or a positive number")
        if s.get("share") is not None and not (_is_num(s["share"]) and 0 <= s["share"] <= 1):
            errors.append(f"{w}: share must be null or a number from 0 to 1")
        if not isinstance(s.get("note"), str):
            errors.append(f"{w}: note must be a string")


def _check_story(site_dir: Path, errors: list[str]) -> None:
    path = site_dir / "story.json"
    story = _load(path, errors)
    if story is None:
        return
    if not isinstance(story.get("headline"), str) or not story["headline"]:
        errors.append(f"{path}: headline must be a non-empty string")
    paragraphs = story.get("story")
    if not (isinstance(paragraphs, list) and paragraphs and all(isinstance(p, str) for p in paragraphs)):
        errors.append(f"{path}: story must be a non-empty list of paragraphs")
    _check_events(story.get("events", []), str(path), errors)
    for i, src in enumerate(story.get("sources", [])):
        if not isinstance(src, dict) or not isinstance(src.get("title"), str) or not isinstance(src.get("url"), str):
            errors.append(f"{path}: sources[{i}] needs title and url")


def _check_series(site_dir: Path, rel: str, errors: list[str]) -> None:
    path = site_dir / rel
    data = _load(path, errors)
    if data is None:
        return
    series = data.get("series")
    if not isinstance(series, list) or not series:
        errors.append(f"{path}: series must be a non-empty list")
        return
    for i, s in enumerate(series):
        where = f"{path}: series[{i}]"
        if not isinstance(s, dict):
            errors.append(f"{where}: must be an object")
            continue
        for key in ("name", "unit", "sensor"):
            if not isinstance(s.get(key), str):
                errors.append(f"{where}: {key} must be a string")
        dates, values = s.get("dates"), s.get("values")
        if not (isinstance(dates, list) and all(_is_date(d) for d in dates)):
            errors.append(f"{where}: dates must be a list of YYYY-MM-DD")
        elif not (
            isinstance(values, list)
            and len(values) == len(dates)
            and all(v is None or _is_num(v) for v in values)
        ):
            errors.append(f"{where}: values must be numbers (or null), same length as dates")
    _check_events(data.get("events", []), str(path), errors)


def _check_layers(site_dir: Path, errors: list[str]) -> None:
    path = site_dir / "layers.json"
    data = _load(path, errors)
    if data is None:
        return
    layers = data.get("layers")
    if not isinstance(layers, list):
        errors.append(f"{path}: layers must be a list")
        return
    seen = set()
    for i, layer in enumerate(layers):
        where = f"{path}: layers[{i}]"
        if not isinstance(layer, dict):
            errors.append(f"{where}: must be an object")
            continue
        lid = layer.get("id")
        if not isinstance(lid, str) or lid in seen:
            errors.append(f"{where}: id must be a unique string")
        seen.add(lid)
        if not isinstance(layer.get("title"), str):
            errors.append(f"{where}: title must be a string")
        if layer.get("date") is not None and not _is_date(layer["date"]):
            errors.append(f"{where}: date must be YYYY-MM-DD or null")
        coords = layer.get("coordinates")
        if not (isinstance(coords, list) and len(coords) == 4 and all(_is_lonlat(c) for c in coords)):
            errors.append(
                f"{where}: coordinates must be 4 [lon, lat] corners (top-left, top-right, bottom-right, bottom-left)"
            )
        _check_rel_file(site_dir, layer.get("url"), f"{where}: url", errors, required=True)


def _check_geometry(geom, where: str, errors: list[str]) -> None:
    if not isinstance(geom, dict) or geom.get("type") not in ("Polygon", "MultiPolygon"):
        errors.append(f"{where}: geometry must be a Polygon or MultiPolygon")
        return
    polygons = geom.get("coordinates")
    if geom["type"] == "Polygon":
        polygons = [polygons]
    try:
        for rings in polygons:
            for ring in rings:
                if len(ring) < 4 or ring[0] != ring[-1] or not all(_is_lonlat(list(p[:2])) for p in ring):
                    raise ValueError
    except (TypeError, ValueError, IndexError):
        errors.append(f"{where}: rings must be closed lists of [lon, lat] (EPSG:4326)")


def _check_change(feature, site_id: str, site_dir: Path, seen: set, where: str, errors: list[str]) -> None:
    if not isinstance(feature, dict) or feature.get("type") != "Feature":
        errors.append(f"{where}: must be a GeoJSON Feature")
        return
    _check_geometry(feature.get("geometry"), where, errors)
    p = feature.get("properties")
    if not isinstance(p, dict):
        errors.append(f"{where}: properties missing")
        return
    cid = p.get("id")
    if not isinstance(cid, str) or not cid.startswith(f"{site_id}-") or cid in seen:
        errors.append(f"{where}: id must be unique and start with '{site_id}-'")
    seen.add(cid)
    where = f"{where} ({cid})"
    if p.get("site") != site_id:
        errors.append(f"{where}: site must be '{site_id}'")
    if p.get("type") not in CHANGE_TYPES:
        errors.append(f"{where}: type must be one of {sorted(CHANGE_TYPES)}")
    first, last = p.get("first_date"), p.get("last_date")
    if not (_is_date(first) and _is_date(last) and first <= last):
        errors.append(f"{where}: first_date and last_date must be dates with first <= last")
    if not (_is_num(p.get("area_ha")) and p["area_ha"] > 0):
        errors.append(f"{where}: area_ha must be a positive number")
    if not isinstance(p.get("sensor"), str) or not p["sensor"]:
        errors.append(f"{where}: sensor must be a non-empty string")
    not_before = p.get("not_before")
    if not _is_date_or_null(not_before):
        errors.append(f"{where}: not_before must be YYYY-MM-DD or null")
    elif not_before is not None and _is_date(first) and not_before > first:
        errors.append(f"{where}: not_before must not be after first_date")
    if "sources" in p:
        _check_change_sources(p["sources"], where, errors)
    signal = p.get("signal")
    if signal is not None:
        ok = isinstance(signal, dict) and isinstance(signal.get("metric"), str)
        ok = ok and all(signal.get(k) is None or _is_num(signal.get(k)) for k in ("before", "after", "delta"))
        if not ok:
            errors.append(f"{where}: signal must be null or {{metric, before, after, delta}}")
    if p.get("confidence") not in CONFIDENCE:
        errors.append(f"{where}: confidence must be one of {sorted(CONFIDENCE)}")
    verdict = p.get("verdict")
    if verdict is not None and verdict not in VERDICTS:
        errors.append(f"{where}: verdict must be null or one of {sorted(VERDICTS)}")
    reasons = p.get("reasons")
    if not isinstance(reasons, list):
        errors.append(f"{where}: reasons must be a list (empty before the verdict step)")
        reasons = []
    for i, r in enumerate(reasons):
        ok = isinstance(r, dict) and all(isinstance(r.get(k), str) and r[k] for k in ("code", "text", "source"))
        ok = ok and (r.get("url") is None or isinstance(r.get("url"), str)) and r.get("effect") in EFFECTS
        if not ok:
            errors.append(f"{where}: reasons[{i}] needs code, text, source, url (or null), effect in {sorted(EFFECTS)}")
    explain = p.get("explain")
    if explain is not None and not isinstance(explain, str):
        errors.append(f"{where}: explain must be a string or null")
    if verdict is not None and (not reasons or not explain):
        errors.append(f"{where}: a verdict needs at least one reason and an explain sentence")
    evidence = p.get("evidence")
    if not isinstance(evidence, dict):
        errors.append(f"{where}: evidence must be an object with before, after, series")
        return
    for key in ("before", "after", "series"):
        _check_rel_file(site_dir, evidence.get(key), f"{where}: evidence.{key}", errors)
    dates = [evidence.get(k) for k in ("before_date", "after_date")]  # optional: when the two pictures were taken
    if any(d is not None and not _is_date(d) for d in dates):
        errors.append(f"{where}: evidence.before_date and after_date must be YYYY-MM-DD when present")
    elif None not in dates and dates[0] > dates[1]:
        errors.append(f"{where}: evidence.before_date must not be after after_date")
    if isinstance(evidence.get("series"), str) and (site_dir / evidence["series"]).is_file():
        _check_series(site_dir, evidence["series"], errors)


def validate(data_dir) -> list[str]:
    """Return a list of problems found under data_dir (empty list = valid)."""
    data_dir = Path(data_dir)
    errors: list[str] = []
    index = _load(data_dir / "sites.json", errors)
    if index is None:
        return errors
    if index.get("version") != VERSION:
        errors.append(f"sites.json: version must be {VERSION}")
    sites = index.get("sites")
    if not isinstance(sites, list) or not sites:
        errors.append("sites.json: sites must be a non-empty list")
        return errors
    ids = set()
    for i, site in enumerate(sites):
        if not _check_site_meta(site, i, errors):
            continue
        sid = site["id"]
        if sid in ids:
            errors.append(f"sites.json: duplicate id {sid}")
        ids.add(sid)
        if site.get("ready") is not True:
            continue
        site_dir = data_dir / sid
        _check_story(site_dir, errors)
        _check_layers(site_dir, errors)
        changes = _load(site_dir / "changes.geojson", errors)
        if changes is None:
            continue
        features = changes.get("features")
        if changes.get("type") != "FeatureCollection" or not isinstance(features, list):
            errors.append(f"{site_dir / 'changes.geojson'}: must be a FeatureCollection")
            continue
        seen: set = set()
        for j, feature in enumerate(features):
            _check_change(feature, sid, site_dir, seen, f"{sid}/changes.geojson: features[{j}]", errors)
    return errors


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    data_dir = Path(args[0]) if args else Path("app/data")
    errors = validate(data_dir)
    for line in errors:
        print(f"ERROR {line}")
    if errors:
        print(f"{len(errors)} problem(s) in {data_dir}")
        return 1
    index = json.loads((data_dir / "sites.json").read_text(encoding="utf-8"))
    ready = [s["id"] for s in index["sites"] if s.get("ready")]
    print(f"OK: {data_dir} is valid ({len(index['sites'])} sites, ready: {', '.join(ready) or 'none'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
