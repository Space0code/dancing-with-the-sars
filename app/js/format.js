// Written by Claude. Shared wording, colors and small helpers. Plain language only: no radar jargon, never "illegal".

// The app's name and pitch live only here (working name; the team picks the final one).
export const APP = {
  name: "SARwatch",
  pitch: "Radar satellites see the ground through clouds and at night. This map shows where the land changed, and which changes deserve a second look.",
};

// Okabe-Ito colorblind-safe palette. The map draws a dark casing around each polygon so all three read on both basemaps.
export const VERDICTS = {
  expected: { label: "Expected", color: "#0072B2" },
  review: { label: "Needs review", color: "#F0E442" },
  high_concern: { label: "High concern", color: "#D55E00" },
  none: { label: "Not judged yet", color: "#9AA3A8" },
};
export const verdictKey = (verdict) => (Object.hasOwn(VERDICTS, verdict) ? verdict : "none"); // null or unknown = not judged yet

const CHANGE_LABELS = {
  clearing: "Forest clearing",
  structure: "New building or structure",
  earthworks: "Earth moved (grading, digging or filling)",
  ground_motion: "Ground sinking or rising",
  fire: "Burned area",
  other: "Other change",
};
export const changeLabel = (type) => CHANGE_LABELS[type] ?? "Change";

const CONFIDENCE = { high: "High", medium: "Medium", low: "Low" };
export const confidenceLabel = (c) => CONFIDENCE[c] ?? "Unknown";

export function sensorLabel(sensor) {
  if (/nisar/i.test(sensor)) return "NISAR radar satellite";
  if (/sentinel-1/i.test(sensor)) return "Sentinel-1 radar satellite";
  if (/sentinel-2|optical|hls/i.test(sensor)) return "Optical satellite";
  return sensor;
}

export function setVerdictColors() {
  for (const [key, v] of Object.entries(VERDICTS)) document.documentElement.style.setProperty(`--c-${key}`, v.color);
}

// --- dates: ISO strings (YYYY-MM-DD) in UTC, so string comparison equals date comparison ---
const DAY_MS = 86400000;
const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
export const toDay = (iso) => Math.round(Date.parse(iso) / DAY_MS);
export const fromDay = (day) => new Date(day * DAY_MS).toISOString().slice(0, 10);
export const formatDate = (iso) => dateFmt.format(new Date(iso));

export function formatArea(ha) {
  return `${ha >= 10 ? Math.round(ha) : ha.toFixed(1)} ha`;
}

export function runningTotal(count, ha) {
  return `${count} ${count === 1 ? "change" : "changes"} · ${formatArea(ha)} so far`;
}

// --- tiny DOM builder (text goes through text nodes, so data can never inject HTML) ---
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child != null && child !== false) el.append(child.nodeType ? child : document.createTextNode(child));
  }
  return el;
}

export const safeUrl = (url) => (typeof url === "string" && /^https?:\/\//i.test(url) ? url : null);
