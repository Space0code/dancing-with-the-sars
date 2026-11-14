// Written by Claude. The drawer over the right side of the map. It is closed by default (the map has the whole width) and
// shows one of three views: the site's overview ("story"), the list of changes ("inbox"), or one change's card ("card").
// Closes with its X button, with Esc (main.js) and with a click on empty map (main.js).

/** `onClose()`: the drawer was closed. `onBack()`: the card's "back to the list" was pressed. `onShow(view)`: a view became visible. */
export function createDrawer({ onClose, onBack, onShow }) {
  const $ = (id) => document.getElementById(id);
  const el = $("drawer");
  const views = { story: $("story-view"), inbox: $("inbox"), card: $("card-view") };
  const tabs = { story: $("tab-story"), inbox: $("tab-inbox") };
  let mode = null; // the open view, or null when closed
  let lastTab = "inbox"; // what "back" returns to

  function show(view) {
    mode = view;
    if (view !== "card") lastTab = view;
    el.inert = false;
    el.classList.add("open");
    el.parentElement.classList.add("drawer-open");
    for (const [key, node] of Object.entries(views)) node.hidden = key !== view;
    for (const [key, tab] of Object.entries(tabs)) tab.setAttribute("aria-selected", String(key === view));
    $("drawer-tabs").hidden = view === "card";
    $("drawer-back").hidden = view !== "card";
    views[view].scrollTop = 0;
    onShow?.(view);
  }

  function close() {
    if (!mode) return;
    mode = null;
    el.classList.remove("open");
    el.inert = true; // out of the tab order while hidden
    el.parentElement.classList.remove("drawer-open");
    onClose?.();
  }

  for (const [key, tab] of Object.entries(tabs)) tab.addEventListener("click", () => show(key));
  $("drawer-close").addEventListener("click", close);
  $("drawer-back").addEventListener("click", () => onBack?.());
  el.inert = true;

  return {
    show,
    close,
    get mode() { return mode; },
    get lastTab() { return lastTab; },
    setTitle(text) { $("drawer-title").textContent = text; },
    /** Hide the Story tab (a site without a story) */
    setTabAvailable(view, available) { tabs[view].hidden = !available; },
  };
}
