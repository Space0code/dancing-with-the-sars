# Mentor feedback: what we did with it

Our geospatial mentor looked at the live app and gave eleven points (paraphrased here, in the mentor's order). This page lists each one, what we did and where, and what we chose not to build and why. Last updated 15 Nov 2026, about 00:40; the overnight work sits on the branch `overnight` and reaches `main` only after the team has looked at it in the morning (plan and rules: issue #119).

## The eleven points

| # | Point | Status | What we did and where |
|---|---|---|---|
| 1 | Download the results as vector or raster data, besides the CSV | Done | The Export dialog (`app/js/export.js`, PR #126) offers CSV, **GeoJSON, Shapefile (zip) and GeoTIFF** (`app/js/download.js`, `app/js/geofiles.js`, PR #131) and the PDF report (point 10). The files hold exactly the changes the dialog counts (area, time frame and list filters applied). GeoTIFF: one 8-bit band, about 10 m pixels, value = label class (1 expected, 2 needs review, 3 high concern, 4 not labelled, 0 no change). No map picture in these files. |
| 2 | Choose the time frame and the area of interest | Done | A Filter block in the site drawer (`app/js/timeframe.js`, `app/js/selection.js`, PRs #126 and #137): From and To dates limited to the site's range, and an area. It filters the changes already detected; the map zooms to the area and the total, the overview, the list and every download follow it. The link carries `from=`, `to=`, `bbox=` and `area=file`. |
| 3 | Add the area by uploading a bounding box or a vector file | Done | In the same block (`app/js/aoi.js`, PR #137): draw a box on the map, type four numbers (west, south, east, north), or upload a `.geojson`, `.json`, zipped shapefile (reprojected with its `.prj`), `.kml` or `.gpx` file of up to 5 MB. The file stays in the browser. Several polygons are combined; points and lines use their bounding box, and the app says so. |
| 4 | Use NDVI, the vegetation index from red and near-infrared bands | Done | NASA's HLS product (Landsat + Sentinel-2, 30 m): NDVI over time per change in `series/<id>.json` (PR #127; method in `kb/data-sources.md`, format in `kb/data-contract.md`). The change card shows "NDVI before → after" and a "Greenness over time" graph (`app/js/ndvi.js`, PR #133); nothing when the data is missing. |
| 5 | Besides wildfire, control for flood and snow cover | Done | The same HLS data gives, per change, the snow share around the first date and the water share after the change (PR #127). The verdict step adds a caution or a "clear" note as a reason, never raising a label (`kb/verdict-rules.md`, PR #130). Thresholds are first guesses `(unverified)`; on today's data none fires. |
| 6 | A panel on the left with a checkbox per layer | **Not built** | Team decision, see below. |
| 7 | At least two base maps: satellite and light grey | Done | Satellite and Light switch in the legend box, `base=light` in the link (`app/js/basemap.js`, PR #124). The light map is Esri's Light Gray Canvas: the CARTO map we first planned now needs an API key. It has no place names. |
| 8 | The tour is a good feature | Nothing to do | Kept (`app/tour.json`); steps for the new features are part of the polish pass of the same night. |
| 9 | "NASA optical alerts (Landsat + Sentinel-2)" is wrong, Sentinel-2 is ESA's; be careful with such credits | Done | Everywhere the tool names the optical source it now says "Optical alerts (NASA OPERA product, from Landsat by NASA/USGS and Sentinel-2 by ESA)"; the "Seen by" list names who provides each source (PR #129). The pages below repeat the credits. |
| 10 | A report that explains the changes, and a service that alerts the end user by urgency | Report: mostly done. Alert service: **not built** | A small Cloudflare Worker holds the Gemini key and writes the summary from facts only (PR #128, `kb/report-proxy.md`). The PDF report is package G: map picture as on screen, legend and attribution, key numbers, summary, the changes to look at first, table of all changes, sources (PR #134, **open** when this page was written). If the Worker is slow or blocked, a rule-based summary is used and no error shows. The FAQ says the summary is labelled as AI-written and that the facts and labels come from rules, not from AI. The alert service is below. |
| 11 | The report should be clear, less technical, more visual and informative, so managers can plan action | Planned for the morning | The first version of the report (point 10) is in; its layout and wording get polished after the team has looked at it. |

Also built tonight, not a mentor point: `app/how-it-works.html` and `app/faq.html` (12 questions), linked from the app header, plain English, with the credits of point 9 (PR #125).

## What we deliberately did not build

- **The left panel with layer checkboxes (point 6).** Team decision: the app is a full-width map with details only when something is clicked (no permanent panel, few simple options). The layer switches that exist live in the legend box: base map, and "What the records say" for sites that have record layers.
- **The alert service by urgency (point 10).** Future work: written down under "Further work" in `app/how-it-works.html` ("Alerts sorted by urgency, sent to the people responsible for a place"), not built. The report's ordering rule is its planned trigger: label first (high concern, needs review, not labelled, expected), then size (largest first), then recency (newest first).
- **Polish of the report (point 11).** Planned for the morning, after the first look; the report itself works end to end (point 10).

## Rules the work followed

Place-agnostic tool with no site history; little text; desktop only; full-width map with details on click; few simple options; no glow; never the word "illegal" (a label is a prompt for a person to check, not a finding of wrongdoing); static app without a build step (libraries from a CDN with a pinned version); no secrets or personal data in the repo.

<sub>Written by Claude</sub>
