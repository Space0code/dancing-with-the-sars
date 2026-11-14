// Written by Claude. The change card's "when / seen by / how sure" wording, built from `not_before` and `sources`
// (kb/multi-sensor-design.md sections 2-4). A change without `sources` keeps the old single-sensor wording.
// Never says "verified", "proved" or "exact date"; "also saw it" / "confirms" only for a second detecting source.
import { h, formatDate, formatArea, toDay, sensorLabel, sensorCredit, confidenceLabel } from "./format.js";

const part = (iso, month, year) =>
  new Intl.DateTimeFormat("en-GB", { day: "numeric", ...(month && { month: "short" }), ...(year && { year: "numeric" }), timeZone: "UTC" }).format(new Date(iso));

/** "2 and 20 May 2026" · "22 May and 31 Jul 2026" · "21 Oct 2025 and 29 Apr 2026" (the shared month/year is said once). */
export function dateRange(a, b, joiner = "and") {
  const sameYear = a.slice(0, 4) === b.slice(0, 4);
  const sameMonth = sameYear && a.slice(5, 7) === b.slice(5, 7);
  return `${part(a, !sameMonth, !sameYear)} ${joiner} ${formatDate(b)}`;
}

/** The name used inside a sentence: "NISAR", "Sentinel-1", "the optical alerts". */
function shortName(sensor) {
  if (/nisar/i.test(sensor)) return "NISAR";
  if (/sentinel-1/i.test(sensor)) return "Sentinel-1";
  if (/dist-alert|optical|hls|sentinel-2/i.test(sensor)) return "the optical alerts";
  return sensor;
}

const hasSources = (p) => Array.isArray(p.sources) && p.sources.length > 0;
const kindOf = (s) => s.kind ?? (/nisar|sentinel-1/i.test(s.sensor) ? "radar" : "optical");

/** When it happened, as a window. `short`: the one-line form for the list rows. */
export function whenText(p, { short = false } = {}) {
  if (!hasSources(p) && p.not_before === undefined) {
    return p.first_date === p.last_date ? formatDate(p.first_date) : `${formatDate(p.first_date)} to ${formatDate(p.last_date)}`;
  }
  const detected = (p.sources ?? []).filter((s) => s.role === "detected");
  const late = (p.sources ?? []).filter((s) => s.role === "late_start");
  if (!detected.length && late.length) {
    const lead = `already under way on ${formatDate(p.first_date)}`;
    return short ? lead : `${lead}, when ${shortName(late[0].sensor)} began watching; the start date is not known`;
  }
  let text;
  if (p.not_before && p.not_before < p.first_date) {
    text = toDay(p.first_date) - toDay(p.not_before) === 1 ? `on ${formatDate(p.first_date)}` : `between ${dateRange(p.not_before, p.first_date)}`;
  } else {
    text = `on or before ${formatDate(p.first_date)}`;
  }
  if (!short && p.last_date > p.first_date) text += `; still changing until ${formatDate(p.last_date)}`;
  return text;
}

/** "14 ha", or "14 ha (sources: 11 to 14 ha)" when the sources measured different areas. */
export function sizeText(p) {
  const areas = (p.sources ?? []).filter((s) => (s.role === "detected" || s.role === "late_start") && s.area_ha != null).map((s) => s.area_ha);
  if (areas.length < 2) return formatArea(p.area_ha);
  const [lo, hi] = [Math.min(...areas), Math.max(...areas)];
  const [a, b] = [formatArea(lo), formatArea(hi)];
  return a === b ? formatArea(p.area_ha) : `${formatArea(p.area_ha)} (sources: ${a.replace(" ha", "")} to ${b})`;
}

/** One sentence on how sure we are and why, from who saw it and the site's risky months. Null without `sources`. */
export function confidenceNote(p, siteSources = []) {
  const saw = (p.sources ?? []).filter((s) => s.role === "detected" || s.role === "late_start");
  if (!saw.length) return null;
  const kinds = new Set(saw.map(kindOf));
  if (kinds.size > 1) return "two independent kinds of satellite saw it";
  const kind = [...kinds][0];
  const month = Number(p.first_date.slice(5, 7));
  const risky = saw.some((s) => siteSources.find((d) => d.sensor === s.sensor)?.risky_months?.includes(month));
  if (risky) {
    return kind === "radar"
      ? "seen only by radar, in a month when weather can fake a change"
      : "seen only by the optical alerts, in a month when weather can fake a change";
  }
  if (kind === "radar" && saw.length > 1) return "both radar satellites saw it";
  return `only ${shortName(saw[0].sensor)} saw it`;
}

/** The card's Confidence line. */
export const confidenceText = (p, siteSources) => {
  const note = confidenceNote(p, siteSources);
  return note ? `${confidenceLabel(p.confidence)} · ${note}` : confidenceLabel(p.confidence);
};

const MARKS = {
  detected: { mark: "●", label: "saw it" },
  late_start: { mark: "◐", label: "began watching after it started" },
  not_seen: { mark: "○", label: "was watching and did not flag it" },
  not_watching: { mark: "○", label: "was not watching yet" },
};
const ORDER = { detected: 0, late_start: 1, not_seen: 2, not_watching: 3 };

// A source can see a change without being able to date it (first_date null): then it shows no date, never "1 Jan 1970".
function dates(s) {
  if (!s.first_date) return "";
  if (s.role === "detected") return s.not_before && s.not_before < s.first_date ? dateRange(s.not_before, s.first_date, "–") : formatDate(s.first_date);
  if (s.role === "late_start") return `by ${formatDate(s.first_date)}`;
  return "";
}

// "not_seen" with a share above 0 means the source flagged a small part of the change: say so, don't say "did not flag it".
const partly = (s) => s.role === "not_seen" && s.share > 0;

/** "Seen by": one row per source: marker, plain name, dates, role in words, then the source's own sentence. */
export function seenBy(p) {
  if (!hasSources(p)) return null;
  const detectedDates = p.sources.filter((s) => s.role === "detected" && s.first_date).map((s) => s.first_date).sort();
  const roleWord = (s) => {
    if (partly(s)) return "flagged only a small part";
    if (s.role === "detected") return !s.first_date ? "saw it, date unknown" : s.first_date > detectedDates[0] ? "confirms" : "first";
    return { late_start: "already under way", not_seen: "did not flag it", not_watching: "not watching" }[s.role] ?? "";
  };
  const dated = (s) => s.first_date ?? "9999-12-31"; // undated rows go last within their group
  const rows = [...p.sources]
    .sort((a, b) => (ORDER[a.role] ?? 9) - (ORDER[b.role] ?? 9) || dated(a).localeCompare(dated(b)))
    .map((s) => {
      const m = partly(s) ? { mark: "○", label: "was watching and flagged only a small part" } : MARKS[s.role] ?? { mark: "○", label: "" };
      return h("li", { class: `seen-row ${s.role}` },
        h("span", { class: "seen-mark", role: "img", "aria-label": m.label }, m.mark),
        h("span", { class: "seen-main" },
          h("span", { class: "seen-name" }, sensorLabel(s.sensor)),
          dates(s) ? h("span", { class: "seen-dates" }, dates(s)) : null),
        h("span", { class: "seen-role" }, roleWord(s)),
        s.note ? h("span", { class: "seen-note" }, s.note) : null,
        sensorCredit(s.sensor) ? h("span", { class: "seen-note seen-credit" }, sensorCredit(s.sensor)) : null);
    });
  return h("ul", { class: "seen" }, rows);
}
