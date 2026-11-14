// Written by Claude. Guided tour: steps from tour.json (text + site + slider date + optional change to open).
// Steps whose site is not ready are skipped; steps on a fake site only run while no real step is ready.
import { h } from "./format.js";

export function createTour(steps, sites, { runStep, onEnd }) {
  const box = document.getElementById("tour");
  const byId = new Map(sites.map((s) => [s.id, s]));
  const ready = (step) => byId.get(step.site)?.ready === true;
  const fake = (step) => byId.get(step.site)?.fixture === true;
  let list = [];
  let index = 0;
  let busy = false;

  function playable() {
    const real = steps.filter((s) => ready(s) && !fake(s));
    return real.length ? real : steps.filter((s) => ready(s) && fake(s));
  }

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
    list = playable();
    box.hidden = false;
    if (!list.length) {
      box.replaceChildren(h("p", {}, "The tour starts once a site is ready."), h("button", { type: "button", onclick: end }, "Close"));
      return;
    }
    go(0);
  }

  function end() {
    if (box.hidden) return;
    box.hidden = true;
    onEnd?.();
  }

  document.addEventListener("keydown", (e) => e.key === "Escape" && !box.hidden && !document.querySelector("dialog[open]") && end());

  return { start, end, get active() { return !box.hidden; } };
}
