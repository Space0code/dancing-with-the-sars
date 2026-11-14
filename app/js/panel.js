// Written by Claude. Side panel: the collapsible site story and the change card.
import { h, VERDICTS, verdictKey, changeLabel, confidenceLabel, sensorLabel, formatDate, formatArea, safeUrl } from "./format.js";

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
  box.replaceChildren(
    h("summary", {}, story.headline),
    ...story.story.map((p) => h("p", {}, p)),
    sources.length
      ? h("p", { class: "sources" }, "Sources: ", sources.flatMap((s, i) => [i ? " · " : "", h("a", { href: s.url, target: "_blank", rel: "noopener" }, s.title)]))
      : null
  );
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

function picture(src, base, caption) {
  const fig = h("figure", {}, h("img", { src: base + src, alt: `${caption} picture of this place`, loading: "lazy" }), h("figcaption", {}, caption));
  fig.querySelector("img").addEventListener("error", () => fig.replaceChildren(h("figcaption", {}, `${caption}: picture not available`)));
  return fig;
}

export function showHint() {
  $("card").replaceChildren(h("p", { class: "hint" }, "Click a colored shape on the map to see what changed and why it was flagged."));
}

/** Show one change. `base` is the site's data folder, for evidence picture paths. */
export function showCard(feature, base, onClose) {
  const p = feature.properties;
  const key = verdictKey(p.verdict);
  $("story").open = false;
  const evidence = p.evidence ?? {};
  const pictures = [evidence.before && picture(evidence.before, base, "Before"), evidence.after && picture(evidence.after, base, "After")].filter(Boolean);

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
      pictures.length ? h("h3", {}, "Before and after") : null,
      pictures.length ? h("div", { class: "pair" }, pictures) : null,
      // Slot for the signal chart (next issue): listen for the "change-shown" event on document.
      h("div", { class: "chart-slot", id: "signal-chart" })
    )
  );
  document.dispatchEvent(new CustomEvent("change-shown", { detail: { feature, base } }));
  $("panel").scrollTop = 0;
}
