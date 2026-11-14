# Web app

Static site: no build step, no npm. MapLibre GL JS 4.7.1 comes from a CDN; basemaps need no API key.

```
cd app
python -m http.server        # then open http://localhost:8000  (add #site=<id> to open a site directly)
```

Data comes from `app/data/` (format: `kb/data-contract.md`). Sites with `ready: true` in `data/sites.json` show up in the switcher.
Layout: `index.html` · `css/style.css` · `js/` (`main.js` wires `map.js`, `timeline.js`, `panel.js`; wording and colors in `format.js`).
The signal chart (next issue) plugs into `#signal-chart`; `panel.js` fires a `change-shown` event on `document` with `{feature, base}`.

<sub>Written by Claude</sub>
