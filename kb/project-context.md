# NASA Space Apps 2026 — "Dancing with the SARs" — project context

_Project background, copied from the founding context doc. Last updated 2026-11-14 (hackathon day 1). Written by Claude; agents keep it current._

## 1. The event
- NASA Space Apps Challenge 2026, **14–15 Nov 2026**, Barcelona local event. Global judging starts **16 Nov**.
- Team of 3 (Tomi, Andrea, Tian). Challenge page: https://www.spaceappschallenge.org/2026/challenges/dancing-with-the-sars/
- Challenge difficulty: Intermediate/Advanced, subject: Earth Science.

## 2. The challenge (paraphrased)
Build an **interactive application** that uses **NISAR** radar data to track and visualize one or more types of **surface change** somewhere on Earth. Target audience is broad (scientists, decision-makers, educators, public) → **open-source, user-friendly, storytelling-first**.

Suggested flow: (1) pick a study area, (2) download free NISAR data (+ optional optical / GIS context layers), (3) present it interactively (web map, image sliders, time-series animation, dashboard, story map, video…), (4) **hypothesize the physical drivers** of what you see — which polarizations show it, what future NISAR applications are possible.

Optional considerations explicitly listed (good for judging):
- multiple polarizations and/or **other sensors / frequencies** (so Sentinel-1 C-band is allowed as a complement)
- **time series** + ancillary data (population, land cover…)
- **human drivers (agriculture, industry…) impacting natural resources** ← our datacenter angle fits this directly
- interactive summary (sliders, web maps)

## 3. Our direction
Something interesting about **datacenters** — e.g. the impact of the recent intensive buildout of datacenters (land conversion, construction footprint, surrounding infrastructure, possibly ground deformation / water). Not yet narrowed down.

## 4. NISAR in one screen
| | |
|---|---|
| What | NASA–ISRO SAR satellite, launched **30 Jul 2025** |
| Radars | **L-band** (NASA, 24 cm, 1.25 GHz) — global; **S-band** (ISRO, ~9–12 cm, 3.2 GHz) — mainly India, polar, selected sites |
| Orbit | sun-synchronous, 747 km, **12-day exact repeat**; asc + desc ⇒ ~6-day average revisit |
| Swath / resolution | 242 km (SweepSAR); ~3–10 m depending on mode |
| Coverage | all land & ice every 12 days (L-band) |
| Data policy | free & open; L-band via **ASF DAAC**, S-band via ISRO **Bhoonidhi** |
| Format | **HDF5**; products are big (dual-pol GCOV frames ≈ 10–25 GB) → subset remotely (GDAL `/vsicurl/`, Harmony) |

### Data availability timeline (critical for a "recent buildout" story)
- **Oct 2025 – Jan 2026**: BETA (pre-calibration) products, released Feb 2026 for a subset of acquisitions; known issues.
- **17 Jun 2026 → now**: **PROVISIONAL** (calibrated) products, public since 20 Jul 2026, forward-processed continuously.
- Q4 2026: validated reprocessing of the full record, expected done by end of 2026.
- ⇒ **NISAR only gives us ~1 year (realistically Jun–Nov 2026 of good data).** For multi-year "before vs after" of datacenter construction we need **Sentinel-1** (2014→) as the long baseline and NISAR as the new, sharper L-band view.

### NISAR L-band products (ASF)
| Level | Product | What it is | Pixel | Use for us |
|---|---|---|---|---|
| L1 | RSLC | range-Doppler single-look complex | — | raw input, skip |
| L1 | RIFG / RUNW / ROFF | radar-geometry interferogram / unwrapped / offsets | 30–90 m | skip |
| L2 | **GCOV** | geocoded, terrain-corrected **backscatter** (polarimetric covariance, e.g. HH, HV) | 10/20/80 m | **main product** — land clearing, new buildings, change maps |
| L2 | **GUNW** | geocoded unwrapped interferogram + **coherence** | 80 m (20 m wrapped) | coherence = construction activity; displacement = subsidence |
| L2 | GSLC | geocoded SLC (amplitude + phase) | 5–40 m | DIY InSAR / coherence at finer res |
| L2 | GOFF | pixel offsets | 80 m | glaciers, not us |
| L3 | SME2 | soil moisture | 200 m | maybe context |

Collection naming: `NISAR_L2_GCOV_PROVISIONAL_V1` (BETA / PROVISIONAL / validated = no suffix).

## 5. Why SAR "sees" datacenter construction (the physics story)
Radar backscatter depends on **roughness/geometry** and **dielectric constant (moisture)**. A datacenter lifecycle has distinct signatures:

1. **Vegetation / farmland** → moderate co-pol (HH), relatively high **cross-pol (HV)** from volume scattering.
2. **Land clearing & grading** → HV drops sharply (no vegetation volume); bare smooth soil is dark; **coherence** fluctuates strongly (surface constantly disturbed).
3. **Steel frames, walls** → appear as **very bright HH** (double-bounce between walls and ground, corner reflectors).
4. **Finished buildings, parking, substations** → stable bright targets, **high InSAR coherence** over time.
5. Secondary impacts visible in SAR: new **substations, gas turbines, solar farms, cooling ponds / reservoirs** (water = dark, flat), road networks, and possibly **ground subsidence** from groundwater pumping or settlement of fill (InSAR, mm–cm).

