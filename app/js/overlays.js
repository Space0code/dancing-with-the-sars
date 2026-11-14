// Written by Claude. Layer control for the site's radar pictures: on/off and opacity per picture, with its caption.
import { h, formatDate } from "./format.js";

export function renderLayerControl(layers, map) {
  const items = layers.length
    ? layers.map((l) => {
        const check = h("input", { type: "checkbox", onchange: (e) => map.setOverlayVisible(l.id, e.target.checked) });
        const opacity = h("input", {
          type: "range", min: "0", max: "100", value: "70", "aria-label": `Opacity of ${l.title}`,
          oninput: (e) => map.setOverlayOpacity(l.id, e.target.value / 100),
        });
        return h("div", { class: "layer-item" },
          h("label", {}, check, l.date ? `${l.title} · ${formatDate(l.date)}` : l.title),
          opacity,
          l.caption ? h("p", {}, l.caption) : null
        );
      })
    : [h("p", { class: "layer-item" }, "This site has no radar pictures yet.")];
  document.getElementById("layer-list").replaceChildren(...items);
  document.getElementById("layers").open = false;
}
