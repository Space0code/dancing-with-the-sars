// Written by Claude. NDVI on the change card: one line "NDVI 0.81 → 0.49" in the facts and a small graph of NDVI over time under the
// radar signal graph. Both come from the optional `ndvi` block of series/<id>.json (kb/data-contract.md); without it, nothing is shown.
import { h } from "./format.js";
import { drawChart, legendFor } from "./chart.js";

const EXPLAIN = "NDVI: how green the ground is, from 0 (bare ground) to 1 (dense vegetation).";
const num = (v) => (typeof v === "number" && Number.isFinite(v) && v >= -1 && v <= 1 ? v : null);

const SAME_SEASON = "Medians of clear photos from the same time of year before and after the change (the same comparison as in \"Why this label?\").";

/** "NDVI 0.81 → 0.49": the same-season pair, or "not enough comparable photos" when `before` / `after` are null. */
export function ndviLine(ndvi) {
  const before = num(ndvi?.before), after = num(ndvi?.after);
  if (before != null && after != null) return `NDVI ${before.toFixed(2)} → ${after.toFixed(2)}`;
  return "not enough comparable photos";
}

/** The measurements that can be drawn: parallel `dates` / `values` lists, entries without a valid value dropped. */
function points(ndvi) {
  const dates = Array.isArray(ndvi?.dates) ? ndvi.dates : [];
  const values = Array.isArray(ndvi?.values) ? ndvi.values : [];
  const keep = dates.map((d, i) => [d, num(values[i])]).filter(([d, v]) => /^\d{4}-\d{2}-\d{2}$/.test(d) && v != null);
  return { dates: keep.map(([d]) => d), values: keep.map(([, v]) => v) };
}

/**
 * Fill the card's NDVI parts from a series file. `parts` = {dt, dd, slot}: the hidden "Greenness" row of the facts and the hidden
 * block under the signal chart. Shows only what the data supports.
 */
export function renderNdvi(data, change, { dt, dd, slot }) {
  const ndvi = data?.ndvi;
  if (!ndvi || typeof ndvi !== "object") return;
  const line = ndviLine(ndvi);
  const paired = line.startsWith("NDVI");
  dd.replaceChildren(line, ...(paired ? [h("span", { class: "note" }, " (same time of year)")] : []));
  dd.title = paired ? `${EXPLAIN} ${SAME_SEASON}` : `${EXPLAIN} Fewer than two clear photos from the same time of year on one side of the change.`;
  dt.hidden = dd.hidden = false;
  const { dates, values } = points(ndvi);
  if (dates.length < 2) return;
  const sensor = typeof ndvi.sensor === "string" && ndvi.sensor ? ndvi.sensor : "HLS";
  const { svg, lines } = drawChart([{ name: "NDVI", sensor, dates, values, unit: "NDVI" }], data, {
    mark: change.first_date, zero: Math.min(...values) >= 0, axis: "NDVI",
  });
  slot.replaceChildren(h("h3", {}, "Greenness over time"), svg, legendFor(lines, (s) => `${s.name} · ${s.sensor}`), h("p", { class: "note" }, EXPLAIN));
  slot.hidden = false;
}
