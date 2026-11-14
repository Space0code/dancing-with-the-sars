// Written by Claude. Wires the site switcher, map, legend, basemap toggle, timeline and side panel together.
import { VERDICTS, setVerdictColors, runningTotal, h } from "./format.js";
import { loadSites, loadSite } from "./data.js";
import { createChangeMap } from "./map.js";
import { createTimeline } from "./timeline.js";
import { renderStory, showCard, showHint } from "./panel.js";
import { renderLayerControl } from "./overlays.js";
import { createInbox } from "./inbox.js";

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
    ...sites.map((s) =>
      h("option", { value: s.id, disabled: !s.ready }, s.ready ? s.name : `${s.name} (coming soon)`)
    )
  );
}

async function main() {
  setVerdictColors();
  renderLegend();
  if (!window.maplibregl) return showError("The map library could not be loaded. Check your internet connection and reload.");

  const sites = await loadSites();
  fillSiteSelect(sites);
  let current = null; // the open site's data
  function select(feature) {
    map.select(feature);
    inbox.setSelected(feature ? feature.properties.id : null);
    if (feature) {
      showCard(feature, current, () => select(null));
      inbox.showTab("details");
    } else showHint();
  }
  const map = createChangeMap($("map"), { onSelect: select });
  await map.ready;

  const refreshTotal = () => {
    const { count, ha } = inbox.stats(); // follows the date and the inbox filters
    timeline.setTotal(runningTotal(count, ha));
  };
  const inbox = createInbox({
    onOpen(feature) {
      map.flyToFeature(feature);
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
    },
  });

  async function openSite(id) {
    const site = sites.find((s) => s.id === id && s.ready);
    if (!site) return;
    $("map-error").hidden = true;
    $("site").value = site.id;
    $("fake-badge").hidden = !site.fixture;
    history.replaceState(null, "", `#site=${site.id}`);
    current = await loadSite(site);
    renderStory(current.story); // first: it changes the map's size on phones
    showHint();
    inbox.setSite(current.changes.features);
    map.setExtraFilter(null);
    map.showSite(site, current.changes);
    map.setOverlays(current.base, current.layers);
    renderLayerControl(current.layers, map);
    timeline.setRange(site.time_range, current.story?.events);
  }

  $("site").addEventListener("change", (e) => openSite(e.target.value).catch((err) => showError(err.message)));
  document.querySelectorAll('input[name="basemap"]').forEach((radio) =>
    radio.addEventListener("change", (e) => map.setBasemap(e.target.value))
  );

  const wanted = new URLSearchParams(location.hash.slice(1)).get("site");
  const first = sites.find((s) => s.id === wanted && s.ready) ?? sites.find((s) => s.ready);
  if (!first) return showError("No site is ready yet.");
  await openSite(first.id);
  const asked = sites.find((s) => s.id === wanted);
  if (asked && !asked.ready) showError(`${asked.name} is coming soon. Showing ${first.name} instead.`, true);
}

main().catch((err) => showError(err.message));
