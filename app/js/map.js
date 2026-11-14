// Written by Claude. MapLibre map: basemaps (no API key), verdict-colored change polygons, date filter, selection.
import { VERDICTS } from "./format.js";

const BASEMAPS = {
  satellite: "base-satellite",
  light: "base-light",
};

const STYLE = {
  version: 8,
  sources: {
    satellite: {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      maxzoom: 19,
      attribution: "Imagery © Esri, Maxar, Earthstar Geographics and the GIS User Community",
    },
    light: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      maxzoom: 19,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    },
  },
  layers: [
    { id: BASEMAPS.satellite, type: "raster", source: "satellite" },
    { id: BASEMAPS.light, type: "raster", source: "light", layout: { visibility: "none" } },
  ],
};

const verdictColor = [
  "match", ["get", "verdict"],
  "expected", VERDICTS.expected.color,
  "review", VERDICTS.review.color,
  "high_concern", VERDICTS.high_concern.color,
  VERDICTS.none.color,
];

const EMPTY = { type: "FeatureCollection", features: [] };
const DATE_LAYERS = ["changes-fill", "changes-casing", "changes-line"];

export function createChangeMap(container, { onSelect }) {
  const map = new maplibregl.Map({ container, style: STYLE, center: [1.6, 41.8], zoom: 6, attributionControl: { compact: true } });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  new ResizeObserver(() => map.resize()).observe(container);

  let overlayIds = [];
  let features = new Map();
  let dateIso = "9999-12-31";

  const ready = new Promise((resolve, reject) => {
    map.on("error", (e) => e.error && /style|webgl/i.test(e.error.message) && reject(e.error));
    map.on("load", () => {
      map.addSource("changes", { type: "geojson", data: EMPTY });
      map.addLayer({ id: "changes-fill", type: "fill", source: "changes", paint: { "fill-color": verdictColor, "fill-opacity": 0.45 } });
      map.addLayer({ id: "changes-casing", type: "line", source: "changes", paint: { "line-color": "#1b1b1b", "line-width": 4.5 } });
      map.addLayer({ id: "changes-line", type: "line", source: "changes", paint: { "line-color": verdictColor, "line-width": 2.5 } });
      map.addLayer({
        id: "changes-selected", type: "line", source: "changes", filter: ["==", ["get", "id"], ""],
        paint: { "line-color": "#ffffff", "line-width": 3, "line-gap-width": 5, "line-opacity": 0.95 },
      });
      map.on("mouseenter", "changes-fill", () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", "changes-fill", () => (map.getCanvas().style.cursor = ""));
      map.on("click", (e) => {
        const hit = map.queryRenderedFeatures(e.point, { layers: ["changes-fill"] })[0];
        onSelect(hit ? features.get(hit.properties.id) : null);
      });
      resolve();
    });
  });

  let extraFilter = null; // the inbox's verdict / kind filters, as a MapLibre expression
  function applyDateFilter() {
    const byDate = ["<=", ["get", "first_date"], dateIso];
    const filter = extraFilter ? ["all", byDate, extraFilter] : byDate;
    for (const id of DATE_LAYERS) map.setFilter(id, filter);
  }

  return {
    ready,
    showSite(site, collection) {
      map.resize(); // measure the container now, so the camera centers on the final size
      features = new Map(collection.features.map((f) => [f.properties.id, f]));
      map.getSource("changes").setData(collection);
      this.select(null);
      applyDateFilter();
      map.flyTo({ center: site.center, zoom: site.zoom, essential: true });
    },
    /** Lay the site's radar pictures (layers.json) under the change polygons; all start switched off. */
    setOverlays(base, layers) {
      for (const id of overlayIds) {
        map.removeLayer(id);
        map.removeSource(id);
      }
      overlayIds = layers.map((l) => `overlay-${l.id}`);
      layers.forEach((l, i) => {
        map.addSource(overlayIds[i], { type: "image", url: base + l.url, coordinates: l.coordinates });
        map.addLayer({
          id: overlayIds[i], type: "raster", source: overlayIds[i], layout: { visibility: "none" },
          paint: { "raster-opacity": 0.7, "raster-fade-duration": 0 },
        }, "changes-fill");
      });
    },
    setOverlayVisible(id, visible) {
      map.setLayoutProperty(`overlay-${id}`, "visibility", visible ? "visible" : "none");
    },
    setOverlayOpacity(id, opacity) {
      map.setPaintProperty(`overlay-${id}`, "raster-opacity", opacity);
    },
    setDate(iso) {
      dateIso = iso;
      applyDateFilter();
    },
    select(feature) {
      map.setFilter("changes-selected", ["==", ["get", "id"], feature ? feature.properties.id : ""]);
    },
    setExtraFilter(expression) {
      extraFilter = expression;
      applyDateFilter();
    },
    flyToFeature(feature) {
      let [w, s, e, n] = [180, 90, -180, -90];
      const walk = (c) => (typeof c[0] === "number" ? ((w = Math.min(w, c[0])), (e = Math.max(e, c[0])), (s = Math.min(s, c[1])), (n = Math.max(n, c[1]))) : c.forEach(walk));
      walk(feature.geometry.coordinates);
      map.fitBounds([[w, s], [e, n]], { padding: 70, maxZoom: 15, essential: true });
    },
    setBasemap(name) {
      for (const [key, layerId] of Object.entries(BASEMAPS)) {
        map.setLayoutProperty(layerId, "visibility", key === name ? "visible" : "none");
      }
    },
  };
}
