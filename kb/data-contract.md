# Data contract (v1): the hand-off between radar, verdict and app

The one format all three tracks share. The radar track writes it, the verdict step fills in the verdict fields, the web
app only reads it. Last updated 2026-11-14. Living example: `app/data/fixture/` (fake data, made by
`explore/fixture/make_fixture.py`). Check any data with `python -m sarwatch.contract app/data`. Need a change? Ask on #9.

## Files (all under `app/data/`, paths inside a site are relative to its folder)
| File | Written by | What |
|---|---|---|
| `sites.json` | radar | list of sites; `ready: false` sites have no files yet |
| `<site>/changes.geojson` | radar, then verdict | one polygon per detected change |
| `<site>/layers.json` + pictures | radar | pictures laid over the map (radar before / after) |
| `<site>/frames.json` + `frames/` (optional) | radar | picture frames for the time-lapse and the before / after swipe |
| `<site>/evidence/*.png` | radar | small before / after pictures per change, for the card |
| `<site>/series/<change id>.json` | radar | the signal over time per change, for the chart |
| `<site>/story.json` | verdict | plain-language story of the site, dated events, sources |
| `<site>/context/` (optional) | verdict | what the public records say, as map layers the user can switch on |

## `sites.json`
`{"version": 1, "sites": [site, ...]}`, each site:
`id` (lowercase slug = folder name) · `name` · `country` (2 letters) · `ready` (bool) · `fixture` (optional bool: fake
data, the app shows a badge) · `center` `[lon, lat]` · `zoom` · `bbox` `[west, south, east, north]` ·
`time_range` `[start, end]` (the timeline's ends).

**`hidden`** (optional bool): a `ready` site that stays out of the app's site menu (kept as a worked example, e.g.
`agroparc`; also set on `catalonia`, which has no files yet). Files are still checked.

**`snapshots`** (optional, per site): the timeline's stops, `[{"date": "YYYY-MM-DD", "sensor": "<name>"}, ...]`, one per
image date actually used, strictly sorted by date (a date two sensors share is one stop, sensor `"A + B"`), every date
inside `time_range`. The slider steps through these only; a red bar marks each stop where a change has its `first_date`
(a change dated between stops counts at the next stop). Written by `pipeline.py` (`snapshot_list`) and `make_fixture.py`.
Without it the app falls back to the distinct `first_date` values plus both ends of `time_range`.

## `changes.geojson`
GeoJSON FeatureCollection in EPSG:4326 (lon, lat). Geometry: Polygon or MultiPolygon. Properties of each change:
| Field | Type | Meaning |
|---|---|---|
| `id` | string | unique, `<site>-NNNN` |
| `site` | string | the site id |
| `type` | enum | `clearing` · `structure` · `earthworks` · `ground_motion` · `fire` · `other` |
| `first_date`, `last_date` | `YYYY-MM-DD` | first satellite pass where the change shows; last pass where it was still growing. **The timeline shows a change when `first_date` ≤ the slider date** |
| `area_ha` | number > 0 | hectares |
| `sensor` | string | e.g. `NISAR L-band`, `Sentinel-1 C-band`, `OPERA DIST-ALERT` |
| `signal` | object or null | `{metric, before, after, delta}`, e.g. `HV_dB` −14 → −20 (−6): the measured change behind the detection |
| `confidence` | enum | `low` · `medium` · `high` (how sure the detection is, not the verdict) |
| `verdict` | enum or null | `expected` · `review` · `high_concern`; `null` = not judged yet |
| `reasons` | list | `[{code, text, source, url, effect}]`: why the verdict; `effect` = `raises` · `lowers` · `neutral`; `url` may be null. Empty before the verdict step |
| `explain` | string or null | one plain sentence for the card. The radar track writes what was seen; the verdict step may extend it |
| `evidence` | object | `{before, after, series}`: relative paths or null; optional `before_date`, `after_date` (`YYYY-MM-DD`, before ≤ after): when the two pictures were taken (the middle pass of each picture, same as its `layers.json` date) |

Rules: a non-null `verdict` needs at least one reason and an `explain` sentence. The app never shows the word
"illegal"; verdict texts follow `product.md`. Reason `code`s are owned by the verdict track (`verdict-rules.md`);
the fixture uses `protected_area`, `zoning_non_buildable`, `no_record_found`, `planned_sector`,
`cadastre_building_found`, `fire_recorded`, `small_area`.

## `layers.json`
`{"layers": [{id, title, date, url, coordinates, caption}]}`. `coordinates` are the picture's four corners as
`[lon, lat]`, in the order top-left, top-right, bottom-right, bottom-left (exactly what a MapLibre `image` source
takes). `date` is `YYYY-MM-DD` or null. `caption` says in plain words what the picture shows.

