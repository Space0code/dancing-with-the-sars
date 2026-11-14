// Written by Claude. What the user has selected on the open site: an area (GeoJSON Polygon / MultiPolygon, EPSG:4326) and a
// time frame (ISO dates, either end may be null = open). Everything that shows or counts changes passes them through
// filterChanges(); with nothing selected it returns the list unchanged.
//
// API
//   getSelection()            -> {area, from, to} (a copy)
//   setArea(geometryOrNull)   -> select an area (null removes it)
//   setTimeFrame(from, to)    -> ISO dates "YYYY-MM-DD" or null
//   clearSelection()          -> area and time frame both removed
//   isActive()                -> true when an area or a date is set
//   onSelectionChange(cb)     -> cb(selection) after every change; returns an unsubscribe function
//   filterChanges(features)   -> the features whose first_date..last_date span touches from..to AND that intersect the area
//   describeSelection()       -> short text for the UI, e.g. "area · 3 Jun 2026 to 1 Aug 2026" ("" when nothing is selected)
// Turf (global `turf`, loaded in index.html) does the exact intersection test; without it a bounding-box test is used.

let area = null;
let from = null;
let to = null;
const listeners = new Set();

const emit = () => {
  const now = getSelection();
  for (const cb of [...listeners]) cb(now);
};

export const getSelection = () => ({ area, from, to });
export const isActive = () => Boolean(area || from || to);

export function setArea(geometry) {
  area = geometry && /^(Multi)?Polygon$/.test(geometry.type) ? geometry : null;
  emit();
}

export function setTimeFrame(start, end) {
  from = start || null;
  to = end || null;
  emit();
}

export function clearSelection() {
  if (!isActive()) return;
  area = from = to = null;
  emit();
}

export function onSelectionChange(cb) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

function bbox(geometry) {
  const box = [Infinity, Infinity, -Infinity, -Infinity];
  const walk = (c) => {
    if (typeof c[0] === "number") {
      box[0] = Math.min(box[0], c[0]); box[1] = Math.min(box[1], c[1]);
      box[2] = Math.max(box[2], c[0]); box[3] = Math.max(box[3], c[1]);
    } else c.forEach(walk);
  };
  walk(geometry.coordinates);
  return box;
}

function intersects(geometry) {
  if (!geometry) return false;
  const a = bbox(area);
  const b = bbox(geometry);
  if (a[0] > b[2] || b[0] > a[2] || a[1] > b[3] || b[1] > a[3]) return false; // boxes apart: cheap exit
  return window.turf ? turf.booleanIntersects(area, geometry) : true;
}

export function filterChanges(features) {
  if (!isActive()) return features;
  return features.filter((f) => {
    const p = f.properties;
    const last = p.last_date ?? p.first_date;
    if (from && last < from) return false;
    if (to && p.first_date > to) return false;
    return !area || intersects(f.geometry);
  });
}

const DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const day = (iso) => DAY.format(new Date(iso));

export function describeSelection() {
  const parts = [];
  if (area) parts.push("area");
  if (from && to) parts.push(`${day(from)} to ${day(to)}`);
  else if (from) parts.push(`from ${day(from)}`);
  else if (to) parts.push(`until ${day(to)}`);
  return parts.join(" · ");
}
