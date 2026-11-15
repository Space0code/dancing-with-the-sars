// Written by Claude. The "Area" row of the Filter block: draw a box, type a bbox, or upload a file (GeoJSON, zipped
// shapefile, KML, GPX). The result goes to setArea() (selection.js); nothing here uploads anything: files are read in the
// browser. Libraries load only when a shapefile / KML / GPX is chosen (pinned versions, CDN).
import { h } from "./format.js";
import { getSelection, setArea, onSelectionChange } from "./selection.js";

const MAX_BYTES = 5 * 1024 * 1024;
const LIBS = {
  shp: "https://cdn.jsdelivr.net/npm/shpjs@4.0.4/dist/shp.min.js", // also reprojects with the .prj file
  toGeoJSON: "https://cdn.jsdelivr.net/npm/@tmcw/togeojson@5.8.1/dist/togeojson.umd.js", // KML and GPX
};
const loaded = {};
function loadLib(name) {
  if (window[name]) return Promise.resolve();
  loaded[name] ??= new Promise((resolve, reject) => {
    const s = h("script", { src: LIBS[name] });
    s.onload = resolve;
    s.onerror = () => {
      delete loaded[name];
      reject(new Error("A helper library could not be loaded. Check your connection."));
    };
    document.head.append(s);
  });
  return loaded[name];
}

class FileProblem extends Error {}
const fail = (message) => {
  throw new FileProblem(message);
};

const round4 = (n) => Math.round(n * 1e4) / 1e4;
const fmt = (n) => String(round4(n));

/** [west, south, east, north] of any GeoJSON coordinates. */
function coordsBox(coords, box = [Infinity, Infinity, -Infinity, -Infinity]) {
  if (typeof coords[0] === "number") {
    box[0] = Math.min(box[0], coords[0]);
    box[1] = Math.min(box[1], coords[1]);
    box[2] = Math.max(box[2], coords[0]);
    box[3] = Math.max(box[3], coords[1]);
  } else for (const c of coords) coordsBox(c, box);
  return box;
}

export const boxPolygon = ([w, s, e, n]) => ({ type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] });
const geometryBox = (g) => coordsBox(g.coordinates);

/** "26.05, 64.81, 26.15, 64.86" (commas, spaces or semicolons) -> [w, s, e, n]; throws a FileProblem with the message. */
export function parseBbox(text) {
  const parts = text.trim().split(/[\s,;]+/).filter(Boolean);
  const nums = parts.map(Number);
  if (parts.length !== 4 || nums.some((n) => !Number.isFinite(n))) fail("Enter four numbers: west, south, east, north.");
  const [w, s, e, n] = nums;
  if (w < -180 || e > 180 || s < -90 || n > 90) fail("Out of range: longitude is -180 to 180, latitude -90 to 90.");
  if (w >= e) fail("West must be smaller than east.");
  if (s >= n) fail("South must be smaller than north.");
  return nums;
}

/** Every geometry in a GeoJSON object, flattened. */
function geometries(obj, out = []) {
  if (!obj) return out;
  if (Array.isArray(obj)) obj.forEach((o) => geometries(o, out));
  else if (obj.type === "FeatureCollection") geometries(obj.features, out);
  else if (obj.type === "Feature") geometries(obj.geometry, out);
  else if (obj.type === "GeometryCollection") geometries(obj.geometries, out);
  else if (obj.coordinates) out.push(obj);
  return out;
}

/**
 * GeoJSON (any shape) -> { geometry (Polygon / MultiPolygon), count (areas), boxOnly (points or lines only) }.
 * Throws a FileProblem for "no features" and for coordinates that are not degrees.
 */
