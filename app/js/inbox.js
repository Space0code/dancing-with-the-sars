// Written by Claude. Review inbox: a sortable, filterable list of the open site's changes (the "Changes" tab in the side panel).
// Filtering on the map is a MapLibre expression (mapFilter), so the map never loops over features in JS. Rows render in chunks.
import { h, VERDICTS, verdictKey, changeLabel, confidenceLabel, formatDate, formatArea } from "./format.js";

const CHUNK = 80; // rows per render step; more load as the list is scrolled
const CONCERN_ORDER = ["high_concern", "review", "none", "expected"]; // what a regulator should look at first
const SHORT_KIND = { // short names for chips and rows; the card has the full wording
  clearing: "Forest clearing", structure: "New building", earthworks: "Earth moved",
  ground_motion: "Ground movement", fire: "Burned area", other: "Other change",
};
const kindName = (type) => SHORT_KIND[type] ?? changeLabel(type);
const SORTS = {
  concern: { label: "Concern", cmp: (a, b) => concernRank(a) - concernRank(b) || b.properties.area_ha - a.properties.area_ha },
  size: { label: "Size (largest first)", cmp: (a, b) => b.properties.area_ha - a.properties.area_ha },
  date: { label: "Date (newest first)", cmp: (a, b) => b.properties.first_date.localeCompare(a.properties.first_date) },
};
const concernRank = (f) => CONCERN_ORDER.indexOf(verdictKey(f.properties.verdict));

