// Written by Claude. Charts in plain SVG, one line per series, no library: the signal chart on the change card and
// the curve in a site story (story.chart, same file format as a series file).
import { h, toDay, formatDate, sensorLabel } from "./format.js";

const NS = "http://www.w3.org/2000/svg";
const W = 360, H = 230, M = { l: 46, r: 12, t: 22, b: 30 };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// One color per satellite (Okabe-Ito purple / bluish green, distinct from the verdict colors); line style tells the series apart.
const SENSOR_COLORS = { nisar: "#7B3FA0", sentinel: "#00826A", optical: "#9A6A00", other: "#555555" };
const DASHES = ["", "7 3", "2 3"];
const DOT_MAX = 15; // lines with at most this many points get a dot per measurement
const sensorKey = (sensor) =>
  /nisar/i.test(sensor) ? "nisar" : /sentinel[- ]?1|^s1\b/i.test(sensor) ? "sentinel" : /optic|dist|hls|landsat|sentinel-?2/i.test(sensor) ? "optical" : "other";

// What a regulator should see in the chart, by kind of change.
const HINTS = {
  clearing: "How to read it: each line is a radar signal over time. When trees are removed, the vegetation line drops.",
  structure: "How to read it: each line is a radar signal over time. When walls and roofs appear, the surface line jumps up.",
  earthworks: "How to read it: each line is a radar signal over time. While the ground is being moved, the lines turn jumpy.",
  fire: "How to read it: each line is a radar signal over time. After a fire, the vegetation line drops.",
};
const GENERIC_HINT = "How to read it: each line is a radar signal over time. A lasting step in a line means the ground changed.";

const el = (tag, attrs = {}, ...kids) => {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) node.setAttribute(k, v);
  node.append(...kids);
  return node;
};

function niceTicks(min, max, count = 4) {
  const raw = (max - min) / count || 1;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
  const ticks = [];
  for (let t = Math.ceil(min / step) * step; t <= max + 1e-9; t += step) ticks.push(Math.round(t * 100) / 100);
  return ticks;
}

function monthTicks(startDay, endDay) {
  const span = endDay - startDay;
  const step = span <= 400 ? 2 : span <= 1200 ? 6 : 12;
  const first = new Date(startDay * 86400000);
  const ticks = [];
  for (let y = first.getUTCFullYear(), m = 0; ; m += step) {
    if (m >= 12) { y += Math.floor(m / 12); m %= 12; }
    const day = Math.round(Date.UTC(y, m, 1) / 86400000);
    if (day > endDay) break;
    if (day >= startDay) ticks.push({ day, label: `${MONTHS[m]} ’${String(y).slice(2)}` });
  }
  return ticks;
}

/**
 * Draw the usable series of a series file. Options: `mark` = a date to flag as "Change first seen" (or null),
 * `zero` = the y-axis starts at 0, `axis` = the y-axis label. Returns {svg, lines, events, setCursor(iso|null)}.
 */