export function areaFromGeoJSON(obj) {
  const list = geometries(obj);
  if (!list.length) fail("No shapes found in this file.");
  const box = list.reduce((b, g) => coordsBox(g.coordinates, b), [Infinity, Infinity, -Infinity, -Infinity]);
  const [w, s, e, n] = box;
  if (![w, s, e, n].every(Number.isFinite) || w < -180 || e > 180 || s < -90 || n > 90) fail("This file is not in longitude/latitude (EPSG:4326).");
  const polygons = [];
  for (const g of list) {
    if (g.type === "Polygon") polygons.push(g.coordinates);
    else if (g.type === "MultiPolygon") polygons.push(...g.coordinates);
  }
  if (polygons.length) {
    const geometry = polygons.length === 1 ? { type: "Polygon", coordinates: polygons[0] } : { type: "MultiPolygon", coordinates: polygons };
    return { geometry, count: polygons.length, boxOnly: false };
  }
  const pad = 0.005; // one point (or a straight line) has no area: give it a small box
  if (e - w < pad) { box[0] = w - pad / 2; box[2] = e + pad / 2; }
  if (n - s < pad) { box[1] = s - pad / 2; box[3] = n + pad / 2; }
  return { geometry: boxPolygon(box), count: 1, boxOnly: true };
}

/** Read a File into GeoJSON (any shape). Throws a FileProblem with a plain message. */
async function readFile(file) {
  if (file.size > MAX_BYTES) fail("This file is over 5 MB.");
  const name = file.name.toLowerCase();
  const ext = name.slice(name.lastIndexOf(".") + 1);
  if (!["geojson", "json", "zip", "kml", "gpx"].includes(ext)) fail("Use a .geojson, .json, .zip (shapefile), .kml or .gpx file.");
  try {
    if (ext === "geojson" || ext === "json") return JSON.parse(await file.text());
    if (ext === "zip") {
      await loadLib("shp");
      const result = await window.shp(await file.arrayBuffer());
      return Array.isArray(result) ? { type: "FeatureCollection", features: result.flatMap((c) => c.features) } : result;
    }
    await loadLib("toGeoJSON");
    const doc = new DOMParser().parseFromString(await file.text(), "text/xml");
    if (doc.querySelector("parsererror")) fail("This file could not be read.");
    return window.toGeoJSON[ext](doc);
  } catch (err) {
    if (err instanceof FileProblem || /library/.test(err.message)) throw err;
    return fail("This file could not be read.");
  }
}

/**
 * `mount`: where the row goes. `map`: createChangeMap's return value. `getSite()`: the open site. `hideDrawer()` /
 * `showDrawer()`: the drawer steps aside while drawing. `room()`: pixels on the right the drawer covers.
 */
