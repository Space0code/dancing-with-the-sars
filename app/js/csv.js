// Written by Claude. CSV export of the Changes list (the Download button in the Changes tab).
// UTF-8 with a byte-order mark so Excel opens accents correctly. Text cells that start with = + - @ get a leading apostrophe
// (spreadsheet formula injection: reason texts come from data files).
import { VERDICTS, verdictKey, safeUrl } from "./format.js";

const COLUMNS = ["id", "site", "kind", "size_ha", "first_seen", "label", "main_reason", "source_link", "centre_lon", "centre_lat"];

/** Centre of the bounding box of a Polygon / MultiPolygon geometry, as [lon, lat] (or [null, null]). */
function centre(geometry) {
  const points = [];
  const walk = (c) => (typeof c?.[0] === "number" ? points.push(c) : c?.forEach(walk));
  walk(geometry?.coordinates);
  if (!points.length) return [null, null];
  const lons = points.map((p) => p[0]);
  const lats = points.map((p) => p[1]);
  return [(Math.min(...lons) + Math.max(...lons)) / 2, (Math.min(...lats) + Math.max(...lats)) / 2];
}

const cell = (value) => {
  if (value == null) return "";
  let text = String(value);
  if (typeof value === "string" && /^[=+\-@\t\r]/.test(text)) text = "'" + text;
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};

/** CSV text for these features, in the order given. `kindName(type)` gives the short readable kind. */
export function changesCsv(features, kindName) {
  const rows = features.map((f) => {
    const p = f.properties;
    const reason = p.reasons?.[0]; // the deciding reason comes first
    const [lon, lat] = centre(f.geometry);
    return [
      p.id, p.site, kindName(p.type), Math.round(p.area_ha * 100) / 100, p.first_date, VERDICTS[verdictKey(p.verdict)].label,
      reason?.text ?? "", safeUrl(reason?.url) ?? "", lon == null ? null : lon.toFixed(5), lat == null ? null : lat.toFixed(5),
    ];
  });
  return "﻿" + [COLUMNS, ...rows].map((row) => row.map(cell).join(",")).join("\r\n") + "\r\n";
}

/** Hand the text to the browser as a file download. */
export function downloadText(filename, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
