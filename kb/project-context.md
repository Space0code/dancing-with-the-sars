# NASA Space Apps 2026 — "Dancing with the SARs" — project context

_Project background: challenge, NISAR facts, cases, resources. What we build is in `product.md`. Last updated 2026-11-14 (pivot, #6). Written by Claude; agents keep it current._

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
- **human drivers (agriculture, industry…) impacting natural resources** ← our change monitor fits this directly
- interactive summary (sliders, web maps)

## 3. Our direction (pivot 14 Nov, #6)
A **radar land-change monitor for regulators**: detect forest clearing, new buildings, earthworks and ground height
change, then flag each as expected / needs review / high concern by checking public government data (fallback: simple
rules). Pilot: **Catalonia** (overview + 2–3 hotspots); test case: Google's Finland clear-cut. Full brief: `product.md`.
The earlier datacenter-buildout angle is dropped (datacenters remain one possible *cause* of change).

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

## 5. Why SAR "sees" land change (the physics story)
Radar backscatter depends on **roughness/geometry** and **dielectric constant (moisture)**. A construction lifecycle (here a datacenter; same for any large build) has distinct signatures:

1. **Vegetation / farmland** → moderate co-pol (HH), relatively high **cross-pol (HV)** from volume scattering.
2. **Land clearing & grading** → HV drops sharply (no vegetation volume); bare smooth soil is dark; **coherence** fluctuates strongly (surface constantly disturbed).
3. **Steel frames, walls** → appear as **very bright HH** (double-bounce between walls and ground, corner reflectors).
4. **Finished buildings, parking, substations** → stable bright targets, **high InSAR coherence** over time.
5. Secondary impacts visible in SAR: new **substations, gas turbines, solar farms, cooling ponds / reservoirs** (water = dark, flat), road networks, and possibly **ground subsidence** from groundwater pumping or settlement of fill (InSAR, mm–cm).

L-band (24 cm) penetrates vegetation better and keeps coherence longer than C-band (Sentinel-1, 5.6 cm) → cleaner change detection in vegetated areas. Nice "why NISAR" talking point.

Simple, robust analysis ideas: HV/HH ratio maps, backscatter difference/ratio between dates, coherence time series, built-up area growth (threshold bright HH + high coherence) → hectares converted per site.

## 6. Complementary / longer-record SAR (allowed: "other sensors")
- **Sentinel-1** (ESA, C-band, 2014→, 6–12 days). Free via ASF / Copernicus.
- **OPERA RTC-S1** — analysis-ready S1 backscatter, 30 m. **Back to 2016 at both demo sites** (ASF search, 14 Nov: Agroparc 85 scenes in 2016, earliest 17 Apr 2016; Muhos 87 in 2016). Easiest long-baseline backscatter; counts are per burst, so pick one track for a clean series.
- **OPERA DIST-S1** — surface disturbance alerts from S1, near-global, from **Mar 2026**.
- **OPERA DISP-S1** — InSAR displacement time series, **North America only, from 2016** (30 m) → subsidence at US datacenter sites.
- Challenge partner data: CSA **RADARSAT Constellation (RCM)** & RADARSAT-1, CONAE **SAOCOM** (L-band, registration needed).
- Optical context: Sentinel-2 / HLS (NDVI before/after), high-res basemaps (Esri/Google) for validation.

## 7. Cases: Finland test case + Catalonia candidates (research 14 Nov; coordinates approximate)
Verdict labels as in `product.md`: **HC** = high concern · **NR** = needs review · **EX** = expected / natural.
Data windows: **S1** = Sentinel-1 only (2015→) · **NB** = NISAR beta (Oct 2025→) · **NC** = NISAR calibrated (Jun 2026→).
Exact outlines are not published: draw them from Sentinel-2 / ICGC orthophotos before measuring anything.

**Finland (verified).** Tuike Finland (Google) cleared ~330 ha at **Muhos** (Leppiniemi, NE of centre, ~64.843, 26.044)
and just under 200 ha at **Kajaani-Otanmäki** (~64.109, 27.107) before the EIAs were done (reports due end 2026).
Muhos cutting ran **Mar–Aug 2026**. On 30 Apr Tuike asked to skip the EIA, was told in May that one was required, and kept
cutting. The permit regulator ordered a stop on 6 Oct; Oulu police opened a preliminary investigation on 29 Oct.
Otanmäki dates (unverified). Radar: Sentinel-1 + NISAR beta cover the whole clearing, calibrated NISAR only Jun–Aug.
March cutting happened **under snow** (changes backscatter). Sources: https://yle.fi/a/74-20254086 ·
https://www.kaleva.fi/hs-google-yritti-saada-poikkeusluvan-muhoksen-hakk/13686840

| Case (lat, lon) | Change · size | Official status | Label | Radar signal · visible? | Window | Source |
|---|---|---|---|---|---|---|
| **Agroparc Penedès**, Gelida (~41.45, 1.85) | earthworks for a 258-ha project, 724,482 m³ of earth, 2025–27 | court partly halted it Jul 2025 (protected eagles); prosecutor dropped the complaint Aug 2026; works ongoing | NR | coherence loss → double-bounce; easily | S1+NB+NC | [Vilaweb](https://www.vilaweb.cat/noticies/ametller-origen-paralitza-els-treballs-a-lagroparc-de-gelida-per-la-pressio-veinal-i-la-resolucio-judicial/) · [Ara](https://en.ara.cat/economy/the-prosecution-files-the-complaint-against-the-works-of-agroparc-of-ametller-origen_25_5816220.html) |
| **Alcarràs solar**, finca Montagut (~41.62, 0.51) | 8 adjoining parks, 656 ha, ~400 MW, connected Feb–May 2026 | authorised, but a court is investigating whether one project was split into 8 permits | NR | panel rows change backscatter; coherence loss while built; very large | S1+NB | [APD](https://www.apdnoticies.com/en/lleida/656-hectares-and-almost-400-mw-eight-solar-parks-in-alcarras-were-processed-separately-despite-being-connected_5375_102.html) |
| Waste buried in farmland, Sant Esteve Sesrovires (town 41.49, 1.87; plots not public) | ≥46,000 t buried ~2022–26; area unknown | 4 arrests Jul 2026; €814,900 fine proposed | HC | coherence loss; depends on size | S1 (+NB?) | [Ara](https://en.ara.cat/society/arrested-for-burying-46-000-tons-of-waste-from-france-in-sant-esteve-sesrovires_1_5797735.html) |
| Fir cutting + earthworks, Espinelves, Osona (town 41.87, 2.42) | 200 firs, 3,000 m³; 0.8 ha vs 8 ha (sources conflict) | Agents Rurals complaint + stop order, Oct 2026 | HC | HV drop + coherence loss; marginal if 0.8 ha | NC | [3Cat](https://www.3cat.cat/3catinfo/els-agents-rurals-denuncien-una-tala-illegal-de-200-avets-a-espinelves/noticia/3433424/) |
| Aigua Xelida villas, Palafrugell (41.925, 3.210) | ~700 trees, Dec 2018, ~3 ha (unverified) | halted, in litigation | NR | HV drop | S1 | [Nació](https://naciodigital.cat/societat/talen-mes-de-700-arbres-del-paisatge-preferit-de-catalunya-sense-permis-de-lajuntament.html) |
| Cogulló salt tailings pile, Sallent (~41.81, 1.88) | ~48 Mt pile; dumping stopped 2019 | Catalan high court (TSJC) final ruling Sep 2026: ICL must remove it | HC | InSAR slope creep; height loss once removal starts | S1+NB+NC | [Ara](https://en.ara.cat/economy/the-end-of-20-years-of-litigation-justice-concludes-that-icl-must-remove-the-salt-mine-waste-dump-from-sallent_25_5837471.html) |
| Barri de l'Estació, Sallent (41.82, 1.896) | old potash-mine cavity; 12–18 cm/yr sinking in 2009; homes demolished | pre-alert monitoring | HC (mining legacy) | InSAR; current rate (unverified) | S1+NB+NC | [Nació](https://naciodigital.cat/manresa/societat/tancat-el-risc-de-subsidencies-del-barri-de-lestacio-de-sallent.html) |
| Cardona salt mountain (41.906, 1.678) | salt dome rising 2–3.5 cm/yr; sinkholes | 2025 InSAR study | EX (natural) | InSAR, strong: **check our numbers against the published rates** | S1+NB+NC | [Unizar](https://zaguan.unizar.es/record/153673) |
| Ebro Delta, Trabucador (40.61, 0.72) | subsidence 1–3 mm/yr; Storm Gloria Jan 2020 | ICGC monitoring | NR (hazard) | shoreline from amplitude yes; InSAR marginal (rice fields lose coherence) | S1+NB+NC | [ICGC](https://www.icgc.cat/en/Innovation/RDi-projects/Life-EBRO-ADMICLIM) |
| Panattoni datacenter, Cerdanyola (~41.486, 2.108) | 6.8-ha plot; first phase Q4 2026 | licensed | EX (clean permitted build) | new double-bounce | NB+NC | [Baxtel](https://baxtel.com/data-center/panattoni-barcelona-1) |
| **Gavarres wildfire**, Calonge (~41.90, 3.05) | 2,200 ha, 3–7 Jul 2026 | accidental (angle-grinder spark) | EX (natural/accident) | **same HV drop as clearing**: tests false positives | NC | [3Cat](https://www.3cat.cat/3catinfo/incendi-a-les-gavarres-la-calor-i-el-vent-principals-obstacles-per-donar-el-foc-per-controlat/noticia/3418793/) |
| Burn scars: Ribera d'Ebre (41.19, 0.63; Jun 2019, ~5–6k ha), Pont de Vilomara (41.70, 1.87; Jul 2022, 1,743 ha) | — | — | EX | HV drop | S1 | [DdT](https://www.diaridetarragona.com/sucesos/216100/el-fiscal-demana-6-anys-de-preso-per-causar-el-gran-foc-de-la-ribera-d-ebre-de-2019-el19746277.html) |
| Sau reservoir (41.973, 2.393) | <2% full Mar 2024 → ~72% Apr 2025 | drought | EX | dark water vs exposed bed | S1 | [Catalan News](https://www.catalannews.com/society-science/item/sau-reservoir-drought-empty-sinking-church-11-april-2025) |
| Watchlist, no change yet: La Ricarda runway (41.30, 2.11; works 2029+), Hard Rock, Móra la Nova AI gigafactory, Flix datacenter (41.231, 0.537) | — | in permitting | — | baseline for later | NC | [Ara](https://es.ara.cat/economia/aerolineas/aena-continua-dando-pasos-ampliacion-aeropuerto-barcelona-comience-2029_1_5791388.html) |

Seasonal farming example: Ebro Delta rice paddies flood every year (calendar unverified).
**Gap:** no documented *illegal* clearing / landfill / quarry ≥5 ha in the NISAR window. Espinelves is the only one, and
it's small. Agents Rurals offences are mostly small (2025: 3,134 clearing/felling cases → 236 formal complaints).
**Research pick for the demo:** Agroparc Penedès (big earthworks, in all 3 windows, textbook "needs review") ·
Alcarràs solar (biggest change; permitted ≠ fine; pair with Panattoni as a clean build) · Gavarres fire (false-positive
test: must come out "expected"). Runner-up: Cardona, to check our InSAR against published rates.

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
- [ ] Pick 2–3 Catalonia hotspots (research pick in §7: Agroparc Penedès, Alcarràs solar, Gavarres fire).
- [ ] Finland: Muhos cutting Mar–Aug 2026 → calibrated NISAR covers only Jun–Aug; use NISAR beta + Sentinel-1 for
      Mar–May and expect snow effects in March.
- [ ] Tech stack (web map + where processing runs) and the "date first changed" map behind the timeline: planner.
- [ ] Verdict-rule thresholds: ask the specialist (#7).
- [ ] Earthdata logins for the team (#2). Pitch format (web app + video / slides).
