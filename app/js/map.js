// Written by Claude. MapLibre map: satellite background (no API key), the big picture of the slider date (a canvas
// drawn by picture.js), verdict-colored change polygons with a date filter, a brief flash on new ones, selection.
import { VERDICTS } from "./format.js";

const STYLE = {
  version: 8,
  sources: {
    satellite: {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      maxzoom: 19,
      attribution: "Background imagery © Esri, Maxar, Earthstar Geographics and the GIS User Community",
    },
  },
  layers: [{ id: "base-satellite", type: "raster", source: "satellite" }],
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
const FLASH_MS = 1600; // how long a newly appeared outline glows
const NONE = ["==", ["get", "id"], ""];
// Thin outlines at the site overview (detailed shapes with holes would hide the picture), full width from zoom 15.
const byZoom = (atSite, close) => ["interpolate", ["linear"], ["zoom"], 12, atSite, 15, close];

export function createChangeMap(container, { onSelect, bounds }) {
  // No rotation or tilt: the before/after divider is a vertical line on screen and on the picture alike.
  const map = new maplibregl.Map({
    container, style: STYLE, bounds, fitBoundsOptions: { padding: 40 }, attributionControl: { compact: true },
    dragRotate: false, pitchWithRotate: false, touchPitch: false,
  });
  map.touchZoomRotate.disableRotation();
  map.keyboard.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  new ResizeObserver(() => map.resize()).observe(container);

  let features = new Map();
  let dateIso = "9999-12-31";
  let flashRaf = 0;

  const ready = new Promise((resolve, reject) => {
    map.on("error", (e) => e.error && /style|webgl/i.test(e.error.message) && reject(e.error));
    map.on("load", () => {
      map.addSource("changes", { type: "geojson", data: EMPTY });
      map.addLayer({ id: "changes-fill", type: "fill", source: "changes", paint: { "fill-color": verdictColor, "fill-opacity": 0.3 } });
      map.addLayer({ id: "changes-casing", type: "line", source: "changes", paint: { "line-color": "#1b1b1b", "line-width": byZoom(2.6, 4.5) } });
      map.addLayer({ id: "changes-line", type: "line", source: "changes", paint: { "line-color": verdictColor, "line-width": byZoom(1.4, 2.5) } });
      map.addLayer({
        id: "changes-flash", type: "line", source: "changes", filter: NONE,
        paint: { "line-color": "#ffffff", "line-width": 4, "line-blur": 2, "line-opacity": 0 },
      });
      map.addLayer({
        id: "changes-selected", type: "line", source: "changes", filter: NONE,
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

  let extraFilter = null; // the inbox's verdict / kind filters, as a MapLibre expression
  const withExtra = (filter) => (extraFilter ? ["all", filter, extraFilter] : filter);

  function applyDateFilter() {
    const filter = withExtra(["<=", ["get", "first_date"], dateIso]);
    for (const id of DATE_LAYERS) map.setFilter(id, filter);
  }

  function stopFlash() {
    cancelAnimationFrame(flashRaf);
    map.setFilter("changes-flash", NONE);
  }

  return {
    ready,
    /** Zoom out to show every site (the intro view). */
    showOverview(bbox) {
      map.resize(); // measure the container now, so the box fits the final size
      features = new Map();
      map.getSource("changes").setData(EMPTY);
      this.select(null);
      stopFlash();
      map.fitBounds(bbox, { padding: 40, essential: true });
    },
    showSite(site, collection) {
      map.resize(); // measure the container now, so the camera centers on the final size
      features = new Map(collection.features.map((f) => [f.properties.id, f]));
      map.getSource("changes").setData(collection);
      this.select(null);
      stopFlash();
      applyDateFilter();
      this.fitChanges(site, collection);
    },
    /** Open on the outlined area with a little margin (the site window is much wider); without outlines, the site view. */
    fitChanges(site, collection) {
      const pts = collection.features.flatMap((f) => f.geometry.coordinates.flat(f.geometry.type === "MultiPolygon" ? 2 : 1));
      if (!pts.length) return this.view(site);
      const lons = pts.map((p) => p[0]);
      const lats = pts.map((p) => p[1]);
      const narrow = container.clientWidth < 640; // the switch box covers the top of a phone map
      map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], {
        padding: { top: narrow ? 56 : 110, bottom: narrow ? 30 : 60, left: narrow ? 20 : 60, right: narrow ? 20 : 60 }, maxZoom: 16, essential: true,
      });
    },
    /** Fly to the site; `bottom` px at the bottom stay free (for the tour box). Padding is always set, as MapLibre keeps it. */
    view(site, bottom = 0) {
      map.flyTo({ center: site.center, zoom: site.zoom, padding: { top: 0, right: 0, left: 0, bottom }, essential: true });
    },
    /**
     * Show `canvas` stretched over the four corners `coordinates` (top-left, top-right, bottom-right, bottom-left), under
     * the change shapes; null hides it. Call again after drawing on the canvas: MapLibre copies it only when told to.
     */
    setFrame(canvas, coordinates) {
      if (!canvas) {
        if (map.getLayer("frame")) map.setLayoutProperty("frame", "visibility", "none");
        return;
      }
      const source = map.getSource("frame");
      if (!source || source.getCanvas() !== canvas) {
        if (source) {
          map.removeLayer("frame");
          map.removeSource("frame");
        }
        map.addSource("frame", { type: "canvas", canvas, coordinates, animate: false });
        map.addLayer({ id: "frame", type: "raster", source: "frame", paint: { "raster-fade-duration": 0 } }, "changes-fill");
      } else {
        if (JSON.stringify(source.coordinates) !== JSON.stringify(coordinates)) source.setCoordinates(coordinates);
        source.play(); // play + pause = copy the canvas to the map once
        source.pause();
      }
      map.setLayoutProperty("frame", "visibility", "visible");
      map.triggerRepaint();
    },
    /** Screen position (px from the map's top-left) of a [lon, lat] point. */
    project(lonLat) {
      return map.project(lonLat);
    },
    /** Call `fn` whenever the camera moves (pan, zoom) or the map is resized. */
    onMove(fn) {
      map.on("move", fn);
      map.on("resize", fn);
    },
    setDate(iso) {
      dateIso = iso;
      applyDateFilter();
    },
    /** Let the outlines of these change ids glow for a moment (they just appeared on the timeline). */
    flash(ids) {
      stopFlash();
      if (!ids.length) return;
      map.setFilter("changes-flash", withExtra(["in", ["get", "id"], ["literal", ids]]));
      const start = performance.now();
      const step = (now) => {
        const k = Math.min(1, (now - start) / FLASH_MS);
        map.setPaintProperty("changes-flash", "line-opacity", 1 - k * k);
        map.setPaintProperty("changes-flash", "line-width", 14 - 10 * k);
        if (k < 1) flashRaf = requestAnimationFrame(step);
        else map.setFilter("changes-flash", NONE);
      };
      flashRaf = requestAnimationFrame(step);
    },
    /** Fly so one change fills the view, with room around it. */
    focus(feature, bottom = 0) {
      const g = feature.geometry;
      const pts = g.coordinates.flat(g.type === "MultiPolygon" ? 2 : 1);
      const lons = pts.map((p) => p[0]);
      const lats = pts.map((p) => p[1]);
      map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: { top: 60, right: 60, left: 60, bottom: 60 + bottom }, maxZoom: 15, essential: true });
    },
    select(feature) {
      map.setFilter("changes-selected", ["==", ["get", "id"], feature ? feature.properties.id : ""]);
    },
    setExtraFilter(expression) {
      extraFilter = expression;
      applyDateFilter();
    },
  };
}
