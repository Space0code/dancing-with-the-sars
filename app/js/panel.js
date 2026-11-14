// Written by Claude. Side panel: the intro screen, the collapsible site story (with its curve) and the change card (the "why this label" checklist, signal chart).
import { buildChart, buildStoryChart } from "./chart.js";
import { loadJson } from "./data.js";
import { buildChecklist } from "./checklist.js";
import { h, APP, VERDICTS, verdictKey, changeLabel, sensorLabel, safeUrl } from "./format.js";
import { whenText, sizeText, confidenceText, seenBy } from "./seen.js";

const $ = (id) => document.getElementById(id);

let storyChart = null; // {setDate} of the open story's curve, if it has one
let storyToken = 0; // a slow chart file must not land in another site's story
let storyDate = null; // the slider date, so a chart that loads late starts at the right place

/** Move the story curve's slider line (called on every timeline step). */
export function setStoryDate(iso) {
  storyDate = iso;
  storyChart?.setDate(iso);
}

// story.chart: {title, file, note}; the file sits next to story.json and has the format of a series file.
function storyChartSlot(chart, base, token) {
  const slot = h("div", { class: "story-chart-slot" });
  loadJson(base + chart.file)
    .then((data) => {
      const built = token === storyToken && buildStoryChart(data, chart);
      if (!built) return;
      slot.replaceChildren(built.node);
      storyChart = built;
      built.setDate(storyDate);
    })
    .catch(() => token === storyToken && slot.replaceChildren(h("p", { class: "note" }, "The chart could not be loaded.")));
  return slot;
}

export function renderStory(story, base = "") {
  const box = $("story");
  const token = ++storyToken;
  storyChart = null;
  if (!story) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  box.open = true;
  const sources = (story.sources ?? []).filter((s) => safeUrl(s.url));
  const sourceLine = sources.length
    ? [h("p", { class: "sources" }, "Sources: ", sources.flatMap((s, i) => [i ? " · " : "", h("a", { href: s.url, target: "_blank", rel: "noopener" }, s.title)]))]
    : []; // an array, not null: replaceChildren(null) would print the word "null"
  const chart = story.chart?.file ? [storyChartSlot(story.chart, base, token)] : [];
  box.replaceChildren(h("summary", {}, story.headline), ...story.story.map((p) => h("p", {}, p)), ...chart, ...sourceLine);
}

/** The first screen, before any site is open: what the app is for, the tour, and the sites. */
export function renderIntro(sites, { onPick, onTour }) {
  $("story").hidden = true;
  const siteButton = (s) =>
    h("li", {},
      h("button", { type: "button", class: "site-btn", disabled: !s.ready, onclick: () => onPick(s.id) },
        s.name,
        s.fixture ? h("span", { class: "fake-badge" }, "Fake data") : null,
        s.ready ? null : h("span", { class: "soon" }, "coming soon")
      )
    );
  $("card").replaceChildren(
    h("section", { class: "intro" },
      h("p", {}, "Pick a site to see where the land changed."),
      h("ul", { class: "site-list" }, sites.map(siteButton)),
      h("button", { type: "button", class: "primary big", onclick: onTour }, "Take the tour")
    )
  );
}

export function showHint() {
  $("card").replaceChildren(h("p", { class: "hint" }, "Click a shape on the map for details."));
}

let cardToken = 0; // guards against a slow chart arriving after another card was opened

/** Show one change. `site` is the loaded site data ({base}). */
export function showCard(feature, site, onClose) {
  const { base } = site;
  const token = ++cardToken;
  const p = feature.properties;
  const key = verdictKey(p.verdict);
  $("story").open = false;
  const evidence = p.evidence ?? {};
  const seen = seenBy(p); // null when the change has no `sources`

  const chartSlot = h("div", { class: "chart-slot", id: "signal-chart" },
    h("p", { class: "note" }, evidence.series ? "Loading…" : "No signal history yet."));
  if (evidence.series) {
    loadJson(base + evidence.series)
      .then((data) => token === cardToken && chartSlot.replaceChildren(buildChart(data, p)))
      .catch(() => token === cardToken && chartSlot.replaceChildren(h("p", { class: "note" }, "The chart could not be loaded.")));
  }

  $("card").replaceChildren(
    h("article", { class: "card" },
      h("div", { class: "card-head" },
        h("span", { class: `badge ${key}` }, VERDICTS[key].label),
        h("button", { class: "close", type: "button", onclick: onClose, "aria-label": "Close details" }, "Close")
      ),
      h("h2", {}, changeLabel(p.type)),
      h("dl", { class: "facts" },
        h("dt", {}, "When"), h("dd", {}, whenText(p)),
        h("dt", {}, "Size"), h("dd", {}, sizeText(p)),
        seen ? null : h("dt", {}, "Seen by"), seen ? null : h("dd", {}, sensorLabel(p.sensor)), // one sensor: as before
        h("dt", {}, "Confidence"), h("dd", {}, confidenceText(p, site.site?.sources))
      ),
      seen ? h("h3", {}, "Seen by") : null,
      seen,
      p.explain ? h("p", { class: "explain" }, p.explain) : null,
      ...buildChecklist(p, site.site?.country),
      p.verdict ? h("p", { class: "note" }, "A label is a prompt to check, not a finding.") : null,
      h("h3", {}, "Signal over time"),
      chartSlot
    )
  );
  $("details-view").scrollTop = 0;
}
