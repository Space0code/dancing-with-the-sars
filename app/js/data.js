// Written by Claude. Loads data/sites.json and one site's files. All paths are relative so GitHub Pages sub-paths work.

export const loadJson = (path) => getJson(path);

async function getJson(path, optional = false) {
  try {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return await res.json();
  } catch (err) {
    if (optional) return null;
    throw new Error(`Could not load ${path}: ${err.message}`);
  }
}

export async function loadSites() {
  return (await getJson("data/sites.json")).sites;
}

export async function loadSite(site) {
  const base = `data/${site.id}/`;
  const [changes, frames, stages] = await Promise.all([
    getJson(`${base}changes.geojson`),
    getJson(`${base}frames.json`, true), // optional: without it the map shows only the background
    getJson(`${base}stages.geojson`, true), // optional: one outline that grows (kb/data-contract.md)
  ]);
  return { site, base, changes, frames, stages };
}
