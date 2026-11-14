// Written by Claude. Wires the intro, site switcher, map, the big picture (Radar / Satellite, swipe), legend, timeline, drawer and tour.
import { APP, VERDICTS, setVerdictColors, runningTotal, changeLabel, h } from "./format.js";
import { loadSites, loadSite, loadJson } from "./data.js";
import { createChangeMap } from "./map.js";
import { createTimeline } from "./timeline.js";
import { renderIntro, renderOverview, setOverviewDate, showCard } from "./panel.js";
import { createDrawer } from "./drawer.js";
import { createInbox, kindName } from "./inbox.js";
import { createPicture } from "./picture.js";
import { createTour } from "./tour.js";
import { createRecords } from "./records.js";
import { filterChanges, getSelection, isActive, clearSelection, onSelectionChange, describeSelection } from "./selection.js";
import { createExport } from "./export.js";
import { createBasemap } from "./basemap.js";

const $ = (id) => document.getElementById(id);

function showError(message, isNotice = false) {
  const box = $("map-error");
  box.textContent = message;
  box.classList.toggle("notice", isNotice);
  box.hidden = false;
}

// One compact legend, the same for every site: the four labels, the radar tint (Radar view only) and the timeline bar.
function renderLegend() {
  const row = (swatch, text, attrs = {}) => h("li", attrs, swatch, text);
  $("legend").replaceChildren(
    ...Object.values(VERDICTS).map((v) => row(h("span", { class: "swatch", style: `background:${v.color}` }), v.label)),
    row(h("span", { class: "swatch tint" }), "Changed since first picture", { id: "legend-tint" }),
    row(h("span", { class: "swatch bar" }), "New changes on the timeline")
  );
}

function fillSiteSelect(sites) {
  $("site").replaceChildren(h("option", { value: "" }, "Choose a site…"), ...sites.map((s) => h("option", { value: s.id }, s.name)));
}

/** One box around every site, for the intro view. */
function allSitesBounds(sites) {
  const boxes = sites.map((s) => s.bbox).filter(Boolean);
  return [
    [Math.min(...boxes.map((b) => b[0])), Math.min(...boxes.map((b) => b[1]))],
    [Math.max(...boxes.map((b) => b[2])), Math.max(...boxes.map((b) => b[3]))],
  ];
}

/** A tour step opens `change` (an id) or, before ids are known, the largest change with label `change_verdict`. */
function findStepChange(features, step) {
  if (step.change) return features.find((f) => f.properties.id === step.change) ?? null;
  if (!step.change_verdict) return null;
  const largest = (list) => list.sort((a, b) => b.properties.area_ha - a.properties.area_ha)[0];
  return largest(features.filter((f) => f.properties.verdict === step.change_verdict)) ?? largest(features.slice()) ?? null;
}

