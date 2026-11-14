// Written by Claude. Wires the intro, site switcher, map, legend, basemap + year photos, timeline, side panel, explainer and tour.
import { APP, VERDICTS, setVerdictColors, runningTotal, h } from "./format.js";
import { loadSites, loadSite, loadJson } from "./data.js";
import { createChangeMap } from "./map.js";
import { createTimeline } from "./timeline.js";
import { renderIntro, renderStory, showCard, showHint } from "./panel.js";
import { renderLayerControl } from "./overlays.js";
import { createInbox } from "./inbox.js";
import { providerFor, photoFor } from "./photos.js";
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

function fillSiteSelect(sites) {
  $("site").replaceChildren(
    h("option", { value: "" }, "Choose a site…"),
    ...sites.map((s) =>
      h("option", { value: s.id, disabled: !s.ready }, s.ready ? s.name : `${s.name} (coming soon)`)
    )
  );
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
  setupExplainer();
  if (!window.maplibregl) return showError("The map library could not be loaded. Check your internet connection and reload.");

  const [sites, tourData] = await Promise.all([loadSites(), loadJson("tour.json").catch(() => ({ steps: [] }))]);
  fillSiteSelect(sites);
  const overview = allSitesBounds(sites);
  let current = null; // the open site's data, or null on the intro screen
  let basemap = "satellite";
  let year = null;

  function select(feature) {
    map.select(feature);
    inbox.setSelected(feature ? feature.properties.id : null);
    if (feature) {
      showCard(feature, current, () => select(null));
      inbox.showTab("details");
    } else showHint();
  }
  const map = createChangeMap($("map"), { onSelect: select, bounds: overview });
  await map.ready;

  // The satellite background follows the slider year: that year's photo, or today's imagery when there is none.
  function showPhoto() {
    const photo = current && year ? photoFor(providerFor(current.site), year) : null;
    map.setPhoto(photo);
    const label = $("photo-label");
    label.hidden = basemap !== "satellite";
    label.textContent = photo ? photo.label : current && year ? `Recent satellite imagery (no ${year} photo)` : "Recent satellite imagery";
  }

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
      inbox.setDate(iso);
      refreshTotal();
      const y = Number(iso.slice(0, 4));
      if (y !== year) {
        year = y;
        showPhoto();
      }
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
    year = null;
    $("map-error").hidden = true;
    $("site").value = "";
    $("fake-badge").hidden = true;
    $("layers").hidden = true;
    history.replaceState(null, "", location.pathname + location.search);
    renderIntro(sites, { onPick: (id) => openSite(id).catch((err) => showError(err.message)), onTour: () => tour.start() });
    inbox.setSite([]); // no site, no list: the tabs hide and the Details view shows the intro
    inbox.showTab("details");
    $("panel-tabs").hidden = true;
    map.setOverlays("", []);
    map.showOverview(overview);
    timeline.clear();
    showPhoto();
  }

  async function openSite(id) {
    const site = sites.find((s) => s.id === id && s.ready);
    if (!site) return;
    $("map-error").hidden = true;
    $("site").value = site.id;
    $("fake-badge").hidden = !site.fixture;
    $("layers").hidden = false;
    $("panel-tabs").hidden = false;
    history.replaceState(null, "", `#site=${site.id}`);
    current = await loadSite(site);
    year = null; // a new site can mean a new photo series, so redraw it even if the year stays the same
    renderStory(current.story); // first: it changes the map's size on phones
    showHint();
    inbox.setSite(current.changes.features);
    map.setExtraFilter(null);
    map.showSite(site, current.changes);
    map.setOverlays(current.base, current.layers);
    renderLayerControl(current.layers, map);
    timeline.setRange(site.time_range, current.story?.events);
  }

  $("site").addEventListener("change", (e) => {
    tour.end();
    const id = e.target.value;
    if (!id) return showIntro();
    openSite(id).catch((err) => showError(err.message));
  });
  document.querySelectorAll('input[name="basemap"]').forEach((radio) =>
    radio.addEventListener("change", (e) => {
      basemap = e.target.value;
      map.setBasemap(basemap);
      showPhoto();
    })
  );

  const wanted = new URLSearchParams(location.hash.slice(1)).get("site");
  const asked = sites.find((s) => s.id === wanted);
  if (asked?.ready) return openSite(asked.id);
  showIntro();
  if (asked) showError(`${asked.name} is coming soon. Pick another site or start the tour.`, true);
}

main().catch((err) => showError(err.message));
