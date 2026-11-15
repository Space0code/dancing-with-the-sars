// Written by Claude. Base map switch (Satellite | Light) in the legend box. The tiles and the swap itself live in map.js (setBase);
// this file draws the two buttons and keeps the choice. The choice goes in the link as `base=light` (satellite is the default).
// The Satellite view without dated photos *is* the imagery, so it fixes the base to it (lock); the user's choice comes back after.
import { h } from "./format.js";

const BASES = [["satellite", "Satellite"], ["light", "Light"]];

/** `map` = the change map (map.js); `box` = the element the switch goes in; `onChange` is called after a user's choice. */
export function createBasemap(map, box, { onChange } = {}) {
  let current = "satellite"; // the user's choice
  let locked = false;
  const buttons = BASES.map(([id, label]) =>
    h("button", { type: "button", role: "radio", "aria-checked": "false", onclick: () => choose(id, true) }, label));
  const hint = h("span", { class: "basemap-hint", hidden: true }, "The Satellite view shows this imagery");
  box.replaceChildren(h("span", { class: "basemap-label" }, "Base map"), h("div", { class: "switch", role: "radiogroup", "aria-label": "Base map" }, ...buttons), hint);

  function show() {
    const shown = locked ? "satellite" : current;
    map.setBase(shown);
    BASES.forEach(([b], i) => {
      buttons[i].setAttribute("aria-checked", String(b === shown));
      buttons[i].disabled = locked;
    });
    hint.hidden = !locked;
  }

  function choose(id, byUser = false) {
    current = BASES.some(([b]) => b === id) ? id : "satellite"; // anything unknown falls back to the default
    show();
    if (byUser) onChange?.(current);
  }
  choose("satellite");

  return {
    /** The user's choice (also while the Satellite view fixes the imagery). */
    get value() {
      return current;
    },
    /** Set the base map from a link (does not call onChange). */
    set: (id) => choose(id),
    /** true: show the imagery whatever the choice, switch disabled with a hint; false: back to the user's choice. */
    lock(on) {
      locked = Boolean(on);
      show();
    },
  };
}