export function createAoi(mount, { map, getSite, hideDrawer, showDrawer, room }) {
  const maplibre = map.maplibre;
  const mapEl = document.getElementById("map");
  const bboxInput = h("input", { type: "text", id: "aoi-bbox", placeholder: "west, south, east, north", "aria-label": "Bounding box: west, south, east, north, in degrees", autocomplete: "off" });
  const fileInput = h("input", { type: "file", accept: ".geojson,.json,.zip,.kml,.gpx", hidden: true, "aria-label": "Upload an area file" });
  const drawBtn = h("button", { type: "button", class: "tool-btn" }, "Draw box");
  const typeBtn = h("button", { type: "button", class: "tool-btn", "aria-expanded": "false" }, "Enter bbox");
  const fileBtn = h("button", { type: "button", class: "tool-btn" }, "Upload file");
  const applyBtn = h("button", { type: "submit", class: "tool-btn primary" }, "Apply");
  const bboxForm = h("form", { class: "bbox-form", hidden: true }, bboxInput, applyBtn);
  const status = h("span", { class: "area-status-text" });
  const clearBtn = h("button", { type: "button", class: "link-btn" }, "Clear");
  const statusLine = h("p", { class: "area-status", hidden: true }, status, clearBtn);
  const message = h("p", { class: "tool-msg", role: "status", hidden: true });
  mount.append(
    h("div", { class: "tool-row" },
      h("span", { class: "tool-label" }, "Area"),
      h("div", { class: "tool-buttons" }, drawBtn, typeBtn, fileBtn)),
    h("p", { class: "tool-hint" }, "Stays on your computer"),
    bboxForm, statusLine, message, fileInput
  );

  let label = null; // what the status line says; null = no area chosen through this block
  let fromFile = false; // the area is an uploaded file (or its box, after a reload)
  let drawing = null;

  const say = (text, kind = "error") => {
    message.textContent = text ?? "";
    message.hidden = !text;
    message.classList.toggle("info", kind === "info");
  };

  function outsideNote(box) {
    const site = getSite();
    if (!site?.bbox) return null;
    const [w, s, e, n] = site.bbox;
    if (box[0] > e || box[2] < w || box[1] > n || box[3] < s) return `No detected changes here. This site covers ${fmt(w)}, ${fmt(s)} – ${fmt(e)}, ${fmt(n)}.`;
    return null;
  }

  function zoomTo(box) {
    maplibre.fitBounds([[box[0], box[1]], [box[2], box[3]]], { padding: { top: 60, bottom: 60, left: 60, right: 60 + (room?.() ?? 0) }, maxZoom: 15, essential: true });
  }

  function showStatus() {
    statusLine.hidden = !getSelection().area || !label;
    status.textContent = label ?? "";
  }

  /** Select `geometry` and say `text` in the status line. */
  function choose(geometry, text, { zoom = true, note = null, file = false } = {}) {
    label = text;
    fromFile = file;
    if (file) bboxInput.value = ""; // an uploaded shape is not a typed box: no stale numbers in the field
    setArea(geometry);
    showStatus();
    const box = geometryBox(geometry);
    const outside = outsideNote(box);
    say(outside ?? note, outside ? "error" : "info");
    if (zoom) zoomTo(box);
  }

  const boxLabel = (b) => `Box ${fmt(b[0])}, ${fmt(b[1])} – ${fmt(b[2])}, ${fmt(b[3])}`;
  const setBox = (b, opts) => {
    bboxInput.value = b.map(fmt).join(", "); // the field shows the box that is applied (also after drawing), not an older entry
    choose(boxPolygon(b), boxLabel(b), opts);
  };

  // --- Enter bbox ---
  typeBtn.addEventListener("click", () => {
    bboxForm.hidden = !bboxForm.hidden;
    typeBtn.setAttribute("aria-expanded", String(!bboxForm.hidden));
    if (!bboxForm.hidden) bboxInput.focus();
    else say(null);
  });
  bboxForm.addEventListener("submit", (e) => {
    e.preventDefault();
    try {
      setBox(parseBbox(bboxInput.value));
    } catch (err) {
      say(err instanceof FileProblem ? err.message : "Enter four numbers: west, south, east, north.");
      bboxInput.focus();
    }
  });

  // --- Upload file ---
  fileBtn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    fileInput.value = ""; // the same file can be chosen again
    if (!file) return;
    say("Reading file…", "info");
    try {
      const { geometry, count, boxOnly } = areaFromGeoJSON(await readFile(file));
      const text = boxOnly ? `File: ${file.name} · box of its points or lines` : `File: ${file.name} · ${count} ${count === 1 ? "area" : "areas"}`;
      choose(geometry, text, { file: true, note: boxOnly ? "This file has only points or lines: using their bounding box." : null });
    } catch (err) {
      say(err instanceof FileProblem ? err.message : "This file could not be read.");
    }
  });

  // --- Draw box: the drawer steps aside, a drag on the map draws a rectangle, Esc cancels ---
  const hint = h("div", { class: "draw-hint", hidden: true }, "Drag on the map to draw a box. Esc cancels.");
  mapEl.parentElement.append(hint);
  function setSketch(box) {
    const data = box ? { type: "Feature", properties: {}, geometry: boxPolygon(box) } : { type: "FeatureCollection", features: [] };
    const source = maplibre.getSource("draw-box");
    if (source) return source.setData(data);
    maplibre.addSource("draw-box", { type: "geojson", data });
    maplibre.addLayer({ id: "draw-box-fill", type: "fill", source: "draw-box", paint: { "fill-color": "#ffffff", "fill-opacity": 0.18 } });
    maplibre.addLayer({ id: "draw-box-casing", type: "line", source: "draw-box", paint: { "line-color": "#ffffff", "line-width": 4 } });
    maplibre.addLayer({ id: "draw-box-line", type: "line", source: "draw-box", paint: { "line-color": "#0a0a0a", "line-width": 1.8, "line-dasharray": [3, 2] } });
  }
  const lngLat = (e) => {
    const r = mapEl.getBoundingClientRect();
    return maplibre.unproject([e.clientX - r.left, e.clientY - r.top]);
  };
  const boxOf = (a, b) => [Math.min(a.lng, b.lng), Math.min(a.lat, b.lat), Math.max(a.lng, b.lng), Math.max(a.lat, b.lat)];

  function onDown(e) {
    if (e.button !== 0 || e.target.closest(".maplibregl-ctrl")) return;
    e.preventDefault();
    e.stopPropagation(); // the map does not pan, and sees no click
    drawing.start = lngLat(e);
    drawing.startPx = [e.clientX, e.clientY];
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }
  function onMove(e) {
    setSketch(boxOf(drawing.start, lngLat(e)));
  }
  function onUp(e) {
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
    if (Math.hypot(e.clientX - drawing.startPx[0], e.clientY - drawing.startPx[1]) < 6) { // a click, not a drag: keep drawing
      setSketch(null);
      return;
    }
    const box = boxOf(drawing.start, lngLat(e)).map(round4);
    stopDrawing(true);
    if (box[0] < box[2] && box[1] < box[3]) setBox(box);
  }
  function onKey(e) {
    if (e.key !== "Escape") return;
    e.preventDefault();
    e.stopPropagation();
    stopDrawing(true);
  }
  function stopDrawing(restore) {
    if (!drawing) return;
    mapEl.removeEventListener("mousedown", onDown, true);
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
    document.removeEventListener("keydown", onKey, true);
    mapEl.classList.remove("drawing");
    hint.hidden = true;
    setSketch(null);
    drawing = null;
    drawBtn.setAttribute("aria-pressed", "false");
    if (restore) setTimeout(showDrawer, 60); // after the mouse-up has passed, so nothing closes it again
  }
  drawBtn.addEventListener("click", () => {
    if (drawing) return;
    say(null);
    drawing = { start: null, startPx: null };
    hideDrawer();
    mapEl.classList.add("drawing");
    hint.hidden = false;
    drawBtn.setAttribute("aria-pressed", "true");
    mapEl.addEventListener("mousedown", onDown, true);
    document.addEventListener("keydown", onKey, true);
  });

  // --- Clear, and following the selection from outside (the "Filtered … Clear" line, a new site, a link) ---
  clearBtn.addEventListener("click", () => setArea(null));
  onSelectionChange(({ area }) => {
    if (!area) {
      label = null;
      fromFile = false;
      say(null);
    }
    showStatus();
  });

  return {
    /** The open site changed (or the intro is shown): forget notes about the old one. */
    setSite() {
      stopDrawing(false);
      say(null);
      bboxForm.hidden = true;
      typeBtn.setAttribute("aria-expanded", "false");
    },
    /** Link parameter bbox=w,s,e,n (rounded to 4 decimals), plus area=file when the box came from an uploaded file. */
    toParams(params) {
      const { area } = getSelection();
      if (!area) return;
      params.set("bbox", geometryBox(area).map(round4).join(","));
      if (fromFile) params.set("area", "file");
    },
    /** From a link: a valid bbox is selected, anything else is ignored. */
    fromParams(params, { zoom = true } = {}) {
      const raw = params.get("bbox");
      if (!raw) return;
      try {
        const b = parseBbox(raw);
        if (params.get("area") === "file") choose(boxPolygon(b), "Box of the uploaded file", { zoom, file: true });
        else setBox(b, { zoom });
      } catch {} // a bad value is ignored
    },
  };
}
