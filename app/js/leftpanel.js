// Written by Claude. Hide / show handle of the left card. Hidden, the card slides off to the left and only its tab stays;
// the choice is kept for the session and goes in the link as `panel=0` (shown is the default).
const KEY = "parallax-panel";

export function createLeftPanel({ onChange } = {}) {
  const panel = document.getElementById("leftpanel");
  const card = document.getElementById("leftcard");
  const handle = document.getElementById("panel-toggle");
  let shown = !matchMedia("(max-width: 640px)").matches; // on a phone the card would cover the map: it starts folded
  try { const kept = sessionStorage.getItem(KEY); if (kept) shown = kept !== "0"; } catch {}

  function set(next, byUser = false) {
    shown = next;
    panel.dataset.shown = String(shown);
    card.inert = !shown; // a hidden card takes no clicks and no keyboard focus
    handle.setAttribute("aria-expanded", String(shown));
    handle.setAttribute("aria-label", shown ? "Hide legend" : "Show legend");
    try { sessionStorage.setItem(KEY, shown ? "1" : "0"); } catch {}
    if (byUser) onChange?.(shown);
  }
  handle.addEventListener("click", () => set(!shown, true)); // a button: Enter and Space click it
  set(shown);

  return {
    get shown() { return shown; },
    set: (next) => set(next),
  };
}
