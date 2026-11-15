# Mentor feedback: what we did with it

Our geospatial mentor looked at the live app and gave eleven points. This page lists each one, what we did and where, and what we chose not to build and why. Last updated 15 Nov 2026, about 00:30; the overnight work sits on the branch `overnight` and reaches `main` only after the team has looked at it in the morning (plan and rules: issue #119).

**Numbering.** Issue #119 numbers eight of the points (1, 2, 3, 4, 5, 7, 9, 10). The other three (numbers 6, 8 and 11) are the "How it works / FAQ" pages and the two things we did not build; which number is which is not recorded in the repo `(unverified)`, so those rows carry no number.

## The eleven points

| # | Point | Status | What we did and where |
|---|---|---|---|
| 1 | Download the changes in GIS formats | Done | The Export dialog (`app/js/export.js`, PR #126) offers CSV, **GeoJSON, Shapefile (zip) and GeoTIFF** (`app/js/download.js`, `app/js/geofiles.js`, PR #131) and the PDF report (below). The files hold exactly the changes the dialog counts (area, time frame and list filters applied). GeoTIFF: one 8-bit band, about 10 m pixels, value = label class (1 expected, 2 needs review, 3 high concern, 4 not labelled, 0 no change). No map picture in these files. |
| 2 | Choose a time frame | In progress | The shared base is merged: `app/js/selection.js` (chosen area and time frame, `filterChanges`) and the map outline for an area (PR #126). The Filter controls on top of it are package A, **not merged yet** when this page was written. |
| 3 | Choose an area (draw a box, type a bounding box, upload GeoJSON, zipped shapefile or KML) | In progress | Same package A as point 2. |
| 4 | Vegetation index (NDVI) per change | Done | NASA's HLS product (Landsat + Sentinel-2, 30 m): NDVI over time per change in `series/<id>.json` (PR #127; method in `kb/data-sources.md`, format in `kb/data-contract.md`). The change card shows "NDVI before → after" and a "Greenness over time" graph (`app/js/ndvi.js`, PR #133); nothing when the data is missing. |
| 5 | Snow and flood can fake a radar change | Done | The same HLS data gives, per change, the snow share around the first date and the water share after the change (PR #127). The verdict step adds a caution or a "clear" note as a reason, never raising a label (`kb/verdict-rules.md`, PR #130). Thresholds are first guesses `(unverified)`; on today's data none fires. |
| 7 | Two base maps | Done | Satellite and Light switch in the legend box, `base=light` in the link (`app/js/basemap.js`, PR #124). The light map is Esri's Light Gray Canvas: the CARTO map we first planned now needs an API key. It has no place names. |
| 9 | Wrong credit: Sentinel-2 is ESA's, not NASA's | Done | Everywhere the tool names the optical source it now says "Optical alerts (NASA OPERA product, from Landsat by NASA/USGS and Sentinel-2 by ESA)"; the "Seen by" list names who provides each source (PR #129). The pages below repeat the credits. |
| 10 | A report to hand on: map picture, key numbers, top changes, short summary | Mostly done | A small Cloudflare Worker holds the Gemini key and writes the summary from facts only (PR #128, `kb/report-proxy.md`). The PDF report is package G: map picture as on screen, legend and attribution, key numbers, summary, the changes to look at first, table of all changes, sources (PR #134, **open** when this page was written). If the Worker is slow or blocked, a rule-based summary is used and no error shows. The FAQ says the summary is labelled as AI-written and that the facts and labels come from rules, not from AI. |
| – | A page that explains how it works and how we handle the hard parts | Done | `app/how-it-works.html` and `app/faq.html` (12 questions), linked from the app header (PR #125). Place-agnostic, plain English, facts from `kb/`. |
| – | A panel on the left with a checkbox per layer | **Not built** | See below. |
| – | An alert service that tells the people responsible, by urgency | **Not built** | See below. |

## What we deliberately did not build

- **The left panel with layer checkboxes.** Team decision: the app is a full-width map with details only when something is clicked (no permanent panel, few simple options). The layer switches that exist live in the legend box: base map, and "What the records say" for sites that have record layers.
- **The alert service by urgency.** Future work: written down under "Further work" in `app/how-it-works.html` ("Alerts sorted by urgency, sent to the people responsible for a place"), not built. The report's ordering rule is its planned trigger: label first (high concern, needs review, not labelled, expected), then size (largest first), then recency (newest first).
- **Polish of the report.** Planned for the morning, after the first look; the report itself works end to end (point 10).

## Rules the work followed

Place-agnostic tool with no site history; little text; desktop only; full-width map with details on click; few simple options; no glow; never the word "illegal" (a label is a prompt for a person to check, not a finding of wrongdoing); static app without a build step (libraries from a CDN with a pinned version); no secrets or personal data in the repo.

<sub>Written by Claude</sub>
