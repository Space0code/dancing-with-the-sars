// Written by Claude. The "PDF report" export format: one A4 PDF with the map as the user sees it, key numbers, a summary,
// the changes to look at first and the full list. The summary is AI-written when the proxy (config.js, kb/report-proxy.md)
// answers in time and passes our check; otherwise a rule-based text is used. The report never depends on the proxy.
// Rules and wording: kb/report.md. jsPDF is loaded from a CDN only when a report is made.
import { VERDICTS, verdictKey, formatArea, formatDate, safeUrl } from "./format.js";
import { registerExportFormat, downloadBlob } from "./export.js";
import { describeSelection, getSelection } from "./selection.js";
import { whenText } from "./seen.js";
import { REPORT_API, REPORT_TIMEOUT_MS } from "./config.js";

const JSPDF = "https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js";
const AUTOTABLE = "https://cdnjs.cloudflare.com/ajax/libs/jspdf-autotable/3.8.2/jspdf.plugin.autotable.min.js";
const FOOTER = "Parallax · radar: NISAR (NASA/ISRO), Sentinel-1 (ESA, as NASA's OPERA RTC-S1 product); optical alerts and photos: NASA's OPERA DIST-ALERT and HLS products from Landsat (NASA/USGS) and Sentinel-2 (ESA) · labels come from rules on public records and are prompts for review, not findings";
const ORDER = ["high_concern", "review", "none", "expected"]; // the priority order of labels
const BAD_WORDS = /illegal|unlawful/i;

// --- priority rule (the same rule is the planned trigger of a future alert service, which is not built) ---
export const labelOf = (f) => verdictKey(f.properties.verdict);

/** label (high concern, needs review, not labelled, expected), then size (largest first), then recency (newest first). */
export function byPriority(a, b) {
  const pa = a.properties;
  const pb = b.properties;
  return ORDER.indexOf(labelOf(a)) - ORDER.indexOf(labelOf(b))
    || pb.area_ha - pa.area_ha
    || String(pb.last_date ?? pb.first_date).localeCompare(String(pa.last_date ?? pa.first_date))
    || String(pa.id).localeCompare(String(pb.id));
}

// --- text that the PDF standard fonts can draw (Latin-1 only) ---
const PLAIN = { "–": "-", "—": "-", "‑": "-", "−": "-", "→": "->", "←": "<-", "↔": "<->", "≥": ">=", "≤": "<=", "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...", "×": "x", "•": "-", " ": " ", " ": " ", "▶": ">" };
export function latin1(value) {
  const text = String(value ?? "").normalize("NFC").replace(/[–—‑−→←↔≥≤“”‘’…×•▶  ]/g, (c) => PLAIN[c]);
  let out = "";
  for (const ch of text) {
    const code = ch.codePointAt(0);
    if (code >= 32 && code <= 255 && !(code >= 127 && code < 160)) out += ch;
    else if (code === 10) out += "\n";
    else if (code === 9) out += " ";
    else {
      const base = ch.normalize("NFD").replace(/[̀-ͯ]/g, ""); // an accent we cannot draw: keep the base letter
      out += base.length && base.codePointAt(0) < 128 ? base : "?";
    }
  }
  return out;
}
const ha = (v) => (v === 0 ? "0 ha" : formatArea(v));
const clip = (text, n) => (text.length > n ? text.slice(0, n - 3).trimEnd() + "..." : text);

// --- facts ---
export function totals(changes) {
  const by = Object.fromEntries(ORDER.map((k) => [k, { n: 0, ha: 0 }]));
  let ha = 0;
  for (const f of changes) {
    by[labelOf(f)].n += 1;
    by[labelOf(f)].ha += f.properties.area_ha;
    ha += f.properties.area_ha;
  }
  return { n: changes.length, ha, by };
}

const reasonOf = (f) => f.properties.reasons?.[0]?.text ?? "No record found for this change.";