/** `onOpen(feature)`: a row was clicked. `onFilters()`: the user changed a filter. */
export function createInbox({ onOpen, onFilters }) {
  const $ = (id) => document.getElementById(id);
  const root = $("inbox");

  let all = [];
  let date = "9999-12-31";
  let verdicts = new Set(); // empty set = no filter
  let kinds = new Set();
  let sortKey = "concern";
  let selectedId = null;
  let matching = []; // features passing date + filters (unsorted until rendered)
  let sorted = null; // `matching`, sorted; null = needs sorting
  let rendered = 0;
  let stale = true; // list DOM is out of date (it is only rebuilt while the tab is visible)

  const verdictChips = h("div", { class: "chips", role: "group", "aria-label": "Filter by label" });
  const kindChips = h("div", { class: "chips", role: "group", "aria-label": "Filter by kind of change" });
  const sortSelect = h("select", { id: "inbox-sort", "aria-label": "Sort changes by", onchange: (e) => { sortKey = e.target.value; sorted = null; stale = true; render(); } },
    Object.entries(SORTS).map(([key, s]) => h("option", { value: key }, s.label)));
  const clearBtn = h("button", { type: "button", class: "clear-filters", hidden: true, onclick: () => { verdicts.clear(); kinds.clear(); filtersChanged(); } }, "Clear filters");
  const summary = h("p", { class: "inbox-summary", "aria-live": "polite" });
  const list = h("ul", { class: "inbox-list", "aria-label": "Changes" });
  root.replaceChildren(
    h("div", { class: "inbox-controls" },
      h("div", { class: "inbox-top" }, h("label", { class: "sort" }, "Sort by ", sortSelect), clearBtn),
      verdictChips, kindChips, summary),
    list
  );

  // --- tabs ---
  const tabs = { details: $("tab-details"), inbox: $("tab-inbox") };
  const views = { details: $("details-view"), inbox: root };
  function showTab(name) {
    for (const key of Object.keys(tabs)) {
      tabs[key].setAttribute("aria-selected", String(key === name));
      views[key].hidden = key !== name;
    }
    if (name === "inbox") render();
  }
  for (const [name, button] of Object.entries(tabs)) button.addEventListener("click", () => showTab(name));

  // --- filtering ---
  const verdictOf = (f) => verdictKey(f.properties.verdict);
  const passes = (f) =>
    f.properties.first_date <= date &&
    (!verdicts.size || verdicts.has(verdictOf(f))) &&
    (!kinds.size || kinds.has(f.properties.type));

  function recompute() {
    matching = all.filter(passes);
    sorted = null;
    stale = true;
    $("inbox-count").textContent = String(matching.length);
    clearBtn.hidden = !(verdicts.size || kinds.size);
  }

  function filtersChanged() {
    syncChips();
    recompute();
    render();
    onFilters();
  }

  function chip(label, count, swatch, pressed, onToggle) {
    return h("button", { type: "button", class: "chip", "aria-pressed": String(pressed), onclick: onToggle },
      swatch ? h("span", { class: "swatch", style: `background:${swatch}` }) : null, `${label} `, h("span", { class: "n" }, String(count)));
  }
  function syncChips() {
    const toggle = (set, key) => () => { set.has(key) ? set.delete(key) : set.add(key); filtersChanged(); };
    const count = (fn) => all.filter(fn).length;
    const present = CONCERN_ORDER.filter((key) => verdicts.has(key) || all.some((f) => verdictOf(f) === key)); // no chips for labels this site doesn't have
    verdictChips.replaceChildren(...present.map((key) =>
      chip(VERDICTS[key].label, count((f) => verdictOf(f) === key), VERDICTS[key].color, verdicts.has(key), toggle(verdicts, key))));
    const types = [...new Set(all.map((f) => f.properties.type))];
    kindChips.replaceChildren(...types.map((type) =>
      chip(kindName(type), count((f) => f.properties.type === type), null, kinds.has(type), toggle(kinds, type))));
  }

  // --- rendering (chunked) ---
  function row(f) {
    const p = f.properties;
    const key = verdictOf(f);
    return h("li", {},
      h("button", { type: "button", class: "row", "data-id": p.id, "aria-current": p.id === selectedId ? "true" : null, onclick: () => onOpen(f) },
        h("span", { class: "swatch", style: `background:${VERDICTS[key].color}`, "aria-hidden": "true" }),
        h("span", { class: "row-main" },
          h("span", { class: "row-title" }, kindName(p.type), h("span", { class: "row-size" }, formatArea(p.area_ha))),
          h("span", { class: "row-sub" }, `${VERDICTS[key].label} · ${formatDate(p.first_date)} · ${confidenceLabel(p.confidence)} confidence`))));
  }

  function appendChunk() {
    const next = sorted.slice(rendered, rendered + CHUNK);
    list.append(...next.map(row));
    rendered += next.length;
  }

  function render() {
    if (root.hidden) return; // rebuilt when the tab opens
    if (!stale) return;
    sorted ??= matching.slice().sort(SORTS[sortKey].cmp);
    list.replaceChildren();
    rendered = 0;
    if (sorted.length) appendChunk();
    else list.append(h("li", { class: "empty" }, all.length ? "No changes match these filters at this date." : "No changes at this site."));
    summary.textContent = `${matching.length} of ${all.length} changes`;
    stale = false;
  }

  list.addEventListener("scroll", () => {
    if (sorted && rendered < sorted.length && list.scrollTop + list.clientHeight > list.scrollHeight - 200) appendChunk();
  });

  return {
    /** Load a site's changes and reset filters. */
    setSite(features) {
      all = features;
      verdicts.clear();
      kinds.clear();
      selectedId = null;
      syncChips();
      recompute();
      render();
    },
    setDate(iso) {
      date = iso;
      recompute();
      render();
    },
    /** Mark one change's row (or none) and bring it into view. */
    setSelected(id) {
      selectedId = id;
      for (const el of list.querySelectorAll("[aria-current]")) el.removeAttribute("aria-current");
      if (!id || !sorted) return;
      const index = sorted.findIndex((f) => f.properties.id === id);
      if (index < 0) return;
      while (rendered <= index) appendChunk();
      const el = list.querySelector(`[data-id="${CSS.escape(id)}"]`);
      el?.setAttribute("aria-current", "true");
      if (!root.hidden) el?.scrollIntoView({ block: "nearest" });
    },
    showTab,
    /** MapLibre filter expression for the user's filters (the date is filtered separately), or null. */
    mapFilter() {
      const parts = [];
      if (verdicts.size) parts.push(["in", ["coalesce", ["get", "verdict"], "none"], ["literal", [...verdicts]]]);
      if (kinds.size) parts.push(["in", ["get", "type"], ["literal", [...kinds]]]);
      return parts.length ? ["all", ...parts] : null;
    },
    /** Count and total area of the changes passing date + filters. */
    stats() {
      return { count: matching.length, ha: matching.reduce((sum, f) => sum + f.properties.area_ha, 0) };
    },
  };
}
