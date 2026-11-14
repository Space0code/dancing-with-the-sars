// Written by Claude. Before/after picture swipe: drag (mouse, touch) or use the arrow keys on the handle.
import { h } from "./format.js";

/** `before` / `after`: {src, label}. Returns a DOM element. */
export function buildSwipe(before, after) {
  const imgBefore = h("img", { src: before.src, alt: `${before.label} picture of this place`, draggable: "false" });
  const imgAfter = h("img", { src: after.src, alt: `${after.label} picture of this place`, class: "swipe-after", draggable: "false" });
  const handle = h("div", {
    class: "swipe-handle", tabindex: "0", role: "slider", "aria-label": "Compare before and after",
    "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuetext": "",
  }, h("span", { "aria-hidden": "true" }, "◂▸"));
  const frame = h("div", { class: "swipe-frame" },
    imgBefore, imgAfter,
    h("span", { class: "swipe-tag left" }, before.label),
    h("span", { class: "swipe-tag right" }, after.label),
    handle
  );
  const box = h("div", { class: "swipe" }, frame, h("p", { class: "note" }, "Drag the handle (or use the arrow keys) to compare."));

  let pos = 50;
  function set(next) {
    pos = Math.min(100, Math.max(0, next));
    imgAfter.style.clipPath = `inset(0 0 0 ${pos}%)`;
    handle.style.left = `${pos}%`;
    handle.setAttribute("aria-valuenow", String(Math.round(pos)));
    handle.setAttribute("aria-valuetext", `${Math.round(pos)}% ${before.label}, ${Math.round(100 - pos)}% ${after.label}`);
  }
  const fromEvent = (e) => {
    const r = frame.getBoundingClientRect();
    set(((e.clientX - r.left) / r.width) * 100);
  };

  frame.addEventListener("pointerdown", (e) => {
    frame.setPointerCapture(e.pointerId);
    frame.classList.add("dragging");
    fromEvent(e);
  });
  frame.addEventListener("pointermove", (e) => frame.classList.contains("dragging") && fromEvent(e));
  for (const type of ["pointerup", "pointercancel"]) frame.addEventListener(type, () => frame.classList.remove("dragging"));
  handle.addEventListener("keydown", (e) => {
    const step = { ArrowLeft: -5, ArrowDown: -5, ArrowRight: 5, ArrowUp: 5 }[e.key];
    if (step) set(pos + step);
    else if (e.key === "Home") set(0);
    else if (e.key === "End") set(100);
    else return;
    e.preventDefault();
  });

  imgBefore.addEventListener("load", () => (frame.style.aspectRatio = `${imgBefore.naturalWidth} / ${imgBefore.naturalHeight}`));
  const broken = () => box.replaceChildren(h("p", { class: "note" }, "The before and after pictures could not be loaded."));
  imgBefore.addEventListener("error", broken);
  imgAfter.addEventListener("error", broken);

  set(50);
  return box;
}
