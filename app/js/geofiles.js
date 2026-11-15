// Written by Claude. The contents of the GeoJSON, Shapefile and GeoTIFF downloads (registered in download.js): pure functions,
// no DOM, so they can be tested in Node. Properties follow the CSV columns (csv.js); no map picture goes into these files.
import { VERDICTS, verdictKey, safeUrl } from "./format.js";
import { centre } from "./csv.js";

/** Label class written to the GeoTIFF: 0 = no change here. */
export const LABEL_CLASS = { expected: 1, review: 2, high_concern: 3, none: 4 };
// Where changes overlap, the more serious label is drawn last (so it wins); "not labelled" never hides a label.
const DRAW_ORDER = ["none", "expected", "review", "high_concern"];

const round = (n, digits) => (typeof n === "number" ? Number(n.toFixed(digits)) : null);

/** The properties shared by every format (the CSV columns). */
function baseProps(f, kindName) {
  const p = f.properties;
  const [lon, lat] = centre(f.geometry);
  return {
    id: p.id, site: p.site, kind: kindName(p.type), size_ha: round(p.area_ha, 2), first_seen: p.first_date,
    label: VERDICTS[verdictKey(p.verdict)].label, main_reason: p.reasons?.[0]?.text ?? "", source_link: safeUrl(p.reasons?.[0]?.url) ?? "",
    centre_lon: round(lon, 5), centre_lat: round(lat, 5),
  };
}

/** One FeatureCollection (EPSG:4326, as stored) with the CSV properties plus every reason. */
export function changesGeoJson(features, kindName) {
  return {
    type: "FeatureCollection",
    features: features.map((f) => ({
      type: "Feature",
      geometry: f.geometry,
      properties: {
        ...baseProps(f, kindName),
        reasons: (f.properties.reasons ?? []).map((r) => ({ text: r.text ?? "", source: r.source ?? "", url: safeUrl(r.url) ?? "", effect: r.effect ?? "" })),
      },
    })),
  };
}

// ---- Shapefile ----------------------------------------------------------------------------------------------------------
// shp-write (a pinned CDN library) writes the .shp / .shx parts. Its own .dbf and .zip are not used: its dBase writer keeps one
// byte per character (it garbles accents and dashes) and its zip step overwrites the Polygon layer with the MultiPolygon one.
// So the .dbf (UTF-8, with a .cpg file) and the zip are made here.

// dBase: field names of at most 10 characters, text of at most 254 bytes.
const DBF_COLUMNS = [
  ["id", "id", "C"], ["site", "site", "C"], ["kind", "kind", "C"], ["size_ha", "size_ha", "N", 2], ["first_seen", "first_seen", "C"],
  ["label", "label", "C"], ["reason", "main_reason", "C"], ["link", "source_link", "C"], ["lon", "centre_lon", "N", 5], ["lat", "centre_lat", "N", 5],
];
const encoder = new TextEncoder();

/** Cut text to at most `max` bytes of UTF-8 without splitting a character. */
function clip(text, max) {
  let out = String(text);
  while (encoder.encode(out).length > max) out = out.slice(0, -1);
  return out;
}

const area = (ring) => ring.reduce((sum, [x, y], i) => sum + (i ? (ring[i - 1][0] * y - x * ring[i - 1][1]) : 0), 0) / 2;
/** Shapefile rings: outer rings run clockwise, holes counter-clockwise (GeoJSON is the other way round). */
const orient = (ring, clockwise) => ((area(ring) < 0) === clockwise ? ring : ring.slice().reverse());

/** Rows (dBase values by short field name) and shapes ([polygon][ring][point], every shape a multi-part polygon) for the shapefile. */
export function shapefileData(features, kindName) {
  const rows = [];
  const geometries = [];
  for (const f of features) {
    const polygons = polygonsOf(f.geometry);
    if (!polygons.length) continue;
    const props = baseProps(f, kindName);
    rows.push(Object.fromEntries(DBF_COLUMNS.map(([name, from]) => [name, props[from]])));
    geometries.push(polygons.map((rings) => rings.map((ring, i) => orient(ring, i === 0))));
  }
  return { rows, geometries };
}