/** The changes sent to the summary: up to 6 high concern, up to 4 needs review, then the rest in priority order, 10 in all. */
function topForSummary(sorted) {
  const pick = [];
  const count = (k) => pick.filter((g) => labelOf(g) === k).length;
  for (const [k, max] of [["high_concern", 6], ["review", 4]]) for (const f of sorted) if (labelOf(f) === k && count(k) < max) pick.push(f);
  for (const f of sorted) if (pick.length < 10 && !pick.includes(f)) pick.push(f);
  return pick.sort(byPriority);
}

/** A reason without what belongs to one change (a size, a percentage, a year, a count, names in brackets), so it is true
 *  for every change whose reason has the same wording. Texts that keep a number after this are not made generic. */
export function genericReason(text) {
  return text
    .replace(/^\d+ building\(s\) registered here date from \d{4} or later.*$/, "Buildings registered here date from the year the change was first seen or later.")
    .replace(/^About \d+(?:[.,]\d+)? ?% of the place is /, "Part of the place is ")
    .replace(/^(The change is small) \([^)]*\)/, "$1")
    .replace(/\s*\([^)]*\)/g, "")
    .replace(/\s+([,.;])/g, "$1")
    .trim();
}

/** Per label, the most common main reasons (what the card shows first) among the selected changes: up to 4 of {reason, n}.
 *  Reasons that differ only in their numbers or names count as one and are worded generically, so the text holds for all n. */
export function reasonsByLabel(changes) {
  const out = {};
  for (const k of ORDER) {
    const groups = new Map();
    for (const f of changes) {
      if (labelOf(f) !== k) continue;
      const text = reasonOf(f).trim();
      const generic = genericReason(text);
      const g = groups.get(generic.toLowerCase()) ?? { generic, texts: new Set(), n: 0 };
      g.texts.add(text);
      g.n += 1;
      groups.set(generic.toLowerCase(), g);
    }
    if (groups.size) {
      out[k] = [...groups.values()].map((g) => {
        const [first] = g.texts;
        const reason = g.texts.size === 1 ? first : /\d/.test(g.generic) ? `for example: ${first}` : g.generic;
        return { reason: reason.slice(0, 240), n: g.n };
      }).sort((a, b) => b.n - a.n || a.reason.localeCompare(b.reason)).slice(0, 4);
    }
  }
  return out;
}

function bboxOf(geometry) {
  const box = [Infinity, Infinity, -Infinity, -Infinity];
  const walk = (c) => {
    if (typeof c[0] === "number") {
      box[0] = Math.min(box[0], c[0]); box[1] = Math.min(box[1], c[1]);
      box[2] = Math.max(box[2], c[0]); box[3] = Math.max(box[3], c[1]);
    } else c.forEach(walk);
  };
  walk(geometry.coordinates);
  return box.map((v) => Math.round(v * 100) / 100);
}

/** Exactly the request body of kb/report-proxy.md; nothing else leaves the browser. */
export function buildRequest({ site, changes, selection, kindName }) {
  const t = totals(changes);
  const iso = (d) => (/^\d{4}-\d{2}-\d{2}$/.test(d ?? "") ? d : null);
  const cap = (text, n) => String(text ?? "").trim().slice(0, n);
  const round = (v) => Math.round(v * 100) / 100;
  return {
    site: { name: cap(site.name, 120), country: cap(site.country ?? "", 120) },
    time_frame: { from: iso(selection.from), to: iso(selection.to) },
    area: selection.area ? { bbox: bboxOf(selection.area) } : null,
    totals: {
      changes: t.n, area_ha: round(t.ha),
      by_label: Object.fromEntries(ORDER.map((k) => [k, { n: t.by[k].n, ha: round(t.by[k].ha) }])),
    },
    reasons_by_label: reasonsByLabel(changes),
    top: topForSummary([...changes].sort(byPriority)).map((f) => ({
      kind: cap(kindName(f.properties.type), 120), area_ha: Number(formatArea(f.properties.area_ha).replace(/[^\d.]/g, "")) || round(f.properties.area_ha),
      when: cap(whenText(f.properties), 120), label: labelOf(f), reason: cap(reasonOf(f), 240),
    })),
  };
}

