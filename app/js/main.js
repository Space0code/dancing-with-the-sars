// Written by Claude. Wires the intro, site switcher, map, the big picture (Radar / Satellite, swipe), legend, timeline, side panel, explainer and tour.
import { APP, VERDICTS, setVerdictColors, runningTotal, h } from "./format.js";
import { loadSites, loadSite, loadJson } from "./data.js";
import { createChangeMap } from "./map.js";
import { createTimeline } from "./timeline.js";
import { renderIntro, renderStory, setStoryDate, showCard, showHint } from "./panel.js";
import { createInbox } from "./inbox.js";
import { createPicture } from "./picture.js";
import { createTour } from "./tour.js";

const $ = (id) => document.getElementById(id);

function showError(message, isNotice = false) {
  const box = $("map-error");
  box.textContent = message;
  box.classList.toggle("notice", isNotice);
  box.hidden = false;
}

function renderLegend() {
  $("legend").replaceChildren(
    ...Object.values(VERDICTS).map((v) =>
      h("li", {}, h("span", { class: "swatch", style: `background:${v.color}` }), v.label)
    )
  );
}

// Phones: the legend and the picture's caption fold behind small buttons so most of the map stays visible.
function wireFolds() {
  const fold = (btn, box) =>
    btn.addEventListener("click", () => btn.setAttribute("aria-expanded", String(box.classList.toggle("open"))));
  fold($("legend-btn"), $("legend-box"));
  fold($("caption-btn"), $("view-caption"));
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
  const matching = features.filter((f) => f.properties.verdict === step.change_verdict);
  return matching.sort((a, b) => b.properties.area_ha - a.properties.area_ha)[0] ?? null;
}

function setupExplainer() {
  const dialog = $("explainer");
  $("explain-btn").addEventListener("click", () => dialog.showModal());
  dialog.querySelector(".close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (e) => e.target === dialog && dialog.close()); // a click on the backdrop closes it
}

async function main() {
  document.title = $("app-name").textContent = APP.name;
  $("app-pitch").textContent = APP.pitch;
  setVerdictColors();
  renderLegend();
  wireFolds();
  setupExplainer();
  if (!window.maplibregl) return showError("The map library could not be loaded. Check your internet connection and reload.");

  const [allSites, tourData] = await Promise.all([loadSites(), loadJson("tour.json").catch(() => ({ steps: [] }))]);
  const sites = allSites.filter((s) => s.ready && !s.hidden); // the only sites the menu, the intro and the tour know
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
      if (selectedId) params.set("change", selectedId);
      try {
        history.replaceState(null, "", `${location.pathname}${location.search}#${params}`);
      } catch {} // Safari refuses more than ~100 calls in 30 s: the link just stays at its last state
    }, 250);
  }

  function select(feature) {
    if (feature) setOverlay(true);
    selectedId = feature ? feature.properties.id : null;
    writeHash();
    map.select(feature);
    inbox.setSelected(feature ? feature.properties.id : null);
    if (feature) {
      showCard(feature, current, () => select(null));
      inbox.showTab("details");
    } else showHint();
  }
  const map = createChangeMap($("map"), { onSelect: select, bounds: overview });
  await map.ready;

  // Play and the slider follow the open view: radar pictures in Radar, colour photos in Satellite.
  const syncStops = () => timeline.setStops(picture.view === "radar" ? null : picture.stops());
  const picture = createPicture(map, document.querySelector(".map-wrap"), { onView: syncStops });

  const refreshTotal = () => {
    const { count, ha } = inbox.stats(); // follows the date and the inbox filters
    timeline.setTotal(runningTotal(count, ha));
  };
  const inbox = createInbox({
    onOpen(feature) {
      map.focus(feature, tourRoom());
      select(feature);
    },
    onFilters() {
      map.setExtraFilter(inbox.mapFilter());
      refreshTotal();
    },
  });
  const timeline = createTimeline({
    onDate(iso) {
      map.setDate(iso);
      picture.setDate(iso);
      inbox.setDate(iso);
      setStoryDate(iso);
      refreshTotal();
      lastDate = iso;
      writeHash();
    },
  });

  const tour = createTour(tourData.steps ?? [], sites, {
    async runStep(step) {
      if (current?.site.id !== step.site) await openSite(step.site);
      const feature = findStepChange(current.changes.features, step);
      const date = step.date ?? (feature ? feature.properties.last_date : current.site.time_range[1]);
      if (step.play_to) timeline.playBetween(date, step.play_to, step.note ?? "");
      else timeline.goTo(date, step.note ?? "");
      if (feature) {
        select(feature);
        map.focus(feature, tourRoom());
      } else {
        select(null);
        map.view(current.site, tourRoom());
      }
    },
  });
  $("tour-btn").addEventListener("click", () => tour.start());

  // Phones: the tour docks at the top of the bottom sheet. Desktop: it floats over the map, and the camera leaves room for it.
  const phone = matchMedia("(max-width: 760px)");
  const placeTour = () => (phone.matches ? $("panel").prepend($("tour")) : document.querySelector(".map-wrap").append($("tour")));
  placeTour();
  phone.addEventListener("change", placeTour);
  const tourRoom = () => (tour.active && !phone.matches ? $("tour").offsetHeight + 30 : 0);

  function showIntro() {
    current = null;
    lastDate = null;
    selectedId = null;
    $("map-error").hidden = true;
    $("site").value = "";
    $("fake-badge").hidden = true;
    history.replaceState(null, "", location.pathname + location.search);
    renderIntro(sites, { onPick: (id) => openSite(id).catch((err) => showError(err.message)), onTour: () => tour.start() });
    inbox.setSite([]); // no site, no list: the tabs hide and the Details view shows the intro
    inbox.showTab("details");
    $("panel-tabs").hidden = true;
    picture.setSite(null);
    map.showOverview(overview);
    timeline.clear();
  }

  async function openSite(id) {
    const site = sites.find((s) => s.id === id);
    if (!site) return;
    $("map-error").hidden = true;
    $("site").value = site.id;
    $("fake-badge").hidden = !site.fixture;
    $("panel-tabs").hidden = false;
    history.replaceState(null, "", `#site=${site.id}`);
    clearTimeout(hashTimer); // a pending write still describes the old site: drop it, and write nothing while this one loads
    selectedId = null;
    lastDate = null;
    loading = true;
    try {
      current = await loadSite(site);
      renderStory(current.story, current.base); // first: it changes the map's size on phones
      showHint();
      inbox.setSite(current.changes.features);
      map.setExtraFilter(null);
      map.showSite(site, current.changes, current.stages);
      picture.setSite(current);
      timeline.setRange(site, current.changes.features, current.story?.events);
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
    if (!sites.some((s) => s.id === id)) return false;
    const date = /^\d{4}-\d{2}-\d{2}$/.test(params.get("date") ?? "") ? params.get("date") : null; // anything else is ignored
    if (current?.site.id !== id) {
      tour.end();
      await openSite(id);
    }
    if (date) timeline.goTo(date);
    const feature = current.changes.features.find((f) => f.properties.id === params.get("change"));
    if (feature) {
      if (!date) timeline.goTo(feature.properties.last_date); // a hand-made link without a date: show the change as it stands
      map.focus(feature, tourRoom());
      select(feature);
    } else if (selectedId) select(null);
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
