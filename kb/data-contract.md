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
| `<site>/evidence/*.png` | radar | small before / after pictures per change, for the card |
| `<site>/series/<change id>.json` | radar | the signal over time per change, for the chart |
| `<site>/story.json` | verdict | plain-language story of the site, dated events, sources |
| `<site>/context/` (optional) | verdict | what the public records say, as map layers the user can switch on |

## `sites.json`
`{"version": 1, "sites": [site, ...]}`, each site:
`id` (lowercase slug = folder name) · `name` · `country` (2 letters) · `ready` (bool) · `fixture` (optional bool: fake
data, the app shows a badge) · `center` `[lon, lat]` · `zoom` · `bbox` `[west, south, east, north]` ·
`time_range` `[start, end]` (the timeline's ends).

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

## `series/<change id>.json`
`{"series": [{name, unit, sensor, dates[], values[]}], "events": [{date, label}]}`. Each series has its own dates
(NISAR and Sentinel-1 pass on different days); `values` are numbers or null, the same length as `dates`. `name` is
already plain language (e.g. "Vegetation echo (HV)").

## `story.json`
`{"headline", "story": [paragraph, ...], "events": [{date, label}], "sources": [{title, url}]}`. Events are shown as
markers on the timeline (e.g. "Told an assessment was required").

## `context/` (optional): what the records say
`context/index.json` = `{"layers": [{id, title, kind, file, source, url, checked, note}]}`: `kind` is `protected` ·
`zoning` · `buildings` · `solar`; `file` is a GeoJSON next to it (`context/<id>.geojson`, EPSG:4326); `checked` is
`YYYY-MM-DD`; `title` (≤ 60 chars) and `note` (≤ 160 chars) are plain language. Feature properties: `label` (always:
the text shown on click) and, where they apply, `class` (zoning: `buildable` · `non_buildable` · `planned`;
protected: `natura2000` · `pein` · `other`), `year` (buildings: construction year), `name`, `status`, `area_ha`.
Records without map positions (the solar-plant list only names municipalities) are not a layer but an entry in an
optional `"notes": [{kind, source, url, checked, note}]` next to `layers`, e.g. the plants filed in the box's towns.
A site without the folder has no record layers. Each file ≤ 1 MB. Made in #45 (`python -m sarwatch.context.layers
<site>`), shown in #52; the validator does not check this folder yet.

## Size and hygiene
Every file under 10 MB (the validator checks); pictures are PNG; nothing here needs credentials or the network.

<sub>Written by Claude</sub>