/** The summary is four sections: {high_concern: [..], review: [..], expected: "..", not_labelled: ".."} (kb/report-proxy.md). */
const LIMITS = { high_concern: 6, review: 4, bullet: 200, expected: 300, not_labelled: 200 };
const SECTION_KEYS = ["high_concern", "review", "expected", "not_labelled"];

/** Shape and length check of an answer (the Worker checks too); null when anything is off. */
export function checkSections(s) {
  if (!s || typeof s !== "object" || Array.isArray(s)) return null;
  if (Object.keys(s).length !== 4 || !SECTION_KEYS.every((k) => k in s)) return null;
  const ok = (v, max) => typeof v === "string" && v.length <= max && !BAD_WORDS.test(v);
  for (const k of ["high_concern", "review"]) {
    if (!Array.isArray(s[k]) || s[k].length > LIMITS[k] || !s[k].every((v) => ok(v, LIMITS.bullet) && v.trim())) return null;
  }
  if (!ok(s.expected, LIMITS.expected) || !ok(s.not_labelled, LIMITS.not_labelled)) return null;
  const out = { high_concern: s.high_concern.map((v) => v.trim()), review: s.review.map((v) => v.trim()), expected: s.expected.trim(), not_labelled: s.not_labelled.trim() };
  return out.high_concern.length + out.review.length + out.expected.length + out.not_labelled.length ? out : null;
}

/** The AI sections, or null for any failure (no address, error, timeout, answer failing our check). */
export async function fetchAiSummary(body) {
  if (!REPORT_API) return null;
  const control = new AbortController();
  let timer;
  try {
    const timeout = new Promise((_, reject) => { timer = setTimeout(() => { control.abort(); reject(new Error("timeout")); }, REPORT_TIMEOUT_MS); });
    const answer = fetch(REPORT_API, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: control.signal })
      .then((r) => (r.ok ? r.json() : null));
    const data = await Promise.race([answer, timeout]);
    return checkSections(data?.sections);
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

// --- rule-based summary: the same four sections from templates ---
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const dotless = (t) => t.replace(/[.\s]+$/, "");
const lowerFirst = (t) => (/^[A-Z][a-z]/.test(t) ? t[0].toLowerCase() + t.slice(1) : t);

/** One short line for a change: "Land clearing, 109 ha: <reason>; <when>". */
function bulletFor(kindName, f) {
  const p = f.properties;
  return clip(`${kindName(p.type)}, ${formatArea(p.area_ha)}: ${dotless(reasonOf(f))}; ${whenText(p, { short: true })}`, LIMITS.bullet);
}

/** Sections for a selection, from the changes' main reasons; the same shape as the AI sections. */
export function ruleSections({ changes, kindName }) {
  const sorted = [...changes].sort(byPriority);
  const of = (k) => sorted.filter((f) => labelOf(f) === k);
  const reasons = reasonsByLabel(changes);
  const review = of("review");
  const group = reasons.review?.slice(0, 3).map(({ reason, n }) => clip(`${plural(n, "change", "changes")}: ${dotless(reason)}`, LIMITS.bullet));
  // the first sentence of each of the two most common reasons, with how many changes each covers
  const why = (reasons.expected ?? []).slice(0, 2).map(({ reason, n }) => `${lowerFirst(dotless(reason.split(/\.\s/)[0]))} (${plural(n, "change", "changes")})`);
  return {
    high_concern: of("high_concern").slice(0, LIMITS.high_concern).map((f) => bulletFor(kindName, f)),
    review: review.length <= LIMITS.review ? review.map((f) => bulletFor(kindName, f)) : group,
    expected: why.length ? `Expected because the records show: ${why.join("; ")}.` : "",
    not_labelled: of("none").length ? "No record has been matched to these yet, so they carry no label." : "",
  };
}

const emptySummary = ({ site, selection }) =>
  `No land changes were found at ${selection.area ? `${site.name}, inside the selected area` : site.name} for the selection in this report. Radar and optical satellite data were checked.`;

// --- libraries and picture ---
const scripts = new Map();
function loadScript(src) {
  if (!scripts.has(src)) {
    scripts.set(src, new Promise((resolve, reject) => {
      document.head.append(Object.assign(document.createElement("script"), { src, onload: resolve, onerror: () => reject(new Error("could not load the PDF library")) }));
    }).catch((err) => { scripts.delete(src); throw err; }));
  }
  return scripts.get(src);
}

async function loadPdf() {
  await loadScript(JSPDF);
  await loadScript(AUTOTABLE);
  return window.jspdf.jsPDF;
}

/** The map picture as a JPEG data URL (smaller than PNG) with its size. */
function toJpeg(dataUrl) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const canvas = Object.assign(document.createElement("canvas"), { width: img.naturalWidth, height: img.naturalHeight });
      const c = canvas.getContext("2d");
      c.fillStyle = "#fff";
      c.fillRect(0, 0, canvas.width, canvas.height);
      c.drawImage(img, 0, 0);
      resolve({ url: canvas.toDataURL("image/jpeg", 0.9), w: img.naturalWidth, h: img.naturalHeight });
    };
    img.onerror = () => reject(new Error("the map picture could not be read"));
    img.src = dataUrl;
  });
}

