# Dancing with the SARs (SARwatch)

NASA Space Apps Challenge 2026, Barcelona. An interactive map that uses **radar satellites** (NASA-ISRO **NISAR** and
Copernicus **Sentinel-1**) to watch the land and tell a regulator **which changes look expected and which need a look**.

![The app showing the fake example site: coloured outlines on the map, a time slider below](docs/screenshots/48-readme.jpg)

*The app on its clearly labelled fake example site (the screenshot shows no real data).*

- **Radar sees through clouds and at night**, so it can follow a site month after month where optical photos cannot.
- It finds where the ground changed: **forest clearing, new buildings, earthworks, ground sinking**.
- Each change gets a plain-language verdict: **expected** · **needs review** · **high concern**, with the reasons
  (protected areas, zoning, cadastre, solar-plant list, official records) next to the radar evidence.
- Click a change to see a before/after swipe and the radar signal over time; move the time slider to replay the site.
- Pilot: **Catalonia**, plus the 2026 **Finland (Muhos)** forest clearing as a test case.

What we build and why: [kb/product.md](kb/product.md) · how: [kb/plan.md](kb/plan.md) ·
new to radar? [kb/sar-primer.md](kb/sar-primer.md).

## Run it

The app is static (no build step, no npm, no API keys):

```
python -m http.server 8000 -d app      # then open http://localhost:8000
```

Add `#site=<id>` to the URL to open a site directly. Sites with `"ready": true` in `app/data/sites.json` appear in the
switcher. App notes: [app/README.md](app/README.md).

On GitHub Pages it is served from `https://space0code.github.io/dancing-with-the-sars/`; the workflow
`.github/workflows/pages.yml` publishes `app/` as it is.

## Rebuild the data

The app reads plain files in `app/data/` (format: [kb/data-contract.md](kb/data-contract.md)). The Python package in
`src/sarwatch/` makes them from real radar data.

```
pip install -e '.[radar,verdict,dev]'              # Python 3.11+
export EARTHDATA_TOKEN=...                         # free NASA Earthdata Login token (urs.earthdata.nasa.gov > Generate Token)
python -m sarwatch.pipeline muhos                  # NISAR + Sentinel-1 -> app/data/muhos/
python -m sarwatch.contract app/data               # check that the files follow the contract
python -m pytest                                   # tests (offline)
```

Radar files are large (NISAR granules are 2-7 GB): the readers fetch only the site's window, and cache small per-date
files under `data/` (gitignored). The fake example site comes from `explore/fixture/make_fixture.py`. A Codespace setup
is in `.devcontainer/`.

## Data sources and credits

| What | Provider | Terms |
|---|---|---|
| NISAR L-band radar (GCOV) | NASA / ISRO, via the [ASF DAAC](https://asf.alaska.edu) | open NASA data |
| OPERA RTC-S1 (Sentinel-1 radar backscatter) | NASA JPL, via ASF | open NASA data |
| Sentinel-1 / Sentinel-2 | [Copernicus](https://www.copernicus.eu) programme (ESA / European Commission) | free, full and open |
| Year photos in Catalonia | [ICGC](https://www.icgc.cat) aerial orthophotos (WMS) | attribution shown in the map; see ICGC's terms |
| Year photos elsewhere | [EOX](https://cloudless.eox.at) Sentinel-2 cloudless, "Contains modified Copernicus Sentinel data" | CC BY 4.0 (2017), CC BY-NC-SA 4.0 (2018 on) |
| Background maps | Esri World Imagery; © OpenStreetMap contributors | see each provider's terms |
| Records for the verdict | Catalan protected areas (PEIN / Natura 2000), MUC zoning (Generalitat), Spanish cadastre (INSPIRE), the Catalan solar-plant list, official records cited in the site stories | public registers; sources listed in [kb/data-sources.md](kb/data-sources.md) |

The EOX layers from 2018 on are non-commercial (CC BY-NC-SA): fine for this challenge, check before any commercial use.

## Licence

Code and text: [MIT](LICENSE). Data and imagery keep their providers' terms (table above).

## Team and how we work

Tian ([`TianK003`](https://github.com/TianK003)), Tomi ([`Space0code`](https://github.com/Space0code)),
Andrea ([`molte38`](https://github.com/molte38)). Each of us drives a Claude Code agent; the agents coordinate
through GitHub Issues and keep the knowledge base in `kb/`. Rules: [AGENTS.md](AGENTS.md).

<sub>Written by Claude</sub>