L-band (24 cm) penetrates vegetation better and keeps coherence longer than C-band (Sentinel-1, 5.6 cm) → cleaner change detection in vegetated areas. Nice "why NISAR" talking point.

Simple, robust analysis ideas: HV/HH ratio maps, backscatter difference/ratio between dates, coherence time series, built-up area growth (threshold bright HH + high coherence) → hectares converted per site.

## 6. Complementary / longer-record SAR (allowed: "other sensors")
- **Sentinel-1** (ESA, C-band, 2014→, 6–12 days). Free via ASF / Copernicus.
- **OPERA RTC-S1** — analysis-ready S1 backscatter, near-global, **since Jan 2022** (30 m). Easiest long-baseline backscatter.
- **OPERA DIST-S1** — surface disturbance alerts from S1, near-global, from **Mar 2026**.
- **OPERA DISP-S1** — InSAR displacement time series, **North America only, from 2016** (30 m) → subsidence at US datacenter sites.
- Challenge partner data: CSA **RADARSAT Constellation (RCM)** & RADARSAT-1, CONAE **SAOCOM** (L-band, registration needed).
- Optical context: Sentinel-2 / HLS (NDVI before/after), high-res basemaps (Esri/Google) for validation.

## 7. Candidate study sites (coordinates approximate — verify before use)
| Site | Where | Why | Approx lat, lon |
|---|---|---|---|
| OpenAI/Oracle **Stargate I** | Abilene, TX | 1.2 GW, built 2024–26, ~3.5 km² | 32.5, −99.8 |
| Meta **Hyperion** | Richland Parish (Holly Ridge), LA | 2→5 GW, ~11 km² former farmland, under construction | ~32.47, −91.7 |
| xAI **Colossus 1/2** | South Memphis, TN | built in months, 2024–26 | 35.06, −90.15 |
| AWS **Project Rainier** | New Carlisle, IN | 2.2 GW, 2024–25 | ~41.7, −86.5 |
| **Data Center Alley** | Ashburn / Loudoun Co., VA | world's densest cluster, continuous sprawl | 39.02, −77.48 |
| **Aragón cluster** (AWS, Microsoft, Blackstone) | Zaragoza/Huesca, Spain — Villanueva de Gállego, El Burgo de Ebro, Walqa, La Muela, Puerto Venecia | Europe's fastest-growing hub, local relevance (water/energy debate), ~2 h from Barcelona | Zaragoza ≈ 41.65, −0.88 |

NISAR coverage verified via ASF search API on 14 Nov 2026: Abilene → 35 GCOV products; Zaragoza → 38 GCOV; Ashburn → 43 GUNW. ✅

Trackers for site lists & dates: Epoch AI Frontier Data Centers Hub, FAS "Tracking Hyperscale AI Data Center Growth", Baxtel, PNNL data center atlas.

## 8. Resources from the challenge page
- NASA Earthdata Search — https://search.earthdata.nasa.gov/search
- ASF Vertex (NISAR) — https://search.asf.alaska.edu/#/?dataset=NISAR
- NISAR Data User Guide (ASF) — https://nisar-docs.asf.alaska.edu/ (see Available Data, Data Products, Accessing, Tutorials)
- Intro to Remote Sensing — https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/remote-sensing
- Intro to SAR — https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/sar
- NASA ARSET trainings (incl. 2026 NISAR course, EN/ES)
- NISAR StoryMaps — https://nisar.jpl.nasa.gov/applications/arcgis-storymaps/
- NISAR Applications white papers — https://nisar.jpl.nasa.gov/applications/societal-benefit/
- UAVSAR Postcards
- CSA RCM data — https://donnees-data.asc-csa.gc.ca/en/dataset/rcm ; RADARSAT-1 — https://donnees-data.asc-csa.gc.ca/en/dataset/radarsat1 ; CSA SAR Python/QGIS tutorial
- CONAE SAOCOM catalogue (registration required)

## 9. Access & tooling notes
- **Earthdata Login** account needed for downloads (urs.earthdata.nasa.gov) → `~/.netrc`.
- Python: `asf_search` (pip `asf-search`), `earthaccess`, `h5py`/`xarray`, `rasterio`/GDAL (`/vsicurl/` to read HDF5 subsets without full download).
- ASF search API (no login needed for search), e.g.
  `https://api.daac.asf.alaska.edu/services/search/param?dataset=NISAR&processingLevel=GCOV&intersectsWith=POINT(lon lat)&output=count`
- **Compute:** some cloud sandboxes (e.g. Claude web containers) can't reach NASA APIs → run downloads/processing from a local Claude CLI. Read small subsets remotely; don't download whole 2–7 GB granules unless needed.
- Front-end idea: static web app (Leaflet/MapLibre + swipe slider + time-series chart), COG/PNG tiles precomputed.

## 10. Open decisions / next steps
- [ ] Pick 1 hero site (+ maybe 1–2 comparison sites). Aragón = local story; Stargate/Hyperion = dramatic scale.
- [ ] Decide the question: land converted? speed of buildout? secondary infrastructure? subsidence/water?
- [ ] Get Earthdata logins for the team (onboarding issue); download a first GCOV subset over the hero site.
- [ ] Long baseline from OPERA RTC-S1 (2022→) to show pre-construction state.
- [ ] Choose presentation format (web app + 30-s video/slides for submission).