const $ = (id) => document.getElementById(id);

/** " (west, south to east, north: 26.06, 64.80 to 26.15, 64.85)" so the report can be reproduced; "" without an area. */
function areaBox() {
  const pts = [];
  const walk = (c) => (typeof c[0] === "number" ? pts.push(c) : c.forEach(walk));
  const g = getSelection().area;
  if (!g?.coordinates) return "";
  walk(g.coordinates);
  if (!pts.length) return "";
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const f = (n) => n.toFixed(2);
  return ` (west, south to east, north: ${f(Math.min(...xs))}, ${f(Math.min(...ys))} to ${f(Math.max(...xs))}, ${f(Math.max(...ys))})`;
}
const isRadar = () => $("view-radar")?.getAttribute("aria-checked") === "true";
const hasPhotos = () => !isRadar() && $("photos-btn")?.getAttribute("aria-pressed") === "true"; // Satellite with Dated photos on

/** What the map shows now, read from the page: the picture's own satellite and date (the label under the view switch)
 *  and the slider date, which is the date up to which changes are shown. The Satellite view without dated photos shows
 *  the Imagery base map, which has no date. */
function viewText() {
  const date = $("date-label")?.textContent.split("·")[0].trim(); // "26 Oct 2026 · image 68 of 68" -> the date
  const upTo = date ? ` · changes shown up to ${date}` : "";
  if (!isRadar() && !hasPhotos()) return `Imagery · undated · may be older${upTo}`;
  const kind = isRadar() ? "Radar" : "Satellite photo";
  const frame = $("frame-label")?.textContent.replace(/\s*·\s*/g, ", ").trim(); // "Landsat · 3 Sept 2026" -> "Landsat, 3 Sept 2026"
  const picture = !frame || /^No /i.test(frame) ? `${kind}, no picture for this date` : `${kind}, ${frame}`;
  return `${picture}${upTo}`;
}

/** The map's own credit line (the base map shown), with the dated photos' source first when they are on. */
function attributionText() {
  const text = document.querySelector(".maplibregl-ctrl-attrib-inner")?.textContent.replace(/\s+/g, " ").trim();
  const base = text || "Background map: Esri and contributors";
  return hasPhotos() ? `Dated photo: NASA HLS (Landsat, Sentinel-2) · ${base}` : base;
}

// --- the PDF ---
const M = 14; // page margin, mm
const W = 210 - 2 * M;
const GREY = [90, 90, 90];

