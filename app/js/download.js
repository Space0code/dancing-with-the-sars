// Written by Claude. Three more formats for the Export dialog (export.js): GeoJSON, Shapefile (zip) and GeoTIFF of the selected changes.
// The files themselves are made by geofiles.js; the two libraries (shp-write, geotiff.js) load from a CDN, pinned and integrity-checked,
// only when that format is first used. No map picture goes into these files (only the PDF report has one).
import { registerExportFormat, downloadBlob } from "./export.js";
import { changesGeoJson, shapefileData, dbfBytes, zipStore, rasterize, geotiffMetadata } from "./geofiles.js";

const LIBS = {
  shpwrite: {
    src: "https://cdn.jsdelivr.net/npm/@mapbox/shp-write@0.4.3/shpwrite.js",
    integrity: "sha384-OZN0ldIk+CMjlOe7C8oGHiN/KaZtlkin35SPz2uuvB0g5cY6RoecVzw2zuoFebQB",
  },
  GeoTIFF: {
    src: "https://cdn.jsdelivr.net/npm/geotiff@2.1.3/dist-browser/geotiff.js",
    integrity: "sha384-m5adk5PRgt3JjiYbYoG8oXxc3EgRFKc1aCBgKzyxqxnbYpdiAMlHkR0gVDp03Q/H",
  },
};
const loading = {};

/** Load a library once (a <script> tag) and return its global. */
function library(name) {
  loading[name] ??= new Promise((resolve, reject) => {
    const script = Object.assign(document.createElement("script"), { src: LIBS[name].src, integrity: LIBS[name].integrity, crossOrigin: "anonymous" });
    script.onload = () => (window[name] ? resolve(window[name]) : reject(new Error(`${name} did not start`)));
    script.onerror = () => {
      delete loading[name]; // a later try may work
      reject(new Error("a helper library could not be loaded; check the internet connection"));
    };
    document.head.append(script);
  });
  return loading[name];
}

const need = (ctx) => {
  if (!ctx.changes.length) throw new Error("no changes are selected.");
};
const stem = (ctx) => `parallax-${ctx.site.id}`;
const text = (s) => new TextEncoder().encode(s);

registerExportFormat({
  id: "geojson", label: "GeoJSON", note: "Shapes and labels in one file, with every reason (EPSG:4326).",
  run: async (ctx) => {
    need(ctx);
    const json = JSON.stringify(changesGeoJson(ctx.changes, ctx.kindName));
    downloadBlob(`${stem(ctx)}-changes.geojson`, new Blob([json], { type: "application/geo+json" }));
  },
});

registerExportFormat({
  id: "shapefile", label: "Shapefile (zip)", note: "For QGIS, ArcGIS and other GIS software.",
  run: async (ctx) => {
    need(ctx);
    const shpwrite = await library("shpwrite");
    const { rows, geometries } = shapefileData(ctx.changes, ctx.kindName);
    const parts = await new Promise((resolve, reject) => shpwrite.write(rows, "POLYGON", geometries, (err, files) => (err ? reject(err) : resolve(files))));
    const folder = `${stem(ctx)}-changes/`;
    const zip = zipStore([
      { name: `${folder}changes.shp`, bytes: new Uint8Array(parts.shp.buffer) },
      { name: `${folder}changes.shx`, bytes: new Uint8Array(parts.shx.buffer) },
      { name: `${folder}changes.dbf`, bytes: dbfBytes(rows) },
      { name: `${folder}changes.prj`, bytes: text(parts.prj) },
      { name: `${folder}changes.cpg`, bytes: text("UTF-8") },
    ]);
    downloadBlob(`${stem(ctx)}-changes.zip`, new Blob([zip], { type: "application/zip" }));
  },
});

registerExportFormat({
  id: "geotiff", label: "GeoTIFF", note: "Raster of about 10 m pixels. Values: 1 expected, 2 needs review, 3 high concern, 4 not labelled, 0 no change.",
  run: async (ctx) => {
    need(ctx);
    const GeoTIFF = await library("GeoTIFF");
    const raster = rasterize(ctx.changes);
    const tiff = await GeoTIFF.writeArrayBuffer(raster.data, geotiffMetadata(raster));
    downloadBlob(`${stem(ctx)}-label-class.tif`, new Blob([tiff], { type: "image/tiff" }));
  },
});
