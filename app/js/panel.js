// Written by Claude. What goes in the drawer and the start box: the intro, the site overview (computed from the changes, the
// same for every site) and the change card (the "why this label" checklist, signal chart).
import { buildChart, buildAreaChart } from "./chart.js";
import { loadJson } from "./data.js";
import { buildChecklist } from "./checklist.js";
import { h, VERDICTS, verdictKey, changeLabel, sensorLabel, formatArea, safeUrl } from "./format.js";
import { whenText, sizeText, confidenceText, seenBy } from "./seen.js";

const $ = (id) => document.getElementById(id);

let areaChart = null; // {setDate} of the open overview's graph
let overviewDate = null; // the slider date, so the graph starts at the right place

/** Move the overview graph's slider line (called on every timeline step). */
export function setOverviewDate(iso) {
  overviewDate = iso;
  areaChart?.setDate(iso);
}

const MONTH = new Intl.DateTimeFormat("en-GB", { month: "short", timeZone: "UTC" });
const YEAR = new Intl.DateTimeFormat("en-GB", { year: "numeric", timeZone: "UTC" });
/** "Apr–Oct 2026" · "Oct 2026" · "Oct 2025–Apr 2026" from two ISO dates. */
export function periodText(a, b) {
  const [da, db] = [new Date(a), new Date(b)];
  const sameYear = YEAR.format(da) === YEAR.format(db);
  const from = sameYear ? MONTH.format(da) : `${MONTH.format(da)} ${YEAR.format(da)}`;
  const to = `${MONTH.format(db)} ${YEAR.format(db)}`;
  return from === to || (sameYear && MONTH.format(da) === MONTH.format(db)) ? to : `${from}–${to}`;
}

/** Short satellite names found in the changes' `sources` (or their single `sensor`), each once, in order of appearance. */
export function sensorNames(features) {
  const names = [];
  for (const f of features) {
    for (const raw of (f.properties.sources ?? []).map((s) => s.sensor).concat(f.properties.sources?.length ? [] : [f.properties.sensor])) {
      const name = /nisar/i.test(raw) ? "NISAR" : /sentinel-1/i.test(raw) ? "Sentinel-1" : /dist-alert|optical|hls|sentinel-2/i.test(raw) ? "Optical alerts" : raw;
      if (name && !names.includes(name)) names.push(name);
    }
  }
  return names;
}

/** The site overview: one computed line, counts per label, the cumulative-area graph and the site's data notes (if any). */
export function renderOverview(site, features) {
  const box = $("overview");
  areaChart = null;
  const total = features.reduce((sum, f) => sum + f.properties.area_ha, 0);
  const first = features.map((f) => f.properties.first_date).sort()[0];
  const last = features.map((f) => f.properties.last_date).sort().at(-1);
  const line = [
    `${features.length} ${features.length === 1 ? "change" : "changes"}`,
    formatArea(total),
    first ? periodText(first, last) : null,
    sensorNames(features).join(", ") || null,
  ].filter(Boolean).join(" · ");

  const counts = Object.keys(VERDICTS)
    .map((key) => [key, features.filter((f) => verdictKey(f.properties.verdict) === key).length])
    .filter(([, n]) => n > 0);
  const countList = h("ul", { class: "label-counts" }, counts.map(([key, n]) =>
    h("li", {}, h("span", { class: "swatch", style: `background:${VERDICTS[key].color}` }), VERDICTS[key].label, h("span", { class: "n" }, String(n)))));

  const slot = h("div", { class: "area-chart-slot" });
  const built = features.length ? buildAreaChart(features, site.time_range) : null;
  if (built) {
    slot.replaceChildren(built.node);
    areaChart = built;
    built.setDate(overviewDate);
  }
  const notes = Array.isArray(site.notes) ? site.notes.filter((n) => typeof n === "string" && n) : [];
  box.replaceChildren(...[
    h("p", { class: "overview-line" }, line),
    features.length ? countList : h("p", { class: "note" }, "No changes at this site."),
    built ? h("h3", {}, "Changed area over time") : null,
    slot,
    notes.length ? h("h3", {}, "About this data") : null,
    notes.length ? h("ul", { class: "data-notes" }, notes.map((n) => h("li", {}, n))) : null,
  ].filter(Boolean)); // replaceChildren(null) would print the word "null"
}

/** The first screen, before any site is open: what the app is for, the tour, and the sites. */
export function renderIntro(sites, { onPick, onTour }) {
  const siteButton = (s) =>
    h("li", {},
      h("button", { type: "button", class: "site-btn", disabled: !s.ready, onclick: () => onPick(s.id) },
        s.name,
        s.fixture ? h("span", { class: "fake-badge" }, "Fake data") : null,
        s.ready ? null : h("span", { class: "soon" }, "coming soon")
      )
    );
  $("intro").replaceChildren(
    h("p", {}, "Pick a site to see where the land changed."),
    h("ul", { class: "site-list" }, sites.map(siteButton)),
    h("button", { type: "button", class: "primary big", onclick: onTour }, "Take the tour")
  );
}

let cardToken = 0; // guards against a slow chart arriving after another card was opened

/** Show one change. `site` is the loaded site data ({base}). */
export function showCard(feature, site) {
  const { base } = site;
  const token = ++cardToken;
  const p = feature.properties;
  const key = verdictKey(p.verdict);
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
      h("span", { class: `badge ${key}` }, VERDICTS[key].label),
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
  $("card-view").scrollTop = 0;
}