/** A dBase III file (bytes) for these rows; text is UTF-8 (say so in a .cpg file next to it). */
export function dbfBytes(rows, now = new Date()) {
  const cols = DBF_COLUMNS.map(([name, , type, decimals]) => {
    const cells = rows.map((r) => (r[name] == null ? "" : type === "N" ? Number(r[name]).toFixed(decimals) : clip(r[name], 254)));
    const width = Math.min(254, Math.max(1, ...cells.map((c) => encoder.encode(c).length)));
    return { name, type, decimals: decimals ?? 0, width, cells };
  });
  const headerLength = 32 + 32 * cols.length + 1;
  const recordLength = 1 + cols.reduce((n, c) => n + c.width, 0);
  const bytes = new Uint8Array(headerLength + recordLength * rows.length + 1);
  const view = new DataView(bytes.buffer);
  bytes[0] = 0x03;
  bytes[1] = now.getFullYear() - 1900; bytes[2] = now.getMonth() + 1; bytes[3] = now.getDate();
  view.setUint32(4, rows.length, true);
  view.setUint16(8, headerLength, true);
  view.setUint16(10, recordLength, true);
  cols.forEach((c, i) => {
    const at = 32 + 32 * i;
    bytes.set(encoder.encode(c.name), at); // names are short ASCII; the rest of the 11 bytes stays 0
    bytes[at + 11] = c.type.charCodeAt(0);
    bytes[at + 16] = c.width;
    bytes[at + 17] = c.decimals;
  });
  bytes[headerLength - 1] = 0x0d;
  rows.forEach((_, r) => {
    let at = headerLength + r * recordLength;
    bytes[at++] = 0x20; // not deleted
    for (const c of cols) {
      const raw = encoder.encode(c.cells[r]);
      const field = new Uint8Array(c.width).fill(0x20);
      if (c.type === "N") field.set(raw, c.width - raw.length); // numbers: right-aligned
      else field.set(raw);
      bytes.set(field, at);
      at += c.width;
    }
  });
  bytes[bytes.length - 1] = 0x1a;
  return bytes;
}

const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
const crc32 = (bytes) => {
  let c = 0xffffffff;
  for (const b of bytes) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
};

