// Written by Claude. Base map switch (Satellite | Light) in the legend box. The tiles and the swap itself live in map.js (setBase);
// this file draws the two buttons and keeps the choice. The choice goes in the link as `base=light` (satellite is the default).
import { h } from "./format.js";

const BASES = [["satellite", "Satellite"], ["light", "Light"]];

/** `map` = the change map (map.js); `box` = the element the switch goes in; `onChange` is called after a user's choice. */
export function createBasemap(map, box, { onChange } = {}) {
  let current = "satellite";
  const buttons = BASES.map(([id, label]) =>
    h("button", { type: "button", role: "radio", "aria-checked": "false", onclick: () => choose(id, true) }, label));
  box.replaceChildren(h("span", { class: "basemap-label" }, "Base map"), h("div", { class: "switch", role: "radiogroup", "aria-label": "Base map" }, ...buttons));

  function choose(id, byUser = false) {
    current = BASES.some(([b]) => b === id) ? id : "satellite"; // anything unknown falls back to the default
    map.setBase(current);
    BASES.forEach(([b], i) => buttons[i].setAttribute("aria-checked", String(b === current)));
    if (byUser) onChange?.(current);
  }
  choose("satellite");

  return {
    get value() {
      return current;
    },
    /** Set the base map from a link (does not call onChange). */
    set: (id) => choose(id),
  };
}