## `frames.json` (optional)
`{"coordinates": [4 corners], "sets": [{id, title, caption, frames: [{date, sensor, url}]}]}`. `coordinates` are the
four corners `[lon, lat]` (top-left, top-right, bottom-right, bottom-left) shared by every frame of the site; all
frames are north-up and the same size. Each set (`radar`, `photo`) is one picture per satellite pass or clear day,
`frames` strictly sorted by date; `url` is a path inside the site folder that must exist. The app shows the latest
frame at or before the slider date. Written by `python -m sarwatch.frames <site>` (radar: VH dB, one fixed grey
stretch, pixels that lost echo since summer 2025 tinted magenta-pink; photo: HLS true colour, cloud-free days). A site without `frames.json` is valid.

## `stages.geojson` (optional): one outline that grows
For sites whose parts of one clearing interleave on the ground (Muhos). A FeatureCollection with one feature per date on
which a part was added. Properties: `group` (text id, e.g. `clearing`), `title` (plain words, e.g. "Cleared area"),
`date` (`YYYY-MM-DD`, the `first_date` of the part added), `area_ha` (geodesic area of the union so far), `verdict` (the
strongest verdict among the members so far, or null), `members` (ids in `changes.geojson` included so far). Geometry:
the union of all members up to that date (holes under 1 ha filled, outline smoothed), Polygon or MultiPolygon.
Members are the changes whose outline lies at least half inside the site's `primary_scope`. The app draws, for the
slider date, the latest stage at or before it with one bold outline in its verdict colour; members of a group lose their
own outlines but stay clickable. The validator checks per group: dates strictly increasing, `area_ha` never decreasing,
members exist. Written by the pipeline (`pipeline.write_stages`); the verdict step refreshes `verdict`. A site without the file is valid.

## `series/<change id>.json`
`{"series": [{name, unit, sensor, dates[], values[]}], "events": [{date, label}]}`. Each series has its own dates
(NISAR and Sentinel-1 pass on different days); `values` are numbers or null, the same length as `dates`. `name` is
already plain language (e.g. "Vegetation echo (HV)").

## `story.json`
`{"headline", "story": [paragraph, ...], "events": [{date, label}], "sources": [{title, url}]}`. Events are shown as
markers on the timeline (e.g. "Told an assessment was required"). Optional `"chart": {"title", "file", "note"}`: a
curve for the story panel (e.g. hectares cleared over time at Muhos); `file` sits next to `story.json` and has the
`series/<change id>.json` format; the validator does not check it yet (#73).

## `context/` (optional): what the records say
`context/index.json` = `{"layers": [{id, title, kind, file, source, url, checked, note}]}`: `kind` is `protected` ·
`zoning` · `buildings` · `solar`; `file` is a GeoJSON next to it (`context/<id>.geojson`, EPSG:4326); `checked` is
`YYYY-MM-DD`; `title` (≤ 60 chars) and `note` (≤ 160 chars) are plain language. Feature properties: `label` (always:
the text shown on click) and, where they apply, `class` (zoning: `buildable` · `non_buildable` · `planned`;
protected: `natura2000` · `pein` · `other`), `year` (buildings: construction year), `name`, `status`, `area_ha`.
A site without the folder has no record layers. Each file ≤ 1 MB. Made in #45, shown in #52; the validator does not
check this folder yet.

## Several sensors (optional fields)
Added for changes seen by more than one satellite; design and wording in `multi-sensor-design.md`. All optional, the
format stays version 1: data without them is valid, and the app shows it as before.
- **Change** `not_before` (`YYYY-MM-DD` or null, not after `first_date`): the last date it was known unchanged.
- **Change** `sources`: list of `{sensor, kind, role, first_date, last_date, not_before, confidence, area_ha, share, note}`.
  `kind` = `optical` · `radar`; `role` = `detected` · `late_start` · `not_seen` · `not_watching`; dates are
  `YYYY-MM-DD` or null; `confidence` is `low` · `medium` · `high` or null; `share` is 0..1 (fraction of the change's
  area); `note` = the plain sentence. Dates, `not_before` and `confidence` must be null for `not_seen` and `not_watching`.
- **Site** `sources` (in `sites.json`): list of `{sensor, kind, start, end, revisit_days, sees, risky_months}`;
  `end` may be null (still running), `sees` = change types it can detect, `risky_months` = month numbers 1..12.

```json
"sources": [
 {"sensor": "OPERA DIST-ALERT", "kind": "optical", "role": "detected", "first_date": "2025-07-15",
  "last_date": "2025-07-15", "not_before": "2025-07-05", "confidence": "medium", "area_ha": 61.7, "share": 1.0,
  "note": "An optical alert found vegetation loss here between 5 and 15 July 2025."},
 {"sensor": "NISAR L-band", "kind": "radar", "role": "late_start", "first_date": "2026-06-25",
  "last_date": "2026-06-25", "not_before": null, "confidence": "medium", "area_ha": 58.6, "share": 0.95,
  "note": "NISAR began watching on 25 Jun 2026 and shows the change already under way."}]
```
Fixture: `fixture-0005` (three sources), `fixture-0007` (one source), `fixture-0004` (late start only).

## Size and hygiene
Every file under 10 MB (the validator checks); pictures are PNG; nothing here needs credentials or the network.

<sub>Written by Claude</sub>