export async function buildReport(ctx, aiSections, picture) {
  const JsPdf = await loadPdf();
  const doc = new JsPdf({ unit: "mm", format: "a4", orientation: "portrait" });
  doc.setProperties({ title: latin1(`Parallax report: ${ctx.site.name}`) });
  const sorted = [...ctx.changes].sort(byPriority);
  const t = totals(sorted);
  const text = (s, x, y, opts) => doc.text(latin1(s), x, y, opts);
  const lines = (s, width) => doc.splitTextToSize(latin1(s), width);
  let y = M;
  const need = (h) => { if (y + h > 297 - 20) { doc.addPage(); y = M; } };
  const heading = (s, room = 32) => { need(room); y += 3; doc.setFont("helvetica", "bold").setFontSize(12).setTextColor(0); text(s, M, y); y += 5; };
  const body = (s, size = 10) => {
    doc.setFont("helvetica", "normal").setFontSize(size).setTextColor(30);
    for (const l of lines(s, W)) { need(5); text(l, M, y); y += 4.6; }
  };
  const table = (opts) => {
    doc.autoTable({ margin: { left: M, right: M, top: M, bottom: 20 }, headStyles: { fillColor: [235, 235, 235], textColor: 0 }, ...opts, startY: y });
    y = doc.lastAutoTable.finalY + 2;
  };

  // header
  doc.setFont("helvetica", "bold").setFontSize(20).setTextColor(0);
  text("Parallax report", M, y + 6); y += 13;
  doc.setFontSize(13); text(ctx.site.name, M, y); y += 6;
  doc.setFont("helvetica", "normal").setFontSize(9.5).setTextColor(...GREY);
  for (const l of [`Selection: ${(describeSelection() || "Whole site, all dates").replace("area", `area${areaBox()}`)}`, `Map picture: ${viewText()}`, `Report made: ${formatDate(new Date().toISOString().slice(0, 10))}`]) { text(l, M, y); y += 4.5; }
  y += 2;

  // map picture, legend, attribution
  const mh = Math.min(105, (W * picture.h) / picture.w);
  doc.addImage(picture.url, "JPEG", M, y, W, mh);
  doc.setDrawColor(180).setLineWidth(0.2).rect(M, y, W, mh);
  y += mh + 4;
  doc.setFontSize(8.5).setFont("helvetica", "normal");
  let x = M;
  const entries = [...Object.values(VERDICTS).map((v) => [v.label, v.color]), ...(isRadar() ? [["Changed since first picture", "#D628A0"]] : [])];
  for (const [label, color] of entries) {
    const w = doc.getTextWidth(latin1(label)) + 9;
    if (x + w > M + W) { x = M; y += 5; }
    doc.setFillColor(color).setDrawColor(60).setLineWidth(0.15).rect(x, y - 2.8, 3.4, 3.4, "FD");
    doc.setTextColor(30); text(label, x + 5, y);
    x += w + 3;
  }
  y += 4.5;
  doc.setFontSize(7).setTextColor(...GREY);
  for (const l of lines(attributionText(), W)) { text(l, M, y); y += 3.3; }
  y += 2;

  // key numbers
  heading("Key numbers");
  table({
    theme: "grid", styles: { fontSize: 9.5, cellPadding: 1.8, textColor: 30 }, head: [[{ content: "" }, { content: "Changes", styles: { halign: "right" } }, { content: "Hectares", styles: { halign: "right" } }]],
    body: [["All selected", t.n, ha(t.ha)], ...ORDER.map((k) => [VERDICTS[k].label, t.by[k].n, ha(t.by[k].ha)])].map((r) => r.map((c) => latin1(c))),
    columnStyles: { 1: { halign: "right" }, 2: { halign: "right" } },
  });

  // summary: sub-headings and bullets in a grey box; it follows the key numbers and may continue on the next page
  const sections = aiSections ?? ruleSections(ctx);
  {
    const LH = 4.4;
    const rows = []; // one printed line each: {s, x, bullet, font, size, color, gap, keep}
    const add = (s, o = {}) => rows.push({ s, x: 0, bullet: "", font: "normal", size: 10, color: 30, gap: 0, keep: false, ...o });
    doc.setFont("helvetica", "normal").setFontSize(10);
    const wrap = (s, indent) => lines(s, W - 8 - indent);
    if (aiSections) add("AI-written summary", { font: "bold", color: 0, keep: true });
    if (!t.n) wrap(emptySummary(ctx), 0).forEach((l) => add(l));
    else {
      const block = (title, items, bullets) => {
        add(title, { font: "bold", size: 9.5, color: 0, gap: rows.length ? 2 : 0, keep: true });
        for (const item of items) wrap(item, bullets ? 5 : 0).forEach((l, i) => add(l, bullets ? { x: 5, bullet: i === 0 ? "-" : "" } : {}));
      };
      if (t.by.high_concern.n && sections.high_concern.length) {
        const more = t.by.high_concern.n - sections.high_concern.length;
        block("High concern", more > 0 ? [...sections.high_concern, `${more} more ${more === 1 ? "is" : "are"} in the list below.`] : sections.high_concern, true);
      }
      if (t.by.review.n && sections.review.length) block("Needs review", sections.review, true);
      if (t.by.expected.n && sections.expected) block("Expected", [sections.expected], false);
      if (t.by.none.n && sections.not_labelled) block("Not labelled yet", [sections.not_labelled], false);
    }
    if (aiSections) add("Written by an AI model from the facts in this report. Check the list below before acting.", { size: 8, color: GREY, gap: 2 });
    const total = rows.reduce((h, r) => h + LH + r.gap, 0) + 5;
    heading("Summary", Math.min(total + 8, 240)); // a box that fits on one page starts on a fresh page rather than being split
    for (let i = 0; i < rows.length;) {
      const fit = () => { let h = 0, n = 0; for (let k = i; k < rows.length && h + LH + rows[k].gap <= 277 - y - 8; k++) { h += LH + rows[k].gap; n++; } while (n > 1 && rows[i + n - 1].keep) n--; return n; };
      let n = fit();
      if (n < Math.min(3, rows.length - i)) { doc.addPage(); y = M; n = fit(); }
      const part = rows.slice(i, i + n);
      const bh = part.reduce((h, r) => h + LH + r.gap, 0) + 5;
      doc.setFillColor(244, 244, 244).setDrawColor(190).rect(M, y, W, bh, "FD");
      let ty = y + 6;
      for (const r of part) {
        ty += r.gap;
        doc.setFont("helvetica", r.font).setFontSize(r.size).setTextColor(...[].concat(r.color));
        if (r.bullet) text(r.bullet, M + 4, ty);
        text(r.s, M + 4 + r.x, ty);
        ty += LH;
      }
      y += bh + 2;
      i += n;
    }
  }

  // top five and the full list
  const sources = [];
  const sourceNo = (f) => {
    const r = f.properties.reasons?.[0];
    const url = safeUrl(r?.url);
    if (!url) return null;
    let i = sources.findIndex((s) => s.url === url);
    if (i < 0) i = sources.push({ url, name: r.source ?? "Source" }) - 1;
    return i + 1;
  };
  const kind = (f) => ctx.kindName(f.properties.type);
  const label = (f) => VERDICTS[labelOf(f)].label;
  // the first five are left out when the summary's high-concern bullets already list all of them (the full table follows)
  const listed = Math.min(sections.high_concern.length, LIMITS.high_concern);
  const firstFive = sorted.slice(0, 5);
  const repeats = firstFive.length > 0 && firstFive.every((f, i) => labelOf(f) === "high_concern" && i < listed);
  if (!repeats) heading("Look at these first");
  if (!sorted.length) body("No changes in this selection.");
  else {
    if (!repeats) table({
      theme: "grid", styles: { fontSize: 8.5, cellPadding: 1.6, textColor: 30, overflow: "linebreak" }, head: [["#", "Kind", { content: "Size", styles: { halign: "right" } }, "When", "Label", "Main reason"]],
      body: sorted.slice(0, 5).map((f, i) => [i + 1, kind(f), formatArea(f.properties.area_ha), whenText(f.properties, { short: true }), label(f), clip(reasonOf(f), 150)].map((c) => latin1(c))),
      columnStyles: { 0: { cellWidth: 7 }, 1: { cellWidth: 26 }, 2: { cellWidth: 16, halign: "right" }, 3: { cellWidth: 34 }, 4: { cellWidth: 24 } },
    });
    heading(`All selected changes (${sorted.length})`);
    table({
      theme: "striped", styles: { fontSize: 7.5, cellPadding: 1.3, textColor: 30, overflow: "linebreak" }, showHead: "everyPage",
      head: [["Id", "Kind", { content: "Size (ha)", styles: { halign: "right" } }, "First seen", "Label", "Main reason", "Src"]],
      body: sorted.map((f) => {
        const n = sourceNo(f);
        return [f.properties.id, kind(f), formatArea(f.properties.area_ha).replace(" ha", ""), formatDate(f.properties.first_date), label(f), clip(reasonOf(f), 200), n ? `[${n}]` : ""].map((c) => latin1(c));
      }),
      columnStyles: { 0: { cellWidth: 25 }, 1: { cellWidth: 21 }, 2: { cellWidth: 14, halign: "right" }, 3: { cellWidth: 20 }, 4: { cellWidth: 21 }, 6: { cellWidth: 9 } },
      didDrawCell(d) {
        if (d.section === "body" && d.column.index === 6 && d.cell.raw) {
          const s = sources[Number(String(d.cell.raw).slice(1, -1)) - 1];
          if (s) doc.link(d.cell.x, d.cell.y, d.cell.width, d.cell.height, { url: s.url });
        }
      },
    });
  }

  // numbered sources (the "Src" column points here)
  if (sources.length) {
    heading("Sources");
    const many = sources.length > 25; // a long list is printed small, in two columns, so it does not add pages of links
    const size = many ? 6.5 : 8;
    const line = many ? 2.9 : 3.4;
    const colW = many ? (W - 6) / 2 : W;
    doc.setFont("helvetica", "normal").setFontSize(size);
    const cut = (url) => { // a URL has no spaces: cut it by width
      const parts = [];
      let rest = latin1(url);
      while (rest) {
        let n = rest.length;
        while (n > 1 && doc.getTextWidth(rest.slice(0, n)) > colW - 4) n--;
        parts.push(rest.slice(0, n));
        rest = rest.slice(n);
      }
      return parts;
    };
    let col = 0;
    let top = y;
    sources.forEach((s, i) => {
      const parts = cut(s.url);
      const height = (parts.length + 1) * line + 1.2;
      if (y + height > 277) {
        if (many && col === 0) { col = 1; y = top; }
        else { doc.addPage(); y = M; top = M; col = 0; }
      }
      const x = M + col * (colW + 6);
      doc.setFont("helvetica", "normal").setFontSize(size).setTextColor(30);
      text(`[${i + 1}] ${clip(s.name, many ? 50 : 90)}`, x, y); y += line;
      doc.setTextColor(0, 70, 160);
      for (const part of parts) {
        text(part, x + 4, y);
        doc.link(x + 4, y - 3, colW - 4, 3.6, { url: s.url });
        y += line;
      }
      y += 1.2;
    });
  }
  if (doc.getNumberOfPages() > 1 && y <= M + 0.1) doc.deletePage(doc.getNumberOfPages()); // never end on an empty page

  // footer on every page
  const pages = doc.getNumberOfPages();
  for (let p = 1; p <= pages; p++) {
    doc.setPage(p);
    doc.setDrawColor(200).setLineWidth(0.2).line(M, 283, M + W, 283);
    doc.setFont("helvetica", "normal").setFontSize(7).setTextColor(...GREY);
    doc.text(doc.splitTextToSize(latin1(FOOTER), W - 20), M, 286.5);
    doc.text(`Page ${p} of ${pages}`, M + W, 286.5, { align: "right" });
  }
  return doc.output("blob");
}

registerExportFormat({
  id: "pdf-report", first: true, label: "PDF report",
  note: "Map picture, key numbers, the changes to look at first, and the full list",
  async run(ctx) {
    ctx.status?.("Preparing report…");
    const picture = await toJpeg(await ctx.snapshot()); // the map exactly as it is now
    const ai = await fetchAiSummary(buildRequest(ctx)); // null on any failure: the rule-based text is used
    downloadBlob(`parallax-${ctx.site.id}-report.pdf`, await buildReport(ctx, ai, picture));
  },
});
