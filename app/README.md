# Web app

Static site: no build step, no npm. MapLibre GL JS 4.7.1 comes from a CDN; basemaps need no API key.

```
cd app
python -m http.server        # then open http://localhost:8000  (add #site=<id> to open a site directly)
```

Data comes from `app/data/` (format: `kb/data-contract.md`). Sites with `ready: true` in `data/sites.json` show up in the switcher.
Layout: `index.html` · `css/style.css` · `js/` (`main.js` wires `map.js`, `timeline.js`, `panel.js`, `overlays.js`, `inbox.js` (the "Changes" tab: sort, filters, list); the card uses
`chart.js` (SVG signal chart) and `swipe.js` (before/after); wording and colors in `format.js`).
Missing pictures, series files or radar-picture layers show a message instead of a broken box.

- **Name and pitch:** `APP` in `js/format.js` (one place). Explainer text: the `<dialog>` in `index.html`.
- **Year photos** (`js/photos.js`): in photo view the background follows the slider year. ICGC aerial photos inside
  Catalonia (2016–2025, 2026 provisional), EOX Sentinel-2 cloudless elsewhere (2017–2025); other years fall back to Esri.
- **Guided tour** (`tour.json`, run by `js/tour.js`): edit the steps without touching code; the field list is in its
  `about`. Steps whose site isn't ready are skipped; steps on the fake site run only while no real site is ready.

<sub>Written by Claude</sub>
