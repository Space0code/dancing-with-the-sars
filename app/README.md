# Web app

Static site: no build step, no npm. MapLibre GL JS 4.7.1 comes from a CDN; basemaps need no API key.

```
cd app
python -m http.server        # then open http://localhost:8000  (add #site=<id> to open a site directly)
```

Data comes from `app/data/` (format: `kb/data-contract.md`). Sites with `ready: true` and no `"hidden": true` in `data/sites.json` show up in the site menu.
Layout: `index.html` · `css/style.css` · `js/` (`main.js` wires `map.js`, `picture.js` (the big picture), `timeline.js`, `panel.js`, `inbox.js` (the "Changes" tab: sort, filters, list); the card uses
`chart.js` (SVG signal chart); wording and colors in `format.js`).
Missing series files show a message instead of a broken box.
Look: one system in `css/style.css` (tokens at the top: colour roles, six type sizes, 4-32px spacing, radii, shadows,
motion). Fonts: Funnel Sans and Funnel Display, self-hosted in `fonts/` (OFL); the system font takes over if they fail.
The interface stays neutral (ink on white, one green for the main action, links and focus); strong colour is kept for the
verdicts, the radar picture's pink and the timeline's red bars.

- **Name and pitch:** `APP` in `js/format.js` (one place). Explainer text: the `<dialog>` in `index.html`.
- **Timeline** (`js/timeline.js`): the slider steps through the site's `snapshots` (one stop per image date; without them: the change dates plus both ends of `time_range`). A red bar crosses the track at every stop where changes first show (click = jump there); story events are grey flags. Dates from the tour or a link snap to the stop on or before them.
- **The big picture** (`js/picture.js`, data `frames.json`): one switch, **Radar | Satellite**, with the set's `caption` under it.
  The map shows the latest frame of that set at or before the slider date (and says its date); play always switches to Radar.
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
- **Guided tour** (`tour.json`, run by `js/tour.js`): edit the steps without touching code; the field list is in its
  `about`. Steps whose site isn't ready are skipped; steps on the fake site run only while no real site is ready.

<sub>Written by Claude</sub>
