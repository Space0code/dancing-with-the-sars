// Written by Claude. MapLibre map: basemaps and yearly photos (no API key), verdict-colored change polygons, date filter, selection.
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

export function createChangeMap(container, { onSelect, bounds }) {
  const map = new maplibregl.Map({ container, style: STYLE, bounds, fitBoundsOptions: { padding: 40 }, attributionControl: { compact: true } });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  new ResizeObserver(() => map.resize()).observe(container);

  let overlayIds = [];
  let features = new Map();
  let dateIso = "9999-12-31";
  let basemap = "satellite";
  let photo = null; // the year photo that should be on screen (photos.js), or null for today's imagery
  const photoIds = new Set();

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
      // On narrow maps the attribution line starts folded behind its (i) button, so it doesn't cover the map.
      if (container.clientWidth < 640) container.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
      map.on("mouseenter", "changes-fill", () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", "changes-fill", () => (map.getCanvas().style.cursor = ""));
      map.on("click", (e) => {
        const hit = map.queryRenderedFeatures(e.point, { layers: ["changes-fill"] })[0];
        onSelect(hit ? features.get(hit.properties.id) : null);
      });
      resolve();
    });
  });

  // The newest photo goes on top of the photo stack; the others are hidden only once it has loaded, so the map never flashes.
  const wantedPhoto = () => (basemap === "satellite" && photo ? photo.id : null);
  function hideOtherPhotos() {
    for (const id of photoIds) if (id !== wantedPhoto()) map.setLayoutProperty(id, "visibility", "none");
  }
  function applyPhoto() {
    const wanted = wantedPhoto();
    if (!wanted) return hideOtherPhotos();
    if (!map.getSource(wanted)) {
      map.addSource(wanted, photo.source);
      map.addLayer({ id: wanted, type: "raster", source: wanted, paint: { "raster-fade-duration": 0 } });
      photoIds.add(wanted);
    }
    map.moveLayer(wanted, overlayIds[0] ?? "changes-fill");
    map.setLayoutProperty(wanted, "visibility", "visible");
    map.once("idle", hideOtherPhotos);
  }

  function applyDateFilter() {
    const filter = ["<=", ["get", "first_date"], dateIso];
    for (const id of DATE_LAYERS) map.setFilter(id, filter);
  }

  return {
    ready,
    /** Zoom out to show every site (the intro view). */
    showOverview(bbox) {
      map.resize(); // measure the container now, so the box fits the final size
      features = new Map();
      map.getSource("changes").setData(EMPTY);
      this.select(null);
      map.fitBounds(bbox, { padding: 40, essential: true });
    },
    showSite(site, collection) {
      map.resize(); // measure the container now, so the camera centers on the final size
      features = new Map(collection.features.map((f) => [f.properties.id, f]));
      map.getSource("changes").setData(collection);
      this.select(null);
      applyDateFilter();
      this.view(site);
    },
    /** Fly to the site; `bottom` px at the bottom stay free (for the tour box). Padding is always set, as MapLibre keeps it. */
    view(site, bottom = 0) {
      map.flyTo({ center: site.center, zoom: site.zoom, padding: { top: 0, right: 0, left: 0, bottom }, essential: true });
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
    /** Fly so one change fills the view, with room around it. */
    focus(feature, bottom = 0) {
      const g = feature.geometry;
      const pts = g.coordinates.flat(g.type === "MultiPolygon" ? 2 : 1);
      const lons = pts.map((p) => p[0]);
      const lats = pts.map((p) => p[1]);
      map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: { top: 60, right: 60, left: 60, bottom: 60 + bottom }, maxZoom: 15, essential: true });
    },
    /** Show a year photo from photos.js (or null for today's imagery) under the change shapes. */
    setPhoto(next) {
      if (next?.id === photo?.id) return;
      photo = next;
      applyPhoto();
    },
    select(feature) {
      map.setFilter("changes-selected", ["==", ["get", "id"], feature ? feature.properties.id : ""]);
    },
    setBasemap(name) {
      basemap = name;
      applyPhoto();
      for (const [key, layerId] of Object.entries(BASEMAPS)) {
        map.setLayoutProperty(layerId, "visibility", key === name ? "visible" : "none");
      }
    },
  };
}
