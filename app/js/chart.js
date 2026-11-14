// Written by Claude. Signal chart for the change card: plain SVG, one line per series, no library.
import { h, toDay, formatDate, sensorLabel } from "./format.js";

const NS = "http://www.w3.org/2000/svg";
const W = 360, H = 230, M = { l: 46, r: 12, t: 22, b: 30 };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// One color per satellite (Okabe-Ito purple / bluish green, distinct from the verdict colors); line style tells the series apart.
const SENSOR_COLORS = { nisar: "#7B3FA0", sentinel: "#00826A", other: "#555555" };
const DASHES = ["", "7 3", "2 3"];
const sensorKey = (sensor) => (/nisar/i.test(sensor) ? "nisar" : /sentinel/i.test(sensor) ? "sentinel" : "other");

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

/** Build the chart block. `data` is a series file ({series, events}); `change` is the change's properties. */
export function buildChart(data, change) {
  const series = (data?.series ?? []).filter((s) => s.dates?.length);
  if (!series.length) return h("p", { class: "note" }, "No signal history for this change yet.");

  const events = (data.events ?? []).filter((e) => e.date !== change.first_date);
  const days = series.flatMap((s) => s.dates.map(toDay)).concat(toDay(change.first_date), events.map((e) => toDay(e.date)));
  const startDay = Math.min(...days), endDay = Math.max(...days);
  const values = series.flatMap((s) => s.values).filter((v) => v != null);
  const vMin = Math.min(...values), vMax = Math.max(...values);
  const pad = (vMax - vMin) * 0.08 || 1;
  const yTicks = niceTicks(vMin - pad, vMax + pad);
  const yLo = Math.min(vMin - pad, yTicks[0]), yHi = Math.max(vMax + pad, yTicks.at(-1));

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

  const unit = series[0].unit;
  const changeX = x(toDay(change.first_date));
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart-svg", role: "img",
    "aria-label": `Signal over time, ${series.length} lines. The change was first seen on ${change.first_date}.` },
    ...yTicks.map((t) => el("g", {},
      el("line", { x1: M.l, x2: W - M.r, y1: y(t), y2: y(t), stroke: "#e1e5e8" }),
      el("text", { x: M.l - 6, y: y(t) + 3, "text-anchor": "end", class: "chart-tick" }, String(t)))),
    ...monthTicks(startDay, endDay).map((t) => el("g", {},
      el("line", { x1: x(t.day), x2: x(t.day), y1: H - M.b, y2: H - M.b + 4, stroke: "#8a949b" }),
      el("text", { x: x(t.day), y: H - M.b + 16, "text-anchor": "middle", class: "chart-tick" }, t.label))),
    el("line", { x1: M.l, x2: W - M.r, y1: H - M.b, y2: H - M.b, stroke: "#8a949b" }),
    ...events.map((e) => el("g", {},
      el("title", {}, `${e.date}: ${e.label}`),
      el("line", { x1: x(toDay(e.date)), x2: x(toDay(e.date)), y1: M.t, y2: H - M.b, stroke: "#8a949b", "stroke-dasharray": "1 3" }),
      el("path", { d: `M${x(toDay(e.date)) - 4} ${H - M.b} l4 -7 l4 7z`, fill: "#555" }))),
    el("line", { x1: changeX, x2: changeX, y1: M.t - 4, y2: H - M.b, stroke: "#B3261E", "stroke-width": 1.6, "stroke-dasharray": "5 3" }),
    el("text", { x: changeX + (changeX > W * 0.6 ? -4 : 4), y: M.t - 8, "text-anchor": changeX > W * 0.6 ? "end" : "start", class: "chart-flag" }, "Change first seen"),
    ...lines.map((l) => el("path", { d: l.path, fill: "none", stroke: l.color, "stroke-width": 2, "stroke-dasharray": l.dash || null, "stroke-linejoin": "round" })),
    el("text", { x: 0, y: 0, transform: `translate(11 ${(M.t + H - M.b) / 2}) rotate(-90)`, "text-anchor": "middle", class: "chart-axis" }, `Signal strength (${unit})`)
  );

  const legend = h("ul", { class: "chart-legend" },
    lines.map((l) => h("li", {},
      el("svg", { viewBox: "0 0 26 8", width: 26, height: 8, "aria-hidden": "true" },
        el("line", { x1: 0, x2: 26, y1: 4, y2: 4, stroke: l.color, "stroke-width": 2.5, "stroke-dasharray": l.dash || null })),
      h("span", {}, `${l.s.name} · ${sensorLabel(l.s.sensor)}`))),
    events.map((e) => h("li", {}, h("span", { class: "tri", "aria-hidden": "true" }, "▲"), h("span", {}, `${e.label}, ${formatDate(e.date)}`)))
  );

  return h("div", {}, svg, legend, h("p", { class: "note" }, HINTS[change.type] ?? GENERIC_HINT));
}