async function main() {
  document.title = $("app-name").textContent = APP.name;
  $("app-pitch").textContent = APP.pitch;
  setVerdictColors();
  renderLegend();
  if (!window.maplibregl) return showError("The map library could not be loaded. Check your internet connection and reload.");

  const [allSites, tourData] = await Promise.all([loadSites(), loadJson("tour.json").catch(() => ({ steps: [] }))]);
  const sites = allSites.filter((s) => s.ready && !s.hidden); // the only sites the menu, the intro and the tour list
  const openable = allSites.filter((s) => s.ready); // hidden sites open by link
  fillSiteSelect(sites);
  const overview = allSitesBounds(sites);
  let current = null; // the open site's data, or null on the intro screen

  // "Marked areas": hides every shape over the picture. Opening a change turns them back on, so the click shows something.
  const overlayBtn = $("overlay-btn");
  function setOverlay(on) {
    overlayBtn.setAttribute("aria-pressed", String(on));
    map.setOverlay(on);
  }
  overlayBtn.addEventListener("click", () => setOverlay(overlayBtn.getAttribute("aria-pressed") !== "true"));

  // --- shareable view: #site=…&date=…&change=… follows the user (replaceState: the back button is not flooded) ---
  let selectedId = null;
  let lastDate = null; // the slider's current date
  let hashTimer = null;
  let loading = false; // a site is being opened: `current` is still the old one
  function writeHash() {
    clearTimeout(hashTimer);
    hashTimer = setTimeout(() => { // debounced: the time-lapse changes the date many times a second
      if (!current || loading) return;
      const params = new URLSearchParams({ site: current.site.id });
      if (lastDate) params.set("date", lastDate);
      if (picture.view !== "radar" && picture.stops()) params.set("view", "satellite"); // a site without photos stays in Radar
      if (selectedId) params.set("change", selectedId);
      if (basemap.value !== "satellite") params.set("base", basemap.value);
      try {
        history.replaceState(null, "", `${location.pathname}${location.search}#${params}`);
      } catch {} // Safari refuses more than ~100 calls in 30 s: the link just stays at its last state
    }, 250);
  }

  /** Select a change (its card opens in the drawer) or, with null, clear the selection (the drawer stays as it is). */
  function select(feature) {
    if (feature) setOverlay(true);
    selectedId = feature ? feature.properties.id : null;
    writeHash();
    map.select(feature);
    inbox.setSelected(selectedId);
    if (!feature) return;
    showCard(feature, current);
    drawer.setTitle(changeLabel(feature.properties.type));
    drawer.show("card");
  }
  const drawer = createDrawer({
    onShow: (view) => view === "inbox" && inbox.refresh(),
    onClose: () => select(null),
    onBack: () => {
      select(null);
      showSiteDrawer();
    },
  });
  /** The site-level view of the drawer: the overview and the list of changes. */
  function showSiteDrawer(view = drawer.lastTab) {
    if (!current) return;
    drawer.setTitle(current.site.name);
    drawer.show(view);
  }
  // A click on empty map closes whatever is open; Esc does too (before the tour's own Esc handling).
  const map = createChangeMap($("map"), { onSelect: (f) => (f ? select(f) : drawer.close()), bounds: overview });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || !drawer.mode || document.querySelector("dialog[open]")) return;
    drawer.close();
    e.preventDefault();
  });
  const room = () => ({ bottom: tourRoom(), right: Math.min(480, $("map").clientWidth * 0.4) }); // the drawer covers the right side: keep the change clear of it
  $("changes-btn").addEventListener("click", () => (drawer.mode && drawer.mode !== "card" ? drawer.close() : (select(null), showSiteDrawer())));
  await map.ready;
  const records = createRecords(map.maplibre, $("records-box"));
  const basemap = createBasemap(map, $("basemap-box"), { onChange: () => writeHash() });

  // Play and the slider follow the open view: radar pictures in Radar, colour photos in Satellite.
  const syncStops = () => {
    timeline.setStops(picture.view === "radar" ? null : picture.stops());
    $("legend-tint").hidden = picture.view !== "radar"; // the tint only exists on the radar pictures
    writeHash(); // the link carries the view
  };
  const picture = createPicture(map, document.querySelector(".map-wrap"), { onView: syncStops });

  const refreshTotal = () => {
    const { count, ha } = inbox.stats(); // follows the date and the inbox filters
    timeline.setTotal(runningTotal(count, ha));
  };
  const inbox = createInbox({
    onOpen(feature) {
      map.focus(feature, room());
      select(feature);
    },
    onFilters() {
      map.setExtraFilter(inbox.mapFilter());
      refreshTotal();
    },
    onExport: (button) => exporter.open(button),
  });
  window.parallax = { snapshot: map.snapshot }; // console access (and the browser checks) to the map picture
  const exporter = createExport({
    buttons: [$("export-btn")],
    getContext: () => current && { site: current.site, changes: inbox.rows(), selection: getSelection(), snapshot: map.snapshot, kindName },
  });

  /** Show the selection (selection.js) everywhere changes are shown or counted: map, total, overview, list. */
  function applySelection() {
    $("filter-line").hidden = !isActive();
    $("filter-text").textContent = `Filtered: ${describeSelection()}`;
    if (!current || loading) return;
    const features = filterChanges(current.changes.features);
    renderOverview(current.site, features);
    map.setShownIds(isActive() ? new Set(features.map((f) => f.properties.id)) : null);
    map.setAreaOutline(getSelection().area);
    inbox.setPool(features);
    if (selectedId && !features.some((f) => f.properties.id === selectedId)) select(null);
  }
  onSelectionChange(applySelection);
  $("filter-clear").addEventListener("click", clearSelection);
  const timeline = createTimeline({
    onDate(iso) {
      map.setDate(iso);
      picture.setDate(iso);
      records.setDate(iso);
      inbox.setDate(iso);
      setOverviewDate(iso);
      refreshTotal();
      lastDate = iso;
      writeHash();
    },
  });

  // Tour steps are the same for every site: they run on the open site, or on the first real one.
  const tour = createTour(tourData.steps ?? [], {
    async runStep(step) {
      if (!current) await openSite((sites.find((s) => !s.fixture) ?? sites[0]).id);
      const feature = findStepChange(current.changes.features, step);
      const day = (d) => ({ start: current.site.time_range[0], end: current.site.time_range[1] })[d] ?? d;
      const date = day(step.date) ?? (feature ? feature.properties.last_date : current.site.time_range[1]);
      if (step.play_to) timeline.playBetween(date, day(step.play_to), step.note ?? "");
      else timeline.goTo(date, step.note ?? "");
      if (feature) {
        select(feature);
        map.focus(feature, room());
      } else {
        select(null);
        drawer.close();
        map.view(current.site, tourRoom());
      }
    },
  });
  $("tour-btn").addEventListener("click", () => tour.start());

  // The tour floats over the map (bottom left); the camera leaves room for it.
  const tourRoom = () => (tour.active ? $("tour").offsetHeight + 30 : 0);

  function showIntro() {
    current = null;
    lastDate = null;
    selectedId = null;
    $("map-error").hidden = true;
    $("site").value = "";
    $("fake-badge").hidden = true;
    history.replaceState(null, "", location.pathname + location.search);
    drawer.close();
    clearSelection();
    $("changes-btn").hidden = true;
    $("export-btn").hidden = true;
    renderIntro(sites, { onPick: (id) => openSite(id).catch((err) => showError(err.message)), onTour: () => tour.start() });
    $("intro").hidden = false;
    inbox.setSite([]);
    picture.setSite(null);
    records.setSite(null);
    map.showOverview(overview);
    timeline.clear();
  }

  async function openSite(id) {
    const site = openable.find((s) => s.id === id);
    if (!site) return;
    $("map-error").hidden = true;
    for (const o of $("site").querySelectorAll("option[value]")) if (o.value && !sites.some((s) => s.id === o.value)) o.remove(); // a hidden site opened earlier by link
    if (!$("site").querySelector(`option[value="${site.id}"]`)) $("site").append(h("option", { value: site.id }, site.name)); // a hidden site, opened by link
    $("site").value = site.id;
    $("fake-badge").hidden = !site.fixture;
    $("intro").hidden = true;
    $("changes-btn").hidden = false;
    $("export-btn").hidden = false;
    drawer.close();
    history.replaceState(null, "", `#site=${site.id}`);
    clearTimeout(hashTimer); // a pending write still describes the old site: drop it, and write nothing while this one loads
    selectedId = null;
    lastDate = null;
    loading = true;
    try {
      clearSelection(); // a selection belongs to one site
      current = await loadSite(site);
      renderOverview(site, current.changes.features);
      inbox.setSite(current.changes.features);
      map.setExtraFilter(null);
      map.showSite(site, current.changes, current.stages);
      picture.setSite(current);
      records.setSite(current.base);
      timeline.setRange(site, current.changes.features);
      syncStops(); // a site with photos only starts in Satellite
    } finally {
      loading = false;
    }
  }

  $("site").addEventListener("change", (e) => {
    tour.end();
    const id = e.target.value;
    if (!id) return showIntro();
    openSite(id).catch((err) => showError(err.message));
  });

  /** Open the view the URL hash describes (site, then date, then change). False when it names no ready site. */
  async function applyHash() {
    const params = new URLSearchParams(location.hash.slice(1));
    const id = params.get("site");
    if (!openable.some((s) => s.id === id)) return false;
    const date = /^\d{4}-\d{2}-\d{2}$/.test(params.get("date") ?? "") ? params.get("date") : null; // anything else is ignored
    if (current?.site.id !== id) {
      tour.end();
      await openSite(id);
    }
    basemap.set(params.get("base")); // anything but "light" is the default satellite map
    const view = params.get("view");
    if (view === "radar" || view === "satellite") picture.setView(view === "satellite" ? "photo" : "radar"); // anything else is ignored; before the date, so the slider has the view's stops
    if (date) timeline.goTo(date);
    const feature = current.changes.features.find((f) => f.properties.id === params.get("change"));
    if (feature) {
      if (!date) timeline.goTo(feature.properties.last_date); // a hand-made link without a date: show the change as it stands
      map.focus(feature, room());
      select(feature);
    } else if (drawer.mode) drawer.close();
    return true;
  }
  window.addEventListener("hashchange", () => applyHash().catch((err) => showError(err.message))); // a link pasted into the same tab

  const wanted = new URLSearchParams(location.hash.slice(1)).get("site");
  if (await applyHash().catch((err) => showError(err.message))) return;
  showIntro();
  const asked = allSites.find((s) => s.id === wanted);
  if (asked) showError(`${asked.name} is not shown in this version. Pick another site or start the tour.`, true);
}

main().catch((err) => showError(err.message));
