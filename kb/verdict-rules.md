# Verdict rules: how a change gets its label

How `src/sarwatch/verdict.py` turns "what the public records say" into **expected / needs review / high concern**. Last updated 2026-11-14 (#17). The rules are a **proposal** from `product.md`; the changes we made to it are listed at the bottom. Tune the two thresholds (`BIG_HA`, `MID_HA`) at the top of `verdict.py`.

The app flags places for a human to look at. It never says "illegal" and never names who did it: reasons describe what the records show, not who is at fault. A test checks that no output contains accusing words.

## What goes in
`judge(change, records) -> (verdict, reasons, explain)`: a pure function, no network.
- `change`: one feature's properties from `changes.geojson` (uses `type`, `area_ha`, `first_date`, `explain`).
- `records`: lookup results by key, the shape the `sarwatch.context` clients (#14) return: `protected` (`inside`, `areas`), `cadastre` (`built_since` = buildings dated on or after the change's `first_date`), `zoning` (`zone` = `urban` / `developable` / `non_buildable` / null), `solar` (`plants`, by municipality only), `fire` (`recorded`; no lookup client yet, so only from a records file). Every record has `checked` (did the service answer).

## The rule table (first matching row wins)
"Matching record" = a registered building since the change (`cadastre.built_since > 0`) **or** zoning `developable` (planned sector) **or** a listed solar plant in the municipality (only for clearing, earthworks, structure).

| # | Condition | Label | Reason codes (effect) |
|---|---|---|---|
| 1 | A wildfire is on record (`fire.recorded`) | **expected** | `fire_recorded` (lowers); `protected_area` (neutral) if inside a protected area: a fire is a natural event |
| 2 | Inside a protected area (PEIN / Natura 2000) | **high concern** | `protected_area` (raises) |
| 3 | Zoning `non_buildable`, type clearing or earthworks, `area_ha` ≥ 5, no matching record | **high concern** | `zoning_non_buildable` (raises), `no_record_found` (raises) |
| 4 | Zoning `non_buildable`, anything else | **needs review** | `zoning_non_buildable` (raises) |
| 5 | Any matching record | **expected** | `cadastre_building_found` / `planned_sector` / `solar_plant_listed` (lowers) |
| 6 | `area_ha` ≥ 2, no matching record | **needs review** | `no_record_found` (raises) |
| 7 | Otherwise (small, nothing flagged) | **expected** | `small_area` (lowers) |

Supporting reasons are added to every row where they apply: `zoning_urban` (lowers), `planned_sector`, `cadastre_building_found`, `solar_plant_listed`, `no_record_found` (only if the land registry answered), `small_area` (below 2 ha, unless high concern).

**Records that could not be checked** (`checked: false` or missing): they count as absent, the label rests on what is left (in the worst case size only: rows 6 and 7), and each gets a `records_unavailable` reason (neutral) saying which service did not answer. `no_record_found` is never claimed when the land registry itself could not be checked.

## What goes out
- `verdict`: `expected` / `review` / `high_concern` (contract enum; the app shows "needs review").
- `reasons`: `[{code, text, source, url, effect}]`, most decisive first. `source` and `url` come from the lookup, so the card can link to the place in the service.
- `explain`: the radar sentence already in the change (its first sentence) + the texts of the first two reasons. Re-running starts again from the radar sentence, so the result is the same each time.

## Running it
`python -m sarwatch.verdict app/data/<site>/changes.geojson [--records file.json] [--dry-run]`, then check with `python -m sarwatch.contract app/data`. It prints the label counts before and after.
- **Catalan sites:** it runs the four lookups from #14 for every change (`cadastre` with `since` = the change's `first_date`).
- **Hand-entered records:** `--records file.json`, or a `records.json` next to `changes.geojson` (used automatically, no network). **Sites outside Spain** (e.g. Muhos) never get Catalan lookups: they use their records file, or nothing (then every part is `records_unavailable` and size decides).
  ```json
  {"version": 1,
   "default": {"zoning": {"zone": "non_buildable", "source": "Municipal plan", "url": "https://…"}},
   "changes": {"muhos-0001": {"fire": {"recorded": true, "source": "…"}}}}
  ```
  Each record has the shape of a lookup result; `checked` defaults to true and `source` to "Hand-entered records". A per-change entry replaces `default` for the same key.

## What we changed from the proposal in `product.md`
- **Order:** a recorded wildfire is checked first, so a fire inside a protected area is "expected", not "high concern".
- **Small and unflagged → expected** (row 7). The proposal did not say what happens below 2 ha with no flag; we chose not to bother a regulator with it. `small_area` is shown so the card says why.
- **Matching record on non-buildable land stays "needs review"** (row 4): a building record there is a reason to look, not to relax.
- **Solar listing counts as a record only for clearing / earthworks / structure**, and it is municipality-level, so it is weak evidence (the reason text says so). Open question for the specialist (#7): is a municipality-level plant listing enough to call a large change "expected"?
- Caveat: cadastre dates can lag the real construction by months, so a recent change can show "no record" for a while. That is why this is "needs review", not an accusation.

<sub>Written by Claude</sub>
