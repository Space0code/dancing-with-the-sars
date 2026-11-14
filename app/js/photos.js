// Written by Claude. Yearly photo basemaps (no API key): ICGC aerial photos inside Catalonia, EOX Sentinel-2 cloudless elsewhere.
// Layer names and years checked against the services' GetCapabilities on 14 Nov 2026.

const ICGC_WMS =
  "https://geoserveis.icgc.cat/servei/catalunya/orto-territorial/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap" +
  "&STYLES=&CRS=EPSG:3857&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256&FORMAT=image/jpeg&LAYERS=";
const CATALONIA = [0.15, 40.5, 3.35, 42.9]; // lon/lat box; the service has no photos outside Catalonia

const range = (from, to) => Array.from({ length: to - from + 1 }, (_, i) => from + i);

const PROVIDERS = {
  icgc: {
    kind: "Aerial photo",
    bounds: CATALONIA,
    maxzoom: 19,
    years: Object.fromEntries([
      ...range(2016, 2025).map((y) => [y, { layer: `ortofoto_25cm_color_${y}`, note: "" }]),
      [2026, { layer: "ortofoto_color_provisional", note: " (provisional)" }],
    ]),
    tiles: (entry) => [ICGC_WMS + entry.layer],
    attribution: () => 'Aerial photos © <a href="https://www.icgc.cat/">Institut Cartogràfic i Geològic de Catalunya (ICGC)</a>',
  },
  eox: {
    kind: "Satellite photo",
    bounds: undefined,
    maxzoom: 15, // Sentinel-2 is 10 m per pixel; closer zooms only enlarge it
    years: Object.fromEntries(range(2017, 2025).map((y) => [y, { layer: `s2cloudless-${y}_3857`, note: "" }])),
    tiles: (entry) => [`https://tiles.maps.eox.at/wmts/1.0.0/${entry.layer}/default/GoogleMapsCompatible/{z}/{y}/{x}.jpg`],
    attribution: (year) =>
      `<a href="https://cloudless.eox.at">Sentinel-2 cloudless</a> by <a href="https://eox.at">EOX IT Services GmbH</a> ` +
      `(Contains modified Copernicus Sentinel data ${year}), ` +
      (year >= 2018
        ? '<a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">CC BY-NC-SA 4.0</a>'
        : '<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>'),
  },
};

const inside = ([lon, lat], [w, s, e, n]) => lon >= w && lon <= e && lat >= s && lat <= n;

/** Which photo series fits a site: the sharp Catalan aerial photos when the site is in Catalonia, else Sentinel-2. */
export const providerFor = (site) => (site && inside(site.center, CATALONIA) ? "icgc" : "eox");

/**
 * The photo for one year, or null when that year has none (the map then shows today's imagery).
 * Returns { id, source (a MapLibre raster source), label } where label is what the map shows, e.g. "Aerial photo: 2023".
 */
export function photoFor(providerId, year) {
  const p = PROVIDERS[providerId];
  const entry = p?.years[year];
  if (!entry) return null;
  return {
    id: `photo-${providerId}-${year}`,
    label: `${p.kind}: ${year}${entry.note}`,
    source: {
      type: "raster", tiles: p.tiles(entry), tileSize: 256, maxzoom: p.maxzoom,
      ...(p.bounds && { bounds: p.bounds }), attribution: p.attribution(year),
    },
  };
}
