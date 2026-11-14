// Written by Claude. Wires the site switcher, map, legend, basemap toggle, timeline and side panel together.
import { VERDICTS, setVerdictColors, runningTotal, h } from "./format.js";
import { loadSites, loadSite } from "./data.js";
import { createChangeMap } from "./map.js";
import { createTimeline } from "./timeline.js";
import { renderStory, showCard, showHint } from "./panel.js";

const $ = (id) => document.getElementById(id);

function showError(message) {
  const box = $("map-error");
  box.textContent = message;
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
    if (feature) showCard(feature, current.base, () => select(null));
    else showHint();
  }
  const map = createChangeMap($("map"), { onSelect: select });
  await map.ready;

  const timeline = createTimeline({
    onDate(iso) {
      map.setDate(iso);
      const shown = (current?.changes.features ?? []).filter((f) => f.properties.first_date <= iso);
      timeline.setTotal(runningTotal(shown.length, shown.reduce((sum, f) => sum + f.properties.area_ha, 0)));
    },
  });

  async function openSite(id) {
    const site = sites.find((s) => s.id === id && s.ready);
    if (!site) return;
    $("site").value = site.id;
    $("fake-badge").hidden = !site.fixture;
    history.replaceState(null, "", `#site=${site.id}`);
    current = await loadSite(site);
    renderStory(current.story); // first: it changes the map's size on phones
    showHint();
    map.showSite(site, current.changes);
    timeline.setRange(site.time_range, current.story?.events);
  }

  $("site").addEventListener("change", (e) => openSite(e.target.value).catch((err) => showError(err.message)));
  document.querySelectorAll('input[name="basemap"]').forEach((radio) =>
    radio.addEventListener("change", (e) => map.setBasemap(e.target.value))
  );

  const wanted = new URLSearchParams(location.hash.slice(1)).get("site");
  const first = sites.find((s) => s.id === wanted && s.ready) ?? sites.find((s) => s.ready);
  if (first) await openSite(first.id);
  else showError("No site is ready yet.");
}

main().catch((err) => showError(err.message));
