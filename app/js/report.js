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
    top: [...changes].sort(byPriority).slice(0, 10).map((f) => ({
      kind: cap(kindName(f.properties.type), 120), area_ha: round(f.properties.area_ha),
      when: cap(whenText(f.properties), 120), label: labelOf(f), reason: cap(reasonOf(f), 240),
    })),
  };
}

/** The AI summary text, or null for any failure (no address, error, timeout, answer failing our check). */
export async function fetchAiSummary(body) {
  if (!REPORT_API) return null;
  const control = new AbortController();
  let timer;
  try {
    const timeout = new Promise((_, reject) => { timer = setTimeout(() => { control.abort(); reject(new Error("timeout")); }, REPORT_TIMEOUT_MS); });
    const answer = fetch(REPORT_API, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: control.signal })
      .then((r) => (r.ok ? r.json() : null));
    const data = await Promise.race([answer, timeout]);
    const text = typeof data?.summary === "string" ? data.summary.trim() : "";
    return text && text.length <= 1500 && !BAD_WORDS.test(text) ? text : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

// --- rule-based summary: templates filled with the same numbers ---
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

export function ruleSummary({ site, changes, selection }) {
  const t = totals(changes);
  const place = selection.area ? `${site.name}, inside the selected area` : site.name;
  if (!t.n) return `No land changes were found at ${place} for the selection in this report. Radar and optical satellite data were checked.`;
  let when;
  if (selection.from && selection.to) when = `between ${formatDate(selection.from)} and ${formatDate(selection.to)}`;
  else if (selection.from) when = `from ${formatDate(selection.from)}`;
  else if (selection.to) when = `until ${formatDate(selection.to)}`;
  else {
    const firsts = changes.map((f) => f.properties.first_date).sort();
    when = firsts[0] === firsts.at(-1) ? `on ${formatDate(firsts[0])}` : `between ${formatDate(firsts[0])} and ${formatDate(firsts.at(-1))}`;
  }
  const first = `Satellite data show ${plural(t.n, "land change", "land changes")} at ${place}, covering about ${formatArea(t.ha)} and first seen ${when}.`;
  const parts = [
    ["high_concern", (n) => `${n} marked high concern`], ["review", (n) => `${n} marked needs review`],
    ["none", (n) => `${n} not labelled yet`], ["expected", (n) => `${n} marked expected`],
  ].filter(([k]) => t.by[k].n).map(([k, say]) => `${say(t.by[k].n)} (${formatArea(t.by[k].ha)})`);
  const second = `Of these, ${parts.join(", ")}.`;
  const look = Math.min(5, t.n);
  const third = `${look === 1 ? "The change" : `The ${look} changes`} listed under "Look at these first" ${look === 1 ? "is" : "are"} the best place to start; a label is a prompt for a person to check the records, not a finding about anyone.`;
  return `${first} ${second} ${third}`;
}

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
 *  the background imagery, which has no date. */
function viewText() {
  const date = $("date-label")?.textContent.split("·")[0].trim(); // "26 Oct 2026 · image 68 of 68" -> the date
  const upTo = date ? ` · changes shown up to ${date}` : "";
  if (!isRadar() && !hasPhotos()) return `Background imagery (undated)${upTo}`;
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

export async function buildReport(ctx, aiText, picture) {
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

  // summary: it follows the key numbers on page 1 and continues on the next page only when it must
  if (aiText) {
    heading("Summary");
    const rows = [
      { s: "AI-written summary", font: "bold", size: 10, color: 0 },
      ...lines(aiText, W - 8).map((s) => ({ s, font: "normal", size: 10, color: 30 })),
      { s: "Written by an AI model from the numbers in this report. Check the list below before acting.", font: "normal", size: 8, color: GREY },
    ];
    for (let i = 0; i < rows.length;) {
      let fit = Math.floor((277 - y - 6) / 4.6);
      if (fit < Math.min(3, rows.length - i)) { doc.addPage(); y = M; fit = Math.floor((277 - y - 6) / 4.6); }
      const part = rows.slice(i, i + fit);
      const bh = part.length * 4.6 + 6;
      doc.setFillColor(244, 244, 244).setDrawColor(190).rect(M, y, W, bh, "FD");
      part.forEach((r, k) => {
        doc.setFont("helvetica", r.font).setFontSize(r.size).setTextColor(...[].concat(r.color));
        text(r.s, M + 4, y + 6 + k * 4.6);
      });
      y += bh + 2;
      i += part.length;
    }
  } else {
    const rule = ruleSummary(ctx);
    heading("Summary", lines(rule, W).length * 4.6 + 12);
    body(rule);
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
  heading("Look at these first");
  if (!sorted.length) body("No changes in this selection.");
  else {
    table({
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
