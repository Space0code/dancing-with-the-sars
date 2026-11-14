# Verdict rules: how a change gets its label

How `src/sarwatch/verdict.py` turns "what the public records say" into **expected / needs review / high concern**. Last updated 2026-11-14 (#17, #46, after review). The rules are a **proposal** from `product.md`; the changes we made to it are listed at the bottom. Tune the thresholds at the top of `verdict.py`.

The app flags places for a human to look at. It never says "illegal" and never names who did it: reasons describe what the records show, not who is at fault. A test checks that no output contains accusing words.

## What goes in
`judge(change, records) -> (verdict, reasons, explain)`: a pure function, no network.
- `change`: one feature's properties from `changes.geojson` (uses `type`, `area_ha`, `confidence`, `first_date`, `explain`).
- `records`: lookup results by key, the shape the `sarwatch.context` clients (#14) return. Every record has `checked` (did the service answer).
  - `protected`: `inside`, `areas` (`[{name, kind, overlap_share}]`), `overlap_share` (total) and `core_overlap_share` (the same without buffer zones, which are not protected areas; the verdict uses this one, and falls back to `overlap_share` for hand-entered records). `inside` is true for any overlap; the share says how much. A share of `null` means the service sent no outline: treated as a real overlap (the safe side).
  - `cadastre`: `built_since` = buildings whose construction **year** is ≥ the change's `first_date` year (the registry only has years; `1900-01-01` is a placeholder and never counts as recent).
  - `zoning`: `zone` (`urban` / `developable` / `non_buildable` / null) and `shares` (fraction of the polygon per zone). `zone: null` with `checked: true` means no zoning polygon there (e.g. the sea): unknown, not a failure.
  - `solar`: `plants` (`[{name, status, ha, ha_in_municipality}]`), by municipality only.
  - `fire`: `recorded` (at least half of the change polygon inside a mapped fire) and `fires` (`[{name, date, area_ha, overlap_share}]`), from the EFFIS lookup (`context/fire.py`, #47). The command line asks for fires that started by the change's `first_date` and ended at most a year before it, so an old burn scar does not explain a change today. If the lookup fails, a `records_unavailable` reason says the wildfire map could not be checked (a burn scar may then be mistaken for a clearing). EFFIS does not map fires under about 20 ha.
  - `official`: hand-entered only (below).

## The rule table (first matching row wins)
"Matching record" = a registered building since the change year (`cadastre.built_since > 0`) **or** a planned development area (zoning `developable`, at least half the polygon) **or** an **authorised** solar plant (status Autoritzat / En servei / Aprovat) with a known area covering **at least half** the change's area, for a clearing, earthworks or structure. A smaller plant, a refused or withdrawn one ("No autoritzat", "Desistit") or one with unknown area never counts (it shows as `solar_plant_other`, neutral). **An application still being processed ("En tramitació") is not an authorisation**: it is never a matching record (see the last rows).

| # | Condition | Label | Deciding reason (effect) |
|---|---|---|---|
| 1 | A wildfire is on record **and** the change is `fire`, `clearing` or `other` | **expected** | `fire_recorded` (lowers) |
| 2 | Inside a protected area with an overlap of at least 10 % of the change (or an unknown overlap), not just a buffer zone | **high concern** | `protected_area` (raises) |
| 3 | Required environmental assessment not completed (`official`), clearing or earthworks, `area_ha` ≥ 5, **or at any size when at least half of the change lies inside the official record's own outline (`scope`)**: it is part of the same clearing | **high concern** | `assessment_missing` (raises) |
| 4 | Zoning non-buildable (≥ 25 % of the polygon), clearing or earthworks, `area_ha` ≥ 5, no matching record. *Not for a change under 2 ha with low confidence (row 9).* | **high concern** | `zoning_non_buildable` (raises) |
| 5 | Zoning non-buildable, anything else (same exception) | **needs review** | `zoning_non_buildable` (raises) |
| 6 | Required assessment not completed, `area_ha` ≥ 2 (any size, at least half inside the record's `scope`) | **needs review** | `assessment_missing` (raises) |
| 7 | Any matching record | **expected** | `cadastre_building_found` / `planned_sector` / `solar_plant_listed` (lowers) |
| 7b | **No land records exist for the country** (`cadastre.not_applicable`, e.g. Finland), `clearing`, `area_ha` < 5, no official record applies, nothing above applies | **expected** | `small_no_records` (lowers): "too small to flag on its own", says no records are connected, not that it is fine |
| 8 | `area_ha` ≥ 2, no matching record | **needs review** | `solar_application_pending` if a matching-size application is pending; else `no_record_found`, or `size_only` if the land registry could not be checked (outside Spain, for anything but a small clearing: "No public land records are connected for this country yet…") |
| 9 | Otherwise (small, nothing flagged) | **expected** | `small_uncertain` if `confidence` is `low`: "too small and too uncertain to flag on its own" (not a finding that it is fine); else `small_area` (lowers) |
| after | The result so far is "expected" (and no fire explains the change) and **one of**: only the buffer zone of a protected area is touched · a pending solar application of matching size and no other matching record · an official step is on record (any size, any confidence) | **needs review** | `protected_buffer` · `solar_application_pending` · the first official action (raises) |

A wildfire on record does not explain a new `structure` or `ground_motion`: it is listed as a neutral `fire_recorded` reason and the normal rows apply. In a protected area, a fire that explains the change stays "expected" and `protected_area` is neutral. A protected-area overlap **below 10 %** only borders the area: neutral reason `protected_edge` ("The place borders a protected area"), no effect on the label.

All other reasons that apply are listed after the deciding one: `zoning_urban`, `planned_sector`, `cadastre_building_found`, `solar_plant_listed` / `solar_plant_other` / `solar_application_pending`, `no_record_found` (only if the land registry answered), `small_area` / `small_uncertain` (below 2 ha, unless high concern), `protected_buffer` / `protected_edge` (when not decisive), `assessment_missing` (any size, when the official record says one is required and not finished), and one reason per official action (`official_stop_order`, `official_investigation`, `official_action`, all raises, text starts with the date; two actions of the same kind and date both show).

**Records that could not be checked** (`checked: false` or missing): they count as absent, the label rests on what is left (in the worst case size only: rows 8 and 9), and each gets a `records_unavailable` reason (neutral) saying which service did not answer. `no_record_found` is never claimed when the land registry itself could not be checked.

## What goes out
- `verdict`: `expected` / `review` / `high_concern` (contract enum; the app shows "needs review").
- `reasons`: `[{code, text, source, url, effect}]`, **the deciding reason first**. `source` and `url` come from the lookup, so the card can link to the place in the service.
- `explain`: the radar sentence already in the change (its first sentence) + the deciding reason + the next reason that points the same way, so the sentence never contradicts the label. Re-running starts again from the radar sentence, so the result is the same each time.

## Running it
`python -m sarwatch.verdict app/data/<site>/changes.geojson [--records file.json] [--dry-run] [--offline] [--allow-unchecked]`, then check with `python -m sarwatch.contract app/data`. Needs the `verdict` extra (`pip install -e ".[verdict]"`). It prints the label counts before and after.
- **Catalan sites:** it runs the lookups from #14 and #47 for every change (`cadastre` with `since` = the change's `first_date`, `fire` with `until` = the same date). It prints how many lookups failed per service; if **every** lookup failed (offline?) it refuses to write, because all labels would rest on size alone.
- **`--allow-unchecked` is for tests only, never for a real run.** It writes the labels even when every lookup failed, and that lowers labels (a change that is high concern with its protected-area record comes out as "needs review" without it).
- **Hand-entered records:** `--records file.json`, or a `records.json` next to `changes.geojson` (used automatically, no network). **Sites outside Spain** (e.g. Muhos) never get Catalan lookups: they use their records file, or nothing. The four Catalan services are then marked "not applicable": they add no `records_unavailable` reason, and size decides unless an `official` record says more.
  ```json
  {"version": 1,
   "default": {"official": {"source": "…", "url": "https://…", "assessment_required": true,
                            "assessment_completed": false,
                            "actions": [{"kind": "stop_order", "date": "2026-10-06", "text": "…", "source": "…", "url": "…"}],
                            "scope": {"type": "Polygon", "coordinates": [[[26.0, 64.8], …]]}}},
   "changes": {"muhos-0001": {"fire": {"recorded": true, "source": "…"}}}}
  ```
  Each record has the shape of a lookup result; `checked` defaults to true and `source` to "Hand-entered records". A per-change entry replaces `default` for the same key. A record with a **`scope`** (GeoJSON Polygon/MultiPolygon, EPSG:4326) applies only to changes that **overlap** it (sharing only a border counts as outside), so a stop notice for one site does not label changes elsewhere. **Do not run a site with an unscoped `official` record on a whole region**: every change in the file would get the stop notice as a reason and be lifted to "needs review" (the Muhos trial: 12 more small changes). A scope that is not a Polygon/MultiPolygon is an error, not ignored. (`records_for` without a geometry, as in some tests, skips the scope check.) **A `default` record without a `scope` covers the whole site**, and the assessment reason then says so ("This record covers the whole site, not only this spot."). The `official` record: `assessment_required`, `assessment_completed` (an assessment needed but not finished at the time of the change) and `actions` (`kind` = `stop_order` / `investigation` / other, `date`, `text`, `source`, `url`).

## Run on a site (one command per site)
After the radar track writes or regenerates `app/data/<site>/changes.geojson`:
```
pip install -e ".[verdict]"                                    # once: requests, shapely, pyproj
python -m sarwatch.verdict app/data/<site>/changes.geojson      # Catalan site: live lookups, cached on disk
python -m sarwatch.contract app/data                            # always check the result
```
- **Muhos, after every radar regeneration (one command, safe to repeat):**
  ```
  python -m sarwatch.verdict app/data/muhos/changes.geojson && python -m sarwatch.contract app/data
  ```
  No network (Finland has no Catalan lookups): it uses `app/data/muhos/records.json` next to the changes file, whose `official` record carries the `scope` polygon (the clearing outline, `explore/muhos/clearing_scope.geojson`). It recomputes every label, reason and explain sentence from scratch, so a second run gives the same file; the radar sentence in each `explain` is kept. Then look at the cards: inside the scope (at least half of the change inside the outline) you get the assessment / stop-notice / police reasons and high concern at any size; outside it a clearing under 5 ha is "expected, too small to flag on its own" (`small_no_records`), and anything bigger, or any other kind of change of 2 ha or more, is flagged by size alone. Add `--dry-run` to see the label counts without writing.
- **Cache:** every lookup response is stored under `data/cache/context/` (gitignored; move it with `SARWATCH_CONTEXT_CACHE`), keyed by the request including the change polygon. A re-run after a regeneration only asks the services about polygons it has not seen; unchanged polygons are answered from disk. Failures are not cached, so they are retried.
- **Re-run is safe and identical:** the command recomputes every verdict from scratch. `--offline` answers from the cache only (a miss counts as a failed lookup, and all-failed refuses to write), which gives a byte-identical file; measured on the 185 Agroparc trial changes: 2 s, 0 requests.
- **Cold cost** (measured 14 Nov 2026, trial Agroparc run, all lookups): 392 s for 185 changes = 2.1 s and 7.1 requests per change (protected areas 3, zoning 2, land registry 1, wildfire map 1, solar list once per municipality). Plan about an hour per 1,700 changes the first time.
- Failed lookups are printed per service on stderr; they never silently become labels (see above).

## What we changed from the proposal in `product.md`
- **Order:** a recorded wildfire that can explain the change is checked first, so a fire inside a protected area is "expected", not "high concern".
- **Small and unflagged → expected** (row 9). The proposal did not say what happens below 2 ha with no flag; we chose not to bother a regulator with it. `small_area` is shown so the card says why. For a **low-confidence** change under 2 ha, zoning alone does not flag it either (the Agroparc trial run put 153 of 185 changes on "needs review", mostly small low-confidence blobs): the reason says it is "too small and too uncertain to flag on its own", which is a statement about our evidence, not a finding that it is fine. A protected area still raises it.
- **Matching record on non-buildable land stays "needs review"** (row 5): a building record there is a reason to look, not to relax.
- **Solar listing is weak evidence** (municipality-level, no location): only an authorised plant at least half as large as the change counts, and a plant that is still an application never makes a change "expected". Open question for the specialist (#7): is even an authorised listing enough to call a large change "expected"?
- **Protected areas:** a buffer-zone-only overlap raises to "needs review"; an overlap below 10 % of the change only borders the area (neutral). `overlap_share` is computed from the service's outlines (simplified to 5 m) in metres.
- **Official steps** (a stop notice, an investigation) lift an "expected" to at least "needs review", because a regulator has already acted on the site; they are reasons, not a judgement.
- **Mixed zoning:** a quarter or more non-buildable counts as non-buildable (conservative: it brings a human look, not an accusation). A planned development area is judged on its own share (at least half developable) *before* that override, so a place that is 51 % developable and 49 % non-buildable has both reasons, and the texts give the share ("About 49 % of the place is zoned as non-buildable"); the label stays "needs review" (row 5).
- **`no_record_found` says what it can know:** "No building registered since the change (the land registry often records new buildings months late), no authorised solar plant and no planned development area match this change." Older buildings may stand on the site: the registry only dates buildings by year.
- Caveat: cadastre dates are year-only and can lag the real construction by months, so a recent change can show "no record" for a while. That is why this is "needs review", not an accusation.

<sub>Written by Claude</sub>
