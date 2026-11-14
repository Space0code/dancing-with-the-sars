# Parallax (web app)

Static site: no build step, no npm. MapLibre GL JS 4.7.1 comes from a CDN; basemaps need no API key.

```
cd app
python -m http.server        # then open http://localhost:8000  (add #site=<id> to open a site directly)
```

Data comes from `app/data/` (format: `kb/data-contract.md`). Sites with `ready: true` and no `"hidden": true` in `data/sites.json` show up in the site menu.
Layout: `index.html` · `css/style.css` · `js/` (`main.js` wires `map.js`, `picture.js` (the big picture), `timeline.js`, `drawer.js` (the drawer's views), `panel.js` (overview, card, start box), `inbox.js` (the "Changes" tab: sort, filters, list); the card uses
`chart.js` (SVG signal chart); wording and colors in `format.js`).
Missing series files show a message instead of a broken box.
Look: one system in `css/style.css` (tokens at the top: colour roles, six type sizes, 4-32px spacing, radii, shadows,
motion). Fonts: Funnel Sans and Funnel Display, self-hosted in `fonts/` (OFL); the system font takes over if they fail.
The interface stays neutral (ink on white, one green for the main action, links and focus); strong colour is kept for the
verdicts, the radar picture's pink and the timeline's red bars.

- **Name and pitch:** `APP` in `js/format.js` (one place). One compact legend (`renderLegend` in `js/main.js`); no help dialog. No app text names a site, country or landscape; site content comes only from the data.
- **Layout:** the map has the whole width. Details live in a **drawer** over its right side (about 440 px), closed by default. Clicking a marked area opens that change's card (label, reasons and sources, pictures, signal chart, checklist). The **Changes** button in the header opens the site's **Overview** (computed from `changes.geojson`: one summary line, counts per label, a graph of cumulative changed area, optional `notes` from `sites.json` under "About this data") and the list of changes (sort, filters, "Smallest change", Download CSV). Close with the X, Esc or a click on empty map. No hand-written site story is read or shown.
- **Timeline** (`js/timeline.js`): in Radar the slider steps through the site's `snapshots` (one stop per image date; without them: the change dates plus both ends of `time_range`), in Satellite through the photo dates. A red bar crosses the track at every stop where changes first show (click = jump there). Dates from the tour or a link snap to the stop on or before them.
- **The big picture** (`js/picture.js`, data `frames.json`): one switch, **Radar | Satellite**, 
  The map shows the latest frame of that set at or before the slider date (and says its satellite and date). **Play runs the pictures of the selected view** (radar pictures in Radar, colour photos in Satellite; switching while playing carries on from the nearest date): the slider's steps are the view's pictures (`timeline.setStops`).
  Frames are drawn on one canvas (a MapLibre `canvas` source over the four `coordinates`), neighbours preloaded.
  **Compare before and after** (`js/swipe.js`): a full-height line on the map; left = the set's first frame, right = the
  frame of the slider date. A site without `frames.json` keeps the Esri background and the Radar button is disabled.
- **New changes** simply appear, with their normal look, at the step where they are first seen (no glow, no flash).
- **Marked areas** (`#overlay-btn`, on by default): off hides every shape drawn over the picture (the grown area, each
  change, hover and selection outlines; `map.setOverlay`). It stays off across dates, play, compare and site switches;
  opening a change from the list or the tour turns it back on. Timeline bars, total and side panel are not affected.
- **One growing outline** (optional `stages.geojson`, `map.js`): changes that are members of a stage group have no outline of
  their own; the map draws the latest stage at or before the slider date as one light fill with one bold outline (verdict
  colour, white casing). The member parts stay clickable; hover or select shows a thin outline of just that part.
- **Shareable view** (`js/main.js`): the address bar follows the user: `#site=muhos&date=2026-07-31&change=muhos-0012`
  (site, slider date, open change). Opening or pasting such a link restores that view (a `change=` opens its card; without it the map opens with nothing open); a bad date or id is ignored.
- **Changes list** (`js/inbox.js`): sort, filter by label / kind, a "Smallest change" slider (list, map and the running
  total follow it) and **Download CSV** (`js/csv.js`: the filtered list in its current order; UTF-8 with BOM).
- **Guided tour** (`tour.json`, run by `js/tour.js`): generic steps (no site names) that run on the open site, or on the first real one; the field list is in its `about`.

<sub>Written by Claude</sub>