function draw(series, data, { mark = null, zero = false, axis }) {
  const events = (data.events ?? []).filter((e) => e.date !== mark);
  const days = series.flatMap((s) => s.dates.map(toDay)).concat(mark ? [toDay(mark)] : [], events.map((e) => toDay(e.date)));
  const startDay = Math.min(...days), endDay = Math.max(...days);
  const values = series.flatMap((s) => s.values).filter((v) => v != null);
  const vMin = zero ? 0 : Math.min(...values), vMax = Math.max(...values);
  const pad = (vMax - vMin) * 0.08 || 1;
  const yTicks = niceTicks(zero ? 0 : vMin - pad, vMax + pad);
  const yLo = zero ? 0 : Math.min(vMin - pad, yTicks[0]), yHi = Math.max(vMax + pad, yTicks.at(-1));

  const x = (day) => M.l + ((day - startDay) / (endDay - startDay || 1)) * (W - M.l - M.r);
  const y = (v) => H - M.b - ((v - yLo) / (yHi - yLo || 1)) * (H - M.t - M.b);

  const bySensor = {};
  const lines = series.map((s) => {
    const key = sensorKey(s.sensor);
    const index = (bySensor[key] = (bySensor[key] ?? -1) + 1);
    const color = SENSOR_COLORS[key], dash = DASHES[index % DASHES.length];
    let path = "", pen = false;
    s.dates.forEach((d, i) => {
      const v = s.values[i];
      if (v == null) pen = false;
      else { path += `${pen ? "L" : "M"}${x(toDay(d)).toFixed(1)} ${y(v).toFixed(1)}`; pen = true; }
    });
    return { s, color, dash, path };
  });

  const changeX = mark ? x(toDay(mark)) : null;
  const cursor = el("line", { y1: M.t, y2: H - M.b, class: "chart-cursor", visibility: "hidden" });
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart-svg", role: "img",
    "aria-label": `${axis} over time, ${series.length} lines.${mark ? ` The change was first seen on ${mark}.` : ""}` },
    ...yTicks.map((t) => el("g", {},
      el("line", { x1: M.l, x2: W - M.r, y1: y(t), y2: y(t), stroke: "#e1e5e8" }),
      el("text", { x: M.l - 6, y: y(t) + 3, "text-anchor": "end", class: "chart-tick" }, String(t)))),
    ...monthTicks(startDay, endDay).map((t) => el("g", {},
      el("line", { x1: x(t.day), x2: x(t.day), y1: H - M.b, y2: H - M.b + 4, stroke: "#8a949b" }),
      el("text", { x: x(t.day), y: H - M.b + 16, "text-anchor": x(t.day) > W - M.r - 16 ? "end" : "middle", class: "chart-tick" }, t.label))),
    el("line", { x1: M.l, x2: W - M.r, y1: H - M.b, y2: H - M.b, stroke: "#8a949b" }),
    ...events.map((e) => el("g", {},
      el("title", {}, `${e.date}: ${e.label}`),
      el("line", { x1: x(toDay(e.date)), x2: x(toDay(e.date)), y1: M.t, y2: H - M.b, stroke: "#8a949b", "stroke-dasharray": "1 3" }),
      el("path", { d: `M${x(toDay(e.date)) - 4} ${H - M.b} l4 -7 l4 7z`, fill: "#555" }))),
    ...(mark ? [
      el("line", { x1: changeX, x2: changeX, y1: M.t - 4, y2: H - M.b, stroke: "#B3261E", "stroke-width": 1.6, "stroke-dasharray": "5 3" }),
      el("text", { x: changeX + (changeX > W * 0.6 ? -4 : 4), y: M.t - 8, "text-anchor": changeX > W * 0.6 ? "end" : "start", class: "chart-flag" }, "Change first seen"),
    ] : []),
    ...lines.map((l) => el("path", { d: l.path, fill: "none", stroke: l.color, "stroke-width": 2, "stroke-dasharray": l.dash || null, "stroke-linejoin": "round" })),
    // Few satellite passes (e.g. 2): show each measurement as a dot, so a straight line is not read as a continuous trend.
    ...lines.filter((l) => l.s.dates.length <= DOT_MAX).flatMap((l) =>
      l.s.dates.flatMap((d, i) => (l.s.values[i] == null ? [] : [el("circle", { cx: x(toDay(d)), cy: y(l.s.values[i]), r: 3, fill: l.color, stroke: "#fff", "stroke-width": 1 })]))),
    el("text", { x: 0, y: 0, transform: `translate(11 ${(M.t + H - M.b) / 2}) rotate(-90)`, "text-anchor": "middle", class: "chart-axis" }, axis),
    cursor
  );
  // The slider line: follows the date, hidden before the chart starts, pinned to the right edge after it ends
  // (the slider opens on and play stops at the site's last day, usually after the last measurement).
  const setCursor = (iso) => {
    const day = iso ? toDay(iso) : NaN;
    const shown = day >= startDay;
    cursor.setAttribute("visibility", shown ? "visible" : "hidden");
    if (shown) for (const k of ["x1", "x2"]) cursor.setAttribute(k, x(Math.min(day, endDay)).toFixed(1));
  };
  return { svg, lines, events, setCursor };
}

function legendFor(lines, events, label) {
  return h("ul", { class: "chart-legend" },
    lines.map((l) => h("li", {},
      el("svg", { viewBox: "0 0 26 8", width: 26, height: 8, "aria-hidden": "true" },
        el("line", { x1: 0, x2: 26, y1: 4, y2: 4, stroke: l.color, "stroke-width": 2.5, "stroke-dasharray": l.dash || null })),
      h("span", {}, label(l.s)))),
    events.map((e) => h("li", {}, h("span", { class: "tri", "aria-hidden": "true" }, "▲"), h("span", {}, `${e.label}, ${formatDate(e.date)}`)))
  );
}

const usable = (data) => (data?.series ?? []).filter((s) => s.dates?.length);

/** The change card's signal chart. `data` is a series file ({series, events}); `change` is the change's properties. */
export function buildChart(data, change) {
  const series = usable(data);
  if (!series.length) return h("p", { class: "note" }, "No signal history for this change yet.");
  const { svg, lines, events } = draw(series, data, { mark: change.first_date, axis: `Signal strength (${series[0].unit})` });
  return h("div", {}, svg, legendFor(lines, events, (s) => `${s.name} · ${sensorLabel(s.sensor)}`),
    h("p", { class: "note" }, HINTS[change.type] ?? GENERIC_HINT));
}

/** A site story's curve (story.chart): y from 0, series names as the legend, `note` as the caption, a slider line. */
export function buildStoryChart(data, chart) {
  const series = usable(data);
  if (!series.some((s) => s.values?.some((v) => v != null))) return null; // nothing to draw: no chart at all
  const { svg, lines, events, setCursor } = draw(series, data, { zero: true, axis: series[0].unit });
  const node = h("figure", { class: "story-chart" },
    chart.title ? h("figcaption", { class: "story-chart-title" }, chart.title) : null,
    svg, legendFor(lines, events, (s) => s.name),
    chart.note ? h("p", { class: "note" }, chart.note) : null);
  return { node, setDate: setCursor };
}
