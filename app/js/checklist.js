// Written by Claude. "Why this label?" checklist on the change card: one line per question the verdict rules ask
// (kb/verdict-rules.md), answered from the change's `reasons`. The deciding reason (reasons[0]) comes first.
import { h, formatArea, safeUrl } from "./format.js";

// Each question the rules ask: which reason codes answer it, and what to say when none of them is present.
const QUESTIONS = [
  { key: "protected", q: "Protected natural area?", codes: ["protected_area", "protected_buffer"], none: "Not inside a protected area.", spain: true },
  { key: "zoning", q: "What does the zoning say?", codes: ["zoning_non_buildable", "zoning_urban", "planned_sector"], none: "Nothing in the zoning changes the label.", spain: true },
  { key: "cadastre", q: "On the land registry?", codes: ["cadastre_building_found", "no_record_found"], none: "No new building on record.", spain: true },
  { key: "solar", q: "A listed solar plant?", codes: ["solar_plant_listed", "solar_plant_other"], none: "No listed solar plant explains this change.", spain: true },
  { key: "fire", q: "A recorded wildfire?", codes: ["fire_recorded"], none: "No wildfire in the records we have." },
  { key: "official", q: "Any official record (assessment, orders)?", codes: ["assessment_missing", "official_stop_order", "official_investigation", "official_action"], none: "None in the records we have (official records are entered by hand)." },
  { key: "size", q: "How big?", codes: ["small_area", "size_only"], none: null },
];

// `records_unavailable` reasons: verdict.py writes "The <service> could not be checked…" ("land registry", …),
// while `source` is the service's own name, so match on both. Each goes to its question's row.
const UNAVAILABLE = [["protected", "protected"], ["land registry", "cadastre"], ["urban-planning", "zoning"], ["solar", "solar"], ["wildfire", "fire"]];

const MARKS = {
  lowers: { mark: "✓", text: "Points to expected" },
  raises: { mark: "✗", text: "Points to a closer look" },
  neutral: { mark: "–", text: "No effect on the label" },
  unchecked: { mark: "?", text: "Could not be checked" },
};

const questionFor = (r) => {
  if (r.code === "records_unavailable") {
    const said = `${r.text ?? ""} ${r.source ?? ""}`.toLowerCase();
    return UNAVAILABLE.find(([word]) => said.includes(word))?.[1] ?? null;
  }
  return QUESTIONS.find((q) => q.codes.includes(r.code))?.key ?? null;
};

const markOf = (r) => (r.code === "records_unavailable" ? "unchecked" : MARKS[r.effect] ? r.effect : "neutral");

// The row's mark: the deciding reason's if it is in the row, else the strongest one present.
function rowMark(reasons, decidingReason) {
  if (reasons.includes(decidingReason)) return markOf(decidingReason);
  for (const m of ["raises", "unchecked", "lowers"]) if (reasons.some((r) => markOf(r) === m)) return m;
  return "neutral";
}

function answerLine(r) {
  const url = safeUrl(r.url);
  const source = r.source ? h("cite", {}, "Source: ", url ? h("a", { href: url, target: "_blank", rel: "noopener" }, r.source) : r.source) : null;
  return h("p", { class: "answer" }, r.text, source);
}

function row(question, reasons, mark, deciding, fallback) {
  const m = MARKS[mark];
  return h("li", { class: deciding ? "deciding" : "" },
    h("span", { class: `mark ${mark}`, title: m.text, role: "img", "aria-label": m.text }, m.mark),
    h("div", {},
      h("p", { class: "question" }, question, deciding ? h("span", { class: "decider" }, "Decided the label") : null),
      ...(reasons.length ? reasons.map(answerLine) : [h("p", { class: "answer" }, fallback)])
    )
  );
}

/** The "Why this label?" block for one change. `country` is the site's country (the Catalan records only apply in "ES"). */
export function buildChecklist(p, country) {
  if (!p.verdict) return [h("h3", {}, "Why this label?"), h("p", { class: "note" }, "Not judged yet: this change has not been checked against public records.")];
  const reasons = p.reasons ?? [];
  if (!reasons.length) return [h("h3", {}, "Why this label?"), h("p", { class: "note" }, "No reasons were recorded for this label.")];

  const deciding = reasons[0];
  const abroad = country && country !== "ES";
  const byKey = new Map();
  const others = [];
  for (const r of reasons) {
    const key = questionFor(r);
    if (key) byKey.set(key, [...(byKey.get(key) ?? []), r]);
    else others.push(r);
  }

  const rows = [];
  for (const q of QUESTIONS) {
    const rs = byKey.get(q.key) ?? [];
    if (abroad && q.spain && !rs.length) continue; // folded into the one "does not apply" row below
    const fallback = q.none ?? `${formatArea(p.area_ha)}.`;
    rows.push({ deciding: rs.includes(deciding), el: row(q.q, rs, rowMark(rs, deciding), rs.includes(deciding), fallback) });
  }
  if (abroad) rows.splice(0, 0, { deciding: false, el: row("Spanish and Catalan records?", [], "neutral", false, "They do not apply outside Spain.") });
  for (const r of others) rows.push({ deciding: r === deciding, el: row("Other", [r], markOf(r), r === deciding) });
  rows.sort((a, b) => b.deciding - a.deciding); // stable: the deciding row moves to the top, the rest keep their order

  return [
    h("h3", {}, "Why this label?"),
    h("ul", { class: "checklist" }, rows.map((r) => r.el)),
    h("p", { class: "note checklist-key" }, Object.values(MARKS).map((m) => `${m.mark} ${m.text.toLowerCase()}`).join(" · ")),
  ];
}
