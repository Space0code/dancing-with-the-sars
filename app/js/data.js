// Written by Claude. Loads data/sites.json and one site's files. All paths are relative so GitHub Pages sub-paths work.

export const loadJson = (path) => getJson(path);

/** fetch with one retry after a server error (5xx) or a dropped connection: the static host now and then answers 503 for a moment,
 * and an optional file (frames.json) that fails once must not make the site silently lose its pictures. A 404 is not retried. */
async function fetchWithRetry(path) {
  const first = await fetch(path).catch(() => null);
  if (first && first.status < 500) return first;
  await new Promise((resolve) => setTimeout(resolve, 400));
  return fetch(path);
}

async function getJson(path, optional = false) {
  try {
    const res = await fetchWithRetry(path);
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
