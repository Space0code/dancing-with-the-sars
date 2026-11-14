# Verdict rules: how a change gets its label

How `src/sarwatch/verdict.py` turns "what the public records say" into **expected / needs review / high concern**. Last updated 2026-11-14 (#17, after review fixes). The rules are a **proposal** from `product.md`; the changes we made to it are listed at the bottom. Tune the thresholds at the top of `verdict.py`.

The app flags places for a human to look at. It never says "illegal" and never names who did it: reasons describe what the records show, not who is at fault. A test checks that no output contains accusing words.

## What goes in
`judge(change, records) -> (verdict, reasons, explain)`: a pure function, no network.
- `change`: one feature's properties from `changes.geojson` (uses `type`, `area_ha`, `first_date`, `explain`).
- `records`: lookup results by key, the shape the `sarwatch.context` clients (#14) return. Every record has `checked` (did the service answer).
  - `protected`: `inside`, `areas` (`[{name, kind, overlap_share}]`), `overlap_share` (total). `inside` is true for any overlap; the share says how much.
  - `cadastre`: `built_since` = buildings whose construction **year** is ≥ the change's `first_date` year (the registry only has years; `1900-01-01` is a placeholder and never counts as recent).
  - `zoning`: `zone` (`urban` / `developable` / `non_buildable` / null) and `shares` (fraction of the polygon per zone). `zone: null` with `checked: true` means no zoning polygon there (e.g. the sea): unknown, not a failure.
  - `solar`: `plants` (`[{name, status, ha, ha_in_municipality}]`), by municipality only.
  - `fire`: `recorded`. No lookup client yet, so only from a records file.
  - `official`: hand-entered only (below).

## The rule table (first matching row wins)
"Matching record" = a registered building since the change year (`cadastre.built_since > 0`) **or** a planned development area (zoning `developable`, at least half the polygon) **or** a listed solar plant that is **authorised** (status not "No autoritzat" / "Desistit"), has a known area covering **at least half** the change's area, and the change is a clearing, earthworks or structure. A small or refused listing never counts (it shows as `solar_plant_other`, neutral).

| # | Condition | Label | Deciding reason (effect) |
|---|---|---|---|
| 1 | A wildfire is on record **and** the change is `fire`, `clearing` or `other` | **expected** | `fire_recorded` (lowers) |
| 2 | Inside a protected area, not just a buffer zone or an edge touch | **high concern** | `protected_area` (raises) |
| 3 | Required environmental assessment not completed (`official`), clearing or earthworks, `area_ha` ≥ 5 | **high concern** | `assessment_missing` (raises) |
| 4 | Zoning non-buildable (≥ 25 % of the polygon), clearing or earthworks, `area_ha` ≥ 5, no matching record | **high concern** | `zoning_non_buildable` (raises) |
| 5 | Zoning non-buildable, anything else | **needs review** | `zoning_non_buildable` (raises) |
| 6 | Required assessment not completed, `area_ha` ≥ 2 | **needs review** | `assessment_missing` (raises) |
| 7 | Any matching record | **expected** | `cadastre_building_found` / `planned_sector` / `solar_plant_listed` (lowers) |
| 8 | `area_ha` ≥ 2, no matching record | **needs review** | `no_record_found` (raises); `size_only` if the land registry could not be checked |
| 9 | Otherwise (small, nothing flagged) | **expected** | `small_area` (lowers) |
| after | Only touches a protected area's buffer zone or edge, and the result so far is "expected" | **needs review** | `protected_buffer` (raises) |

A wildfire on record does not explain a new `structure` or `ground_motion`: it is listed as a neutral `fire_recorded` reason and the normal rows apply. In a protected area, a fire that explains the change stays "expected" and `protected_area` is neutral.

All other reasons that apply are listed after the deciding one: `zoning_urban`, `planned_sector`, `cadastre_building_found`, `solar_plant_listed` / `solar_plant_other`, `no_record_found` (only if the land registry answered), `small_area` (below 2 ha, unless high concern), `protected_buffer` (when not decisive), and one reason per official action (`official_stop_order`, `official_investigation`, `official_action`, all raises, text starts with the date).

**Records that could not be checked** (`checked: false` or missing): they count as absent, the label rests on what is left (in the worst case size only: rows 8 and 9), and each gets a `records_unavailable` reason (neutral) saying which service did not answer. `no_record_found` is never claimed when the land registry itself could not be checked.

## What goes out
- `verdict`: `expected` / `review` / `high_concern` (contract enum; the app shows "needs review").
- `reasons`: `[{code, text, source, url, effect}]`, **the deciding reason first**. `source` and `url` come from the lookup, so the card can link to the place in the service.
- `explain`: the radar sentence already in the change (its first sentence) + the deciding reason + the next reason that points the same way, so the sentence never contradicts the label. Re-running starts again from the radar sentence, so the result is the same each time.

## Running it
`python -m sarwatch.verdict app/data/<site>/changes.geojson [--records file.json] [--dry-run] [--allow-unchecked]`, then check with `python -m sarwatch.contract app/data`. Needs the `verdict` extra (`pip install -e ".[verdict]"`). It prints the label counts before and after.
- **Catalan sites:** it runs the four lookups from #14 for every change (`cadastre` with `since` = the change's `first_date`). It prints how many lookups failed per service; if **every** lookup failed (offline?) it refuses to write, because all labels would rest on size alone. `--allow-unchecked` overrides that.
- **Hand-entered records:** `--records file.json`, or a `records.json` next to `changes.geojson` (used automatically, no network). **Sites outside Spain** (e.g. Muhos) never get Catalan lookups: they use their records file, or nothing. The four Catalan services are then marked "not applicable": they add no `records_unavailable` reason, and size decides unless an `official` record says more.
  ```json
  {"version": 1,
   "default": {"official": {"source": "…", "url": "https://…", "assessment_required": true,
                            "assessment_completed": false,
                            "actions": [{"kind": "stop_order", "date": "2026-10-06", "text": "…", "source": "…", "url": "…"}],
                            "scope": {"type": "Polygon", "coordinates": [[[26.0, 64.8], …]]}}},
   "changes": {"muhos-0001": {"fire": {"recorded": true, "source": "…"}}}}
  ```
  Each record has the shape of a lookup result; `checked` defaults to true and `source` to "Hand-entered records". A per-change entry replaces `default` for the same key. A record with a **`scope`** (GeoJSON Polygon/MultiPolygon, EPSG:4326) applies only to changes that intersect it, so a stop order for one site does not label changes elsewhere. The `official` record: `assessment_required`, `assessment_completed` (an assessment needed but not finished at the time of the change) and `actions` (`kind` = `stop_order` / `investigation` / other, `date`, `text`, `source`, `url`).

## Run on a site (one command per site)
After the radar track writes or regenerates `app/data/<site>/changes.geojson`:
```
pip install -e ".[verdict]"                                   # once: requests, shapely, pyproj
python -m sarwatch.verdict app/data/agroparc/changes.geojson   # Catalan site: live lookups, cached on disk
python -m sarwatch.verdict app/data/muhos/changes.geojson      # Finland: uses app/data/muhos/records.json, no network
python -m sarwatch.contract app/data                           # always check the result
```
- **Cache:** every lookup response is stored under `data/cache/context/` (gitignored; move it with `SARWATCH_CONTEXT_CACHE`), keyed by the request including the change polygon. A re-run after a regeneration only asks the services about polygons it has not seen; unchanged polygons are answered from disk. Failures are not cached, so they are retried.
- **Re-run is safe and identical:** the command recomputes every verdict from scratch. `--offline` answers from the cache only (a miss counts as a failed lookup, and all-failed refuses to write), which gives a byte-identical file; measured on the 185 Agroparc trial changes: 2 s, 0 requests.
- **Cold cost** (measured 14 Nov 2026, trial Agroparc run): 326 s for 185 changes = 1.8 s and 6.1 requests per change (protected areas 3, zoning 2, land registry 1, solar list once per municipality). Plan about an hour per 2,000 changes the first time.
- Failed lookups are printed per service on stderr; they never silently become labels (see above).

## What we changed from the proposal in `product.md`
- **Order:** a recorded wildfire that can explain the change is checked first, so a fire inside a protected area is "expected", not "high concern".
- **Small and unflagged → expected** (row 9). The proposal did not say what happens below 2 ha with no flag; we chose not to bother a regulator with it. `small_area` is shown so the card says why.
- **Matching record on non-buildable land stays "needs review"** (row 5): a building record there is a reason to look, not to relax.
- **Solar listing is weak evidence** (municipality-level, no location), so it counts only if authorised and at least half as large as the change. Open question for the specialist (#7): is even that enough to call a large change "expected"?
- **Buffer zones and edge touches** of protected areas are "needs review", not "high concern". `protected.lookup` says `inside` for any overlap, so an edge touch is recognised by `overlap_share` (share of the change polygon inside any protected area, 0-1; the lookup computes it from the service's outlines, simplified to 5 m). Below 1 % counts as an edge touch.
- **Mixed zoning:** a quarter or more non-buildable counts as non-buildable (conservative: it brings a human look, not an accusation).
- Caveat: cadastre dates are year-only and can lag the real construction by months, so a recent change can show "no record" for a while. That is why this is "needs review", not an accusation.

<sub>Written by Claude</sub>
