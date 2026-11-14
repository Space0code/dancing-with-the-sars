// Written by Claude. Layer control for the site's radar pictures: on/off and opacity per picture, with its caption.
import { h, formatDate } from "./format.js";

const LONG_CAPTION = 100; // characters

export function renderLayerControl(layers, map) {
  const items = layers.length
    ? layers.map((l) => {
        const check = h("input", { type: "checkbox", onchange: (e) => map.setOverlayVisible(l.id, e.target.checked) });
        const opacity = h("input", {
          type: "range", min: "0", max: "100", value: "70", "aria-label": `Opacity of ${l.title}`,
          oninput: (e) => map.setOverlayOpacity(l.id, e.target.value / 100),
        });
        const shown = l.date && !l.title.includes(l.date.slice(0, 4)); // a title naming its dates ("25 Jun to 19 Jul 2026") needs no extra one
        const long = l.caption && l.caption.length > LONG_CAPTION; // real captions explain the colors: keep them one click away
        return h("div", { class: "layer-item" },
          h("label", {}, check, shown ? `${l.title} · ${formatDate(l.date)}` : l.title),
          opacity,
          !l.caption ? null : long ? h("details", { class: "layer-info" }, h("summary", {}, "What am I looking at?"), h("p", {}, l.caption)) : h("p", {}, l.caption)
        );
      })
    : [h("p", { class: "layer-item" }, "This site has no radar pictures yet.")];
  document.getElementById("layer-list").replaceChildren(...items);
  document.getElementById("layers").open = false;
}
