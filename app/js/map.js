// Written by Claude. MapLibre map: satellite background (no API key), the big picture of the slider date (a canvas
// drawn by picture.js), verdict-colored change polygons with a date filter, selection, and a switch that hides them all.
// A site with stages.geojson draws its grouped changes as ONE area with one bold outline that grows with the date.
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
    // Light grey base map (Esri Light Gray Canvas, no key). CARTO's free Positron tiles now answer "API KEY REQUIRED".
    // Only fetched while its layer is visible. Its native detail ends at zoom 16; closer in, the tiles are stretched.
    light: {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      maxzoom: 16,
      attribution: "Background map © Esri, HERE, Garmin, © OpenStreetMap contributors and the GIS User Community",
    },
  },
  layers: [
    { id: "base-satellite", type: "raster", source: "satellite" },
    { id: "base-light", type: "raster", source: "light", layout: { visibility: "none" } },
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
// everything drawn over the picture for the changes: the grown area, each change, the hover / selection outlines
const OVERLAY_LAYERS = ["stage-fill", "stage-casing", "stage-line", ...DATE_LAYERS, "part-casing", "part-line", "changes-selected"];
const OWN_OUTLINE = ["!", ["get", "grouped"]]; // changes in a group have no outline of their own (the stage has one)
const PART = ["==", ["get", "id"], ""]; // the part under the pointer or selected: a thin outline
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
  let stages = [];
  let hoverId = "";
  let selectedId = "";
  let dateIso = "9999-12-31";
  let overlayOn = true; // the marked areas drawn over the picture; off shows the bare picture

  const ready = new Promise((resolve, reject) => {
    map.on("error", (e) => e.error && /style|webgl/i.test(e.error.message) && reject(e.error));
    map.on("load", () => {
      map.addSource("changes", { type: "geojson", data: EMPTY });
      map.addSource("stage", { type: "geojson", data: EMPTY });
      // the grown area: one light fill, one bold outline with a thin white casing (reads on the grey and the colour picture)
      map.addLayer({ id: "stage-fill", type: "fill", source: "stage", paint: { "fill-color": verdictColor, "fill-opacity": 0.16 } });
      map.addLayer({ id: "stage-casing", type: "line", source: "stage", layout: { "line-join": "round" }, paint: { "line-color": "#ffffff", "line-width": 5.5 } });
      map.addLayer({ id: "stage-line", type: "line", source: "stage", layout: { "line-join": "round" }, paint: { "line-color": verdictColor, "line-width": 3 } });
      // grouped parts stay clickable but add no fill (a hairline opacity keeps them hit-testable)
      map.addLayer({ id: "changes-fill", type: "fill", source: "changes", paint: { "fill-color": verdictColor, "fill-opacity": ["case", ["get", "grouped"], 0.01, 0.3] } });
      map.addLayer({ id: "changes-casing", type: "line", source: "changes", filter: OWN_OUTLINE, paint: { "line-color": "#1b1b1b", "line-width": byZoom(2.6, 4.5) } });
      map.addLayer({ id: "changes-line", type: "line", source: "changes", filter: OWN_OUTLINE, paint: { "line-color": verdictColor, "line-width": byZoom(1.4, 2.5) } });
      map.addLayer({ id: "part-casing", type: "line", source: "changes", filter: PART, paint: { "line-color": "#1b1b1b", "line-width": 4 } });
      map.addLayer({ id: "part-line", type: "line", source: "changes", filter: PART, paint: { "line-color": "#ffffff", "line-width": 1.8 } });
      map.addLayer({
        id: "changes-selected", type: "line", source: "changes", filter: NONE,
        paint: { "line-color": "#ffffff", "line-width": 3, "line-gap-width": 5, "line-opacity": 0.95 },
      });
      // On narrow maps the attribution line starts folded behind its (i) button, so it doesn't cover the map.
      if (container.clientWidth < 640) container.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
      map.on("mouseenter", "changes-fill", () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", "changes-fill", () => {
        map.getCanvas().style.cursor = "";
        hover("");
      });
      map.on("mousemove", "changes-fill", (e) => hover(e.features?.[0]?.properties.grouped ? e.features[0].properties.id : ""));
      map.on("click", (e) => {
        const hit = map.queryRenderedFeatures(e.point, { layers: ["changes-fill"] })[0];
        onSelect(hit ? features.get(hit.properties.id) : null);
      });
      resolve();
    });
  });

  let extraFilter = null; // the inbox's verdict / kind filters, as a MapLibre expression
  let shownIds = null; // the selection's changes (selection.js): only these are drawn; null = all
  const idFilter = () => (shownIds ? ["in", ["get", "id"], ["literal", [...shownIds]]] : null);
  const withExtra = (filter) => { const parts = [filter, extraFilter, idFilter()].filter(Boolean); return parts.length > 1 ? ["all", ...parts] : filter; };

  function applyDateFilter() {
    const filter = withExtra(["<=", ["get", "first_date"], dateIso]);
    for (const id of DATE_LAYERS) map.setFilter(id, id === "changes-fill" ? filter : ["all", filter, OWN_OUTLINE]);
  }

  /** The stage to draw at the slider date: the latest one at or before it (none before the first). */
  function applyStage() {
    const now = stages.filter((f) => f.properties.date <= dateIso && (!shownIds || f.properties.members.some((id) => shownIds.has(id)))).at(-1);
    map.getSource("stage").setData(now ? { type: "FeatureCollection", features: [now] } : EMPTY);
  }

  /** A grouped part gets a thin outline while the pointer is on it or it is selected; other changes have their own. */
  function showPart() {
    const id = hoverId || selectedId;
    map.setFilter("part-casing", id ? ["==", ["get", "id"], id] : PART);
    map.setFilter("part-line", id ? ["==", ["get", "id"], id] : PART);
  }
  function hover(id) {
    hoverId = id;
    showPart();
  }

  function applyOverlay() {
    for (const id of OVERLAY_LAYERS) map.setLayoutProperty(id, "visibility", overlayOn ? "visible" : "none");
  }

  return {
    ready,
    maplibre: map, // for layers drawn by other modules (records.js)
    /** Zoom out to show every site (the intro view). */
    showOverview(bbox) {
      map.resize(); // measure the container now, so the box fits the final size
      features = new Map();
      map.getSource("changes").setData(EMPTY);
      stages = [];
      applyStage();
      this.select(null);
      map.fitBounds(bbox, { padding: 40, essential: true });
    },
    showSite(site, collection, stageCollection = null) {
      map.resize(); // measure the container now, so the camera centers on the final size
      features = new Map(collection.features.map((f) => [f.properties.id, f]));
      stages = (stageCollection?.features ?? []).slice().sort((a, b) => a.properties.date.localeCompare(b.properties.date));
      const grouped = new Set(stages.flatMap((f) => f.properties.members));
      // the map's copy knows which changes belong to a group; the originals (card, list) stay untouched
      const drawn = { ...collection, features: collection.features.map((f) => ({ ...f, properties: { ...f.properties, grouped: grouped.has(f.properties.id) } })) };
      map.getSource("changes").setData(drawn);
      this.select(null);
      applyDateFilter();
      applyStage();
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
        map.addLayer({ id: "frame", type: "raster", source: "frame", paint: { "raster-fade-duration": 0 } }, map.getStyle().layers.find((l) => !l.id.startsWith("base-"))?.id); // right above the base maps, so record layers (records.js) and change shapes stay on top
      } else {
        if (JSON.stringify(source.coordinates) !== JSON.stringify(coordinates)) source.setCoordinates(coordinates);
        source.play(); // play + pause = copy the canvas to the map once
        source.pause();
      }
      map.setLayoutProperty("frame", "visibility", "visible");
      map.triggerRepaint();
    },
    /** Show one base map, "satellite" or "light"; the picture, marked areas and record layers stay as they are. */
    setBase(id) {
      for (const base of ["satellite", "light"]) map.setLayoutProperty(`base-${base}`, "visibility", base === id ? "visible" : "none");
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
      applyStage();
    },
    /** Show (true) or hide (false) every marked area over the picture; it stays that way across dates and sites. */
    setOverlay(on) {
      overlayOn = on;
      applyOverlay();
    },
    /** Fly so one change fills the view, with room around it; `right` / `bottom` px stay free (the drawer, the tour box). */
    focus(feature, { bottom = 0, right = 0 } = {}) {
      const g = feature.geometry;
      const pts = g.coordinates.flat(g.type === "MultiPolygon" ? 2 : 1);
      const lons = pts.map((p) => p[0]);
      const lats = pts.map((p) => p[1]);
      map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: { top: 60, right: 60 + right, left: 60, bottom: 60 + bottom }, maxZoom: 15, essential: true });
    },
    select(feature) {
      selectedId = feature ? feature.properties.id : "";
      map.setFilter("changes-selected", ["all", ["==", ["get", "id"], selectedId], OWN_OUTLINE]);
      showPart();
    },
    /** Draw only the changes with these ids (a Set), or all of them with null. */
    setShownIds(ids) {
      shownIds = ids;
      applyDateFilter();
      applyStage();
    },
    /** The selected area as a thin dashed outline above the picture, below the marked areas; null removes it. */
    setAreaOutline(geometry) {
      const data = geometry ? { type: "Feature", properties: {}, geometry } : EMPTY;
      const source = map.getSource("area");
      if (source) return source.setData(data);
      map.addSource("area", { type: "geojson", data });
      map.addLayer({ id: "area-casing", type: "line", source: "area", layout: { "line-join": "round" }, paint: { "line-color": "#ffffff", "line-width": 3.5 } }, "stage-fill");
      map.addLayer({ id: "area-line", type: "line", source: "area", layout: { "line-join": "round" }, paint: { "line-color": "#0a0a0a", "line-width": 1.6, "line-dasharray": [3, 2] } }, "stage-fill");
    },
    /**
     * PNG data URL of the map as it is on screen now (picture, marked areas, record layers, area outline). MapLibre's canvas
     * is only readable right after a render, so this repaints and reads it inside that render event.
     */
    snapshot() {
      return new Promise((resolve, reject) => {
        map.once("render", () => {
          try {
            resolve(map.getCanvas().toDataURL("image/png"));
          } catch (err) {
            reject(err);
          }
        });
        map.triggerRepaint();
      });
    },
    setExtraFilter(expression) {
      extraFilter = expression;
      applyDateFilter();
    },
  };
}
