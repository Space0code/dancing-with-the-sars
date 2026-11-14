// Written by Claude. Side panel: the intro screen, the collapsible site story and the change card (reasons, before/after swipe, signal chart).
import { buildChart } from "./chart.js";
import { buildSwipe } from "./swipe.js";
import { loadJson } from "./data.js";
import { h, APP, VERDICTS, verdictKey, changeLabel, confidenceLabel, sensorLabel, formatDate, formatArea, safeUrl } from "./format.js";

const $ = (id) => document.getElementById(id);

const EFFECT = {
  raises: { mark: "▲", text: "Raises concern" },
  lowers: { mark: "▼", text: "Lowers concern" },
  neutral: { mark: "●", text: "Neutral" },
};

export function renderStory(story) {
  const box = $("story");
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
  box.replaceChildren(h("summary", {}, story.headline), ...story.story.map((p) => h("p", {}, p)), ...sourceLine);
}

function when(p) {
  return p.first_date === p.last_date ? formatDate(p.first_date) : `${formatDate(p.first_date)} to ${formatDate(p.last_date)}`;
}

function reasonItem(r) {
  const effect = EFFECT[r.effect] ?? EFFECT.neutral;
  const url = safeUrl(r.url);
  return h("li", {},
    h("span", { class: `mark ${r.effect}`, title: effect.text, role: "img", "aria-label": effect.text }, effect.mark),
    h("div", {}, r.text, h("cite", {}, "Source: ", url ? h("a", { href: url, target: "_blank", rel: "noopener" }, r.source) : r.source))
  );
}

// Picture dates: evidence.before_date / after_date when the exporter sets them, else the dates of the site's radar pictures (layers.json).
function evidenceBlock(evidence, base, layers) {
  const date = (id) => layers.find((l) => l.id === id)?.date;
  const label = (name, d) => (d ? `${name} · ${formatDate(d)}` : name);
  const before = evidence.before && { src: base + evidence.before, label: label("Before", evidence.before_date ?? date("radar_before")) };
  const after = evidence.after && { src: base + evidence.after, label: label("After", evidence.after_date ?? date("radar_after")) };
  if (before && after) return buildSwipe(before, after);
  const single = before ?? after;
  if (single) return h("figure", { class: "single" }, h("img", { src: single.src, alt: `${single.label} picture of this place` }), h("figcaption", {}, single.label));
  return h("p", { class: "note" }, "No before and after pictures for this change yet.");
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
      h("p", { class: "lead phone-only" }, APP.pitch), // on desktop the top bar already shows the pitch
      h("p", {}, "Every few days, radar satellites pass overhead and record the ground, whatever the weather. We compare the passes, mark where the land changed (trees removed, buildings added, earth moved), and check each change against public records. Pick a place to start."),
      h("ul", { class: "site-list" }, sites.map(siteButton)),
      h("button", { type: "button", class: "primary big", onclick: onTour }, "Or take the two-minute tour")
    )
  );
}

export function showHint() {
  $("card").replaceChildren(h("p", { class: "hint" }, "Click a colored shape on the map to see what changed and why it was flagged."));
}

let cardToken = 0; // guards against a slow chart arriving after another card was opened

/** Show one change. `site` is the loaded site data ({base, layers}). */
export function showCard(feature, site, onClose) {
  const { base, layers } = site;
  const token = ++cardToken;
  const p = feature.properties;
  const key = verdictKey(p.verdict);
  $("story").open = false;
  const evidence = p.evidence ?? {};

  const chartSlot = h("div", { class: "chart-slot", id: "signal-chart" },
    h("p", { class: "note" }, evidence.series ? "Loading signal history…" : "No signal history for this change yet."));
  if (evidence.series) {
    loadJson(base + evidence.series)
      .then((data) => token === cardToken && chartSlot.replaceChildren(buildChart(data, p)))
      .catch(() => token === cardToken && chartSlot.replaceChildren(h("p", { class: "note" }, "The signal history could not be loaded.")));
  }

  $("card").replaceChildren(
    h("article", { class: "card" },
      h("div", { class: "card-head" },
        h("span", { class: `badge ${key}` }, VERDICTS[key].label),
        h("button", { class: "close", type: "button", onclick: onClose, "aria-label": "Close details" }, "Close")
      ),
      h("h2", {}, changeLabel(p.type)),
      h("dl", { class: "facts" },
        h("dt", {}, "When"), h("dd", {}, when(p)),
        h("dt", {}, "Size"), h("dd", {}, formatArea(p.area_ha)),
        h("dt", {}, "Seen by"), h("dd", {}, sensorLabel(p.sensor)),
        h("dt", {}, "Confidence"), h("dd", {}, confidenceLabel(p.confidence))
      ),
      p.explain ? h("p", { class: "explain" }, p.explain) : null,
      p.reasons?.length ? h("h3", {}, "Why this verdict") : null,
      p.reasons?.length ? h("ul", { class: "reasons" }, p.reasons.map(reasonItem)) : null,
      p.verdict ? h("p", { class: "note" }, "A verdict says where a person should look first. It is not a finding about anyone.") : h("p", { class: "note" }, "This change has not been checked against public records yet."),
      h("h3", {}, "Before and after"),
      evidenceBlock(evidence, base, layers),
      h("h3", {}, "Radar signal over time"),
      chartSlot
    )
  );
  $("details-view").scrollTop = 0;
}
