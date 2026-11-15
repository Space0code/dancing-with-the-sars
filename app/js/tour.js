// Written by Claude. Guided tour: generic steps from tour.json (text, optional slider dates, optional change to open), run on the open site.
import { h } from "./format.js";

export function createTour(steps, { runStep, onEnd }) {
  const box = document.getElementById("tour");
  let list = [];
  let index = 0;
  let busy = false;
  // --tour-h: the box's height, so the left card and the drawer can stop above it on phones (css/style.css)
  new ResizeObserver(() => box.offsetHeight && document.documentElement.style.setProperty("--tour-h", `${box.offsetHeight}px`)).observe(box);

  function render() {
    const step = list[index];
    const last = index === list.length - 1;
    box.replaceChildren(
      h("div", { class: "tour-head" },
        h("span", { class: "tour-count" }, `Tour · ${index + 1} of ${list.length}`),
        h("button", { class: "close", type: "button", onclick: end, "aria-label": "End the tour" }, "End tour")
      ),
      h("h2", {}, step.title),
      h("p", {}, step.text),
      h("div", { class: "tour-nav" },
        h("button", { type: "button", disabled: index === 0 || busy, onclick: () => go(index - 1) }, "Back"),
        h("button", { class: "primary", type: "button", disabled: busy, onclick: () => (last ? end() : go(index + 1)) }, last ? "Finish" : "Next")
      )
    );
  }

  async function go(n) {
    index = n;
    busy = true; // the buttons wait for the map, so quick clicks can't run two steps at once
    render();
    try {
      await runStep(list[index]);
    } finally {
      busy = false;
      if (!box.hidden) render();
    }
  }

  function start() {
    list = steps;
    box.hidden = false;
    if (!list.length) {
      box.replaceChildren(h("p", {}, "No tour yet."), h("button", { type: "button", onclick: end }, "Close"));
      return;
    }
    go(0);
  }

  function end() {
    if (box.hidden) return;
    box.hidden = true;
    onEnd?.();
  }

  document.addEventListener("keydown", (e) => e.key === "Escape" && !e.defaultPrevented && !box.hidden && end());

  return { start, end, get active() { return !box.hidden; } };
}