/** A zip file (bytes, stored without compression) of `files` = [{name, bytes}]. */
export function zipStore(files, now = new Date()) {
  const time = (now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1);
  const date = ((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate();
  const parts = [];
  const central = [];
  let offset = 0;
  for (const { name, bytes } of files) {
    const nameBytes = encoder.encode(name);
    const crc = crc32(bytes);
    const local = new DataView(new ArrayBuffer(30));
    [[0, 0x04034b50, 4], [4, 20, 2], [6, 0x0800, 2], [8, 0, 2], [10, time, 2], [12, date, 2], [14, crc, 4], [18, bytes.length, 4], [22, bytes.length, 4], [26, nameBytes.length, 2], [28, 0, 2]]
      .forEach(([at, value, size]) => (size === 4 ? local.setUint32(at, value, true) : local.setUint16(at, value, true)));
    parts.push(new Uint8Array(local.buffer), nameBytes, bytes);
    const entry = new DataView(new ArrayBuffer(46));
    [[0, 0x02014b50, 4], [4, 20, 2], [6, 20, 2], [8, 0x0800, 2], [10, 0, 2], [12, time, 2], [14, date, 2], [16, crc, 4], [20, bytes.length, 4], [24, bytes.length, 4], [28, nameBytes.length, 2], [30, 0, 2], [32, 0, 2], [34, 0, 2], [36, 0, 2], [38, 0, 4], [42, offset, 4]]
      .forEach(([at, value, size]) => (size === 4 ? entry.setUint32(at, value, true) : entry.setUint16(at, value, true)));
    central.push(new Uint8Array(entry.buffer), nameBytes);
    offset += 30 + nameBytes.length + bytes.length;
  }
  const centralSize = central.reduce((n, p) => n + p.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(8, files.length, true);
  end.setUint16(10, files.length, true);
  end.setUint32(12, centralSize, true);
  end.setUint32(16, offset, true);
  const all = [...parts, ...central, new Uint8Array(end.buffer)];
  const out = new Uint8Array(all.reduce((n, p) => n + p.length, 0));
  let at = 0;
  for (const p of all) { out.set(p, at); at += p.length; }
  return out;
}

/** Walk a Polygon / MultiPolygon into a list of polygons, each a list of rings of [lon, lat]. */
function polygonsOf(geometry) {
  if (geometry?.type === "Polygon") return [geometry.coordinates];
  if (geometry?.type === "MultiPolygon") return geometry.coordinates;
  return [];
}

/**
 * Draw the changes on a grid: one byte per pixel, LABEL_CLASS or 0. Pixels are about `metres` wide, but the grid is never
 * larger than `maxSide` x `maxSide` (coarser pixels for a big area). Georeferenced in EPSG:4326 (north-up, `dx` / `dy` in degrees).
 * Returns {width, height, west, north, dx, dy, data, metres}; throws when there is nothing to draw.
 */
export function rasterize(features, { metres = 10, maxSide = 4000 } = {}) {
  const polys = features.map((f) => ({ cls: LABEL_CLASS[verdictKey(f.properties.verdict)], polygons: polygonsOf(f.geometry) })).filter((x) => x.polygons.length);
  if (!polys.length) throw new Error("There is nothing to draw: no changes are selected.");
  let west = Infinity, south = Infinity, east = -Infinity, north = -Infinity;
  for (const { polygons } of polys) for (const poly of polygons) for (const ring of poly) for (const [x, y] of ring) {
    west = Math.min(west, x); east = Math.max(east, x); south = Math.min(south, y); north = Math.max(north, y);
  }
  const DEG_M = 111320; // metres per degree of latitude
  let dy = metres / DEG_M;
  let dx = dy / Math.cos((((north + south) / 2) * Math.PI) / 180);
  let width = Math.max(1, Math.ceil((east - west) / dx));
  let height = Math.max(1, Math.ceil((north - south) / dy));
  const scale = Math.max(1, width / maxSide, height / maxSide);
  if (scale > 1) {
    dx *= scale; dy *= scale;
    width = Math.max(1, Math.ceil((east - west) / dx));
    height = Math.max(1, Math.ceil((north - south) / dy));
  }
  const data = new Uint8Array(width * height);

  for (const key of DRAW_ORDER) {
    for (const { cls, polygons } of polys.filter((x) => x.cls === LABEL_CLASS[key])) {
      for (const poly of polygons) {
        let drawn = 0;
        const edges = [];
        for (const ring of poly) for (let i = 0; i < ring.length - 1; i++) edges.push([ring[i], ring[i + 1]]);
        let ymin = Infinity, ymax = -Infinity, xmin = Infinity, xmax = -Infinity;
        for (const [[ax, ay]] of edges) { ymin = Math.min(ymin, ay); ymax = Math.max(ymax, ay); xmin = Math.min(xmin, ax); xmax = Math.max(xmax, ax); }
        const r0 = Math.max(0, Math.floor((north - ymax) / dy - 0.5));
        const r1 = Math.min(height - 1, Math.ceil((north - ymin) / dy - 0.5));
        for (let r = r0; r <= r1; r++) {
          const y = north - (r + 0.5) * dy; // centre of the pixel row
          const xs = [];
          for (const [[ax, ay], [bx, by]] of edges) {
            if ((ay <= y) !== (by <= y)) xs.push(ax + ((y - ay) / (by - ay)) * (bx - ax)); // even-odd rule: holes stay empty
          }
          xs.sort((a, b) => a - b);
          for (let i = 0; i + 1 < xs.length; i += 2) {
            const c0 = Math.max(0, Math.ceil((xs[i] - west) / dx - 0.5));
            const c1 = Math.min(width - 1, Math.ceil((xs[i + 1] - west) / dx - 0.5) - 1);
            for (let c = c0; c <= c1; c++) { data[r * width + c] = cls; drawn++; }
          }
        }
        if (!drawn) { // smaller than a pixel: still mark one pixel, so no change disappears from the file
          const c = Math.min(width - 1, Math.max(0, Math.floor(((xmin + xmax) / 2 - west) / dx)));
          const r = Math.min(height - 1, Math.max(0, Math.floor((north - (ymin + ymax) / 2) / dy)));
          data[r * width + c] = cls;
        }
      }
    }
  }
  return { width, height, west, north, dx, dy, data, metres: Math.round(dy * DEG_M) };
}

/** The tags for geotiff.js `writeArrayBuffer(data, metadata)`: one 8-bit band, north-up, WGS 84, 0 = no data. */
export function geotiffMetadata(r) {
  return {
    width: r.width, height: r.height, SamplesPerPixel: 1, BitsPerSample: [8], SampleFormat: [1], PhotometricInterpretation: 1,
    ModelPixelScale: [r.dx, r.dy, 0], ModelTiepoint: [0, 0, 0, r.west, r.north, 0],
    GTModelTypeGeoKey: 2, GTRasterTypeGeoKey: 1, GeographicTypeGeoKey: 4326, GeogCitationGeoKey: "WGS 84", GDAL_NODATA: "0",
  };
}
