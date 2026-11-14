// Written by Claude. Before/after divider over the map: a full-height line with a handle and a date tag on each side.
// Drag it (mouse or touch) or use the arrow keys on the handle; the map itself still pans and zooms around it.
import { h } from "./format.js";

/** `onMove()` runs whenever the line moves. Returns {show(on), x(), setLabels(left, right)}. */
export function createSwipe(container, { onMove }) {
  const left = h("span", { class: "swipe-tag left" });
  const right = h("span", { class: "swipe-tag right" });
  const handle = h("div", {
    class: "swipe-handle", tabindex: "0", role: "slider", "aria-label": "Move the line between before and after",
    "aria-valuemin": "0", "aria-valuemax": "100",
  }, h("span", { "aria-hidden": "true" }, "◂▸"));
  const line = h("div", { class: "swipe-line", hidden: true }, h("div", { class: "swipe-grip" }), handle, left, right);
  container.append(line);

  let frac = 0.5; // position as a fraction of the map width, so a resize keeps it in place
  const width = () => container.clientWidth || 1;

  function set(next) {
    frac = Math.min(1, Math.max(0, next));
    line.style.left = `${frac * 100}%`;
    handle.setAttribute("aria-valuenow", String(Math.round(frac * 100)));
    handle.setAttribute("aria-valuetext", `${Math.round(frac * 100)}% before, ${Math.round(100 - frac * 100)}% after`);
    placeTags();
    onMove();
  }
  // Each tag sits beside the line on its own side; near an edge it slides inward so its date stays readable.
  function placeTags() {
    const x = frac * width();
    left.style.transform = `translateX(${Math.max(0, left.offsetWidth + 12 - x)}px)`;
    right.style.transform = `translateX(${-Math.max(0, right.offsetWidth + 12 - (width() - x))}px)`;
  }
  const fromEvent = (e) => set((e.clientX - container.getBoundingClientRect().left) / width());

  line.addEventListener("pointerdown", (e) => {
    if (!e.target.closest(".swipe-grip, .swipe-handle")) return;
    line.setPointerCapture(e.pointerId);
    line.classList.add("dragging");
    e.preventDefault();
  });
  line.addEventListener("pointermove", (e) => line.classList.contains("dragging") && fromEvent(e));
  for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) line.addEventListener(type, () => line.classList.remove("dragging"));
  handle.addEventListener("keydown", (e) => {
    const step = { ArrowLeft: -0.05, ArrowDown: -0.05, ArrowRight: 0.05, ArrowUp: 0.05 }[e.key];
    if (step) set(frac + step);
    else if (e.key === "Home") set(0);
    else if (e.key === "End") set(1);
    else return;
    e.preventDefault();
    e.stopPropagation(); // the timeline also listens to arrow keys
  });

  return {
    show(on) {
      line.hidden = !on;
      if (on) set(frac);
    },
    /** The line's position in px from the map's left edge. */
    x: () => frac * width(),
    setLabels(leftText, rightText) {
      left.textContent = leftText;
      right.textContent = rightText;
      if (!line.hidden) placeTags();
    },
  };
}
