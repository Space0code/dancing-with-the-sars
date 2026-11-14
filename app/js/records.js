// Written by Claude. "What the records say": a site's record layers (<site>/context/, kb/data-contract.md) as map
// layers the user switches on in the legend box: protected areas, zoning, registered buildings, solar plants.
// Drawn above the picture and below the change outlines; a click shows the feature's label and the layer's source.
import { h, formatDate, safeUrl } from "./format.js";
import { loadJson } from "./data.js";

// Colours stay clear of the verdict palette (blue, yellow, vermillion). `classes` = legend rows when the class occurs.
const KINDS = {
  protected: {
    by: { natura2000: "#1a7f37", pein: "#5c9e2e", other: "#7d8f3a" }, fallback: "#5c9e2e", fill: 0.18,
    classes: { natura2000: "Natura 2000", pein: "PEIN (Catalan protected area)", other: "Other protected area" },
  },
  zoning: {
    // not grey (the "not judged yet" verdict) and not purple (bare ground in the radar picture)
    by: { non_buildable: "#7f3f1f", buildable: "#8f7f5f", planned: "#17808a" }, fallback: "#8f7f5f", fill: 0.2,
    classes: { non_buildable: "Non-buildable land", buildable: "Buildable land", planned: "Planned development" },
  },
  buildings: { by: {}, fallback: "#2b2b2b", fill: 0.55, classes: {} },
  solar: { by: {}, fallback: "#8c6d1f", fill: 0.35, classes: {} },
};
const kindOf = (layer) => KINDS[layer.kind] ?? KINDS.zoning;
// A kind without classes gets one plain colour: a "match" with no cases is an invalid MapLibre expression.
const colorBy = (kind) =>
  Object.keys(kind.by).length ? ["match", ["coalesce", ["get", "class"], ""], ...Object.entries(kind.by).flat(), kind.fallback] : kind.fallback;

