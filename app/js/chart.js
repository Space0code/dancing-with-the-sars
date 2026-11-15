// Written by Claude. Charts in plain SVG, one line per series, no library: the signal chart on the change card and
// the site overview's graph of cumulative changed area (built from the changes themselves).
import { h, toDay, sensorLabel, VERDICTS, verdictKey } from "./format.js";

const NS = "http://www.w3.org/2000/svg";
const W = 360, H = 230, M = { l: 46, r: 12, t: 22, b: 30 };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// One color per satellite (Okabe-Ito purple / bluish green, distinct from the verdict colors); line style tells the series apart.
const SENSOR_COLORS = { nisar: "#7B3FA0", sentinel: "#00826A", optical: "#9A6A00", other: "#555555" };
const DASHES = ["", "7 3", "2 3"];
const DOT_MAX = 15; // lines with at most this many points get a dot per measurement
const sensorKey = (sensor) =>
  /nisar/i.test(sensor) ? "nisar" : /sentinel[- ]?1|^s1\b/i.test(sensor) ? "sentinel" : /optic|dist|hls|landsat|sentinel-?2/i.test(sensor) ? "optical" : "other";

const HINT = "Radar signal over time. A lasting step means the ground changed.";

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
  const step = span <= 400 ? 2 : span <= 1200 ? 6 : span <= 2400 ? 12 : 24;
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
 * `zero` = the y-axis starts at 0, `axis` = the y-axis label. Returns {svg, lines, setCursor(iso|null)}.
 */
function draw(series, data, { mark = null, marks = [], zero = false, axis }) {
  const days = series.flatMap((s) => s.dates.map(toDay)).concat(mark ? [toDay(mark)] : [], marks.map((m) => toDay(m.date)));
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
    const color = s.color ?? SENSOR_COLORS[key], dash = s.color ? "" : DASHES[index % DASHES.length];
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
    ...(mark ? [
      el("line", { x1: changeX, x2: changeX, y1: M.t - 4, y2: H - M.b, stroke: "#B3261E", "stroke-width": 1.6, "stroke-dasharray": "5 3" }),
      el("text", { x: changeX + (changeX > W * 0.6 ? -4 : 4), y: M.t - 8, "text-anchor": changeX > W * 0.6 ? "end" : "start", class: "chart-flag" }, "Change first seen"),
    ] : []),
    // First sighting of each source: a small labelled tick on the axis (staggered, so close dates don't print over each other)
    ...marks.flatMap((m, i) => {
      const mx = x(toDay(m.date)), right = mx > W * 0.65, ly = H - M.b - 10 - (i % 2) * 11;
      return [
        el("line", { x1: mx, x2: mx, y1: H - M.b, y2: ly + 2, stroke: m.color, "stroke-width": 2 }),
        el("text", { x: mx + (right ? -3 : 3), y: ly, "text-anchor": right ? "end" : "start", class: "chart-tick", fill: m.color }, m.label),
      ];
    }),
    ...lines.map((l) => el("path", { d: l.path, fill: "none", stroke: l.color, "stroke-width": 2, "stroke-dasharray": l.dash || null, "stroke-linejoin": "round" })),
    // Few satellite passes (e.g. 2): show each measurement as a dot, so a straight line is not read as a continuous trend.
    ...lines.filter((l) => l.s.dates.length <= DOT_MAX && !l.s.color).flatMap((l) =>
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
  return { svg, lines, setCursor };
}

function legendFor(lines, label) {
  return h("ul", { class: "chart-legend" },
    lines.map((l) => h("li", {},
      el("svg", { viewBox: "0 0 26 8", width: 26, height: 8, "aria-hidden": "true" },
        el("line", { x1: 0, x2: 26, y1: 4, y2: 4, stroke: l.color, "stroke-width": 2.5, "stroke-dasharray": l.dash || null })),
      h("span", {}, label(l.s))))
  );
}

const usable = (data) => (data?.series ?? []).filter((s) => s.dates?.length);

/** The change card's signal chart. `data` is a series file ({series}); `change` is the change's properties. */
export function buildChart(data, change) {
  const series = usable(data);
  if (!series.length) return h("p", { class: "note" }, "No signal history for this change yet.");
  // each source's first sighting of the change ("NISAR saw it"); none for data without `sources`
  const marks = (change.sources ?? []).filter((s) => s.first_date).sort((a, b) => a.first_date.localeCompare(b.first_date)).map((s) => {
    const key = sensorKey(s.sensor);
    return { date: s.first_date, color: SENSOR_COLORS[key], label: `${key === "nisar" ? "NISAR" : key === "sentinel" ? "Sentinel-1" : key === "optical" ? "Optical" : s.sensor} first saw it` };
  });
  const { svg, lines } = draw(series, data, { mark: change.first_date, marks, axis: `Signal strength (${series[0].unit})` });
  return h("div", {}, svg, legendFor(lines, (s) => `${s.name} · ${sensorLabel(s.sensor)}`),
    h("p", { class: "note" }, HINT));
}

/**
 * The site overview's graph: cumulative area of detected change over time, one line per label (a single line when no
 * change has a label). `features` are the site's changes; `range` = [first, last] day of the site. Has a slider line.
 */
export function buildAreaChart(features, range) {
  const groups = new Map(); // label key -> changes
  for (const f of features) {
    const key = verdictKey(f.properties.verdict);
    groups.set(key, [...(groups.get(key) ?? []), f]);
  }
  const judged = [...groups.keys()].some((key) => key !== "none");
  const order = ["high_concern", "review", "expected", "none"];
  const series = [...groups]
    .sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]))
    .map(([key, list]) => {
      const sorted = list.slice().sort((a, b) => a.properties.first_date.localeCompare(b.properties.first_date));
      const dates = [range[0]], values = [0];
      let total = 0;
      for (const f of sorted) {
        dates.push(f.properties.first_date, f.properties.first_date); // a step: up at the day it was first seen
        values.push(Math.round(total * 10) / 10);
        total += f.properties.area_ha;
        values.push(Math.round(total * 10) / 10);
      }
      dates.push(range[1]);
      values.push(values.at(-1));
      return { name: judged ? VERDICTS[key].label : "All changes", color: judged ? VERDICTS[key].color : "#0a0a0a", dates, values, unit: "ha" };
    });
  if (!series.length) return null;
  const { svg, lines, setCursor } = draw(series, {}, { zero: true, axis: "Cumulative area (ha)" });
  return { node: h("figure", { class: "area-chart" }, svg, legendFor(lines, (s) => s.name)), setDate: setCursor };
}

// The NDVI graph on the change card (ndvi.js) draws with the same plot and legend.
export { draw as drawChart, legendFor };