/** `map` = the MapLibre map; `box` = the element the Records switches go in. */
export function createRecords(map, box) {
  let layers = []; // the open site's index entries that loaded
  let token = 0;
  let year = 9999;
  let popup = null;
  let handlers = []; // [type, layer id, fn], removed with the site's layers
  const on = (type, id, fn) => {
    map.on(type, id, fn);
    handlers.push([type, id, fn]);
  };
  const ids = (layer) => [`rec-${layer.id}-fill`, `rec-${layer.id}-line`];

  function clear() {
    popup?.remove();
    for (const [type, id, fn] of handlers) map.off(type, id, fn);
    handlers = [];
    for (const layer of layers) {
      for (const id of ids(layer)) if (map.getLayer(id)) map.removeLayer(id);
      if (map.getSource(`rec-${layer.id}`)) map.removeSource(`rec-${layer.id}`);
    }
    layers = [];
    map.getCanvas().style.cursor = ""; // a pointer set by a record hover must not outlive its layer
    box.replaceChildren();
    box.hidden = true;
  }

  // Buildings registered after the slider year are drawn hollow: on the record now, not yet built then.
  const buildingFill = (kind) => ["case", [">", ["coalesce", ["get", "year"], 0], year], 0, kind.fill];

  function add(layer, data) {
    layers.push(layer); // registered first: if adding fails halfway, clear() still removes what was added
    const kind = kindOf(layer);
    const color = colorBy(kind);
    map.addSource(`rec-${layer.id}`, { type: "geojson", data });
    const [fill, line] = ids(layer);
    const hidden = { visibility: "none" };
    // "stage-fill" is the lowest change layer: records go right under it, above the picture
    map.addLayer({ id: fill, type: "fill", source: `rec-${layer.id}`, layout: hidden,
      paint: { "fill-color": color, "fill-opacity": layer.kind === "buildings" ? buildingFill(kind) : kind.fill } }, "stage-fill");
    map.addLayer({ id: line, type: "line", source: `rec-${layer.id}`, layout: hidden,
      paint: { "line-color": color, "line-width": layer.kind === "buildings" ? 1.2 : 1.8 } }, "stage-fill");
    on("mouseenter", fill, () => (map.getCanvas().style.cursor = "pointer"));
    on("mouseleave", fill, () => (map.getCanvas().style.cursor = ""));
    on("click", fill, (e) => {
      // a change outline on top wins: its card opens instead
      if (map.queryRenderedFeatures(e.point, { layers: ["changes-fill"] }).length) return;
      const f = e.features?.[0];
      if (!f) return;
      popup?.remove();
      popup = new maplibregl.Popup({ maxWidth: "280px" }).setLngLat(e.lngLat).setDOMContent(popupBody(layer, f.properties)).addTo(map);
    });
    return { layer, data };
  }

  function popupBody(layer, p) {
    const url = safeUrl(layer.url);
    return h("div", { class: "record-popup" },
      h("p", { class: "record-layer" }, layer.title),
      h("p", {}, p.label ?? "No description in the record."),
      h("p", { class: "record-source" }, "Source: ", url ? h("a", { href: url, target: "_blank", rel: "noopener" }, layer.source) : layer.source,
        layer.checked ? ` · checked ${formatDate(layer.checked)}` : ""));
  }

  function setVisible(layer, on) {
    for (const id of ids(layer)) map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
    if (!on) popup?.remove();
  }

  function swatch(color, hollow = false) {
    return h("span", { class: `rec-swatch${hollow ? " hollow" : ""}`, style: `--c:${color}`, "aria-hidden": "true" });
  }

  function control(loaded) {
    const rows = loaded.map(({ layer, data }) => {
      const kind = kindOf(layer);
      const present = new Set(data.features.map((f) => f.properties?.class).filter(Boolean));
      const keys = Object.entries(kind.classes).filter(([c]) => present.has(c))
        .map(([c, name]) => h("li", {}, swatch(kind.by[c]), name));
      if (layer.kind === "buildings") keys.push(h("li", {}, swatch(kind.fallback, true), "Registered after the slider date"));
      const input = h("input", { type: "checkbox", onchange: (e) => setVisible(layer, e.target.checked) });
      return h("li", {},
        h("label", { title: layer.note ?? "" }, input, keys.length ? null : swatch(kind.fallback), layer.title),
        keys.length ? h("ul", { class: "rec-keys" }, keys) : null);
    });
    box.replaceChildren(h("p", { class: "records-title" }, "What the records say"), h("ul", { class: "rec-list" }, rows));
    box.hidden = !rows.length;
  }

  return {
    /** Load the site's record layers, if it has any; a site without context/ shows nothing. */
    async setSite(base) {
      const mine = ++token;
      clear();
      if (!base) return;
      const index = await loadJson(`${base}context/index.json`).catch(() => null);
      if (mine !== token || !Array.isArray(index?.layers)) return;
      // a layer without an id, or with an id seen before, would clash on the map: skip it, keep the others
      const seen = new Set();
      const usable = index.layers.filter((l) => l && typeof l.id === "string" && l.id && l.file && !seen.has(l.id) && seen.add(l.id));
      const files = await Promise.all(usable.map((l) => loadJson(`${base}context/${l.file}`).then((d) => [l, d]).catch(() => [l, null])));
      if (mine !== token) return;
      // a layer that fails to draw is skipped, the others stay
      const loaded = files.filter(([, d]) => d?.features?.length).flatMap(([l, d]) => {
        try { return [add(l, d)]; } catch { return []; }
      });
      control(loaded);
    },
    setDate(iso) {
      year = Number(iso.slice(0, 4));
      for (const layer of layers) if (layer.kind === "buildings" && map.getLayer(ids(layer)[0])) map.setPaintProperty(ids(layer)[0], "fill-opacity", buildingFill(KINDS.buildings));
    },
  };
}
