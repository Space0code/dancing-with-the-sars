# Data sources

Which datasets help **detect** a land change or **judge** it (allowed? expected?), for Catalonia + the Finland test case.
Last updated 2026-11-14 (web research + live catalog checks). EDL = free NASA Earthdata Login. Effort L/M/H.

## Coverage checks we ran (ASF search API, 14 Nov 2026)
- NISAR GCOV over Catalonia since 2026-06-17: **147 granules, ~185 GB, 13 track/frame footprints**, median 1.5 GB each,
  8–11 dates per footprint (Jun 21 → Nov 2). Any one point gets a new NISAR look roughly every 5–6 days.
- Per test point, GCOV total / since 17 Jun: Barcelona 36/31 · Lleida 36/31 · Girona 29/24 · Ebro Delta 47/42 ·
  Sallent 33/28. GUNW: 16–38 per point.
- Finland: Muhos 44 GCOV (all since 17 Jun), 33 GUNW · Kajaani 52 GCOV, 41 GUNW.
- NISAR is **not** in Google Earth Engine or Planetary Computer (catalogs checked): read it from ASF (HDF5, EDL).

## 1. NASA (the challenge requires NASA data)
| Dataset | What · resolution · period | Catalonia | Access | Use for us | Effort |
|---|---|---|---|---|---|
| **NISAR GCOV** | L-band backscatter HH/HV, 10–20 m | ✓ PROVISIONAL Jun–Oct 2026; VALIDATED since 28 Oct | ASF HDF5, EDL | clearing (HV drop), new structures (HH up) | M |
| NISAR GUNW / GSLC | phase + coherence (GUNW 80 m unwrapped, coherence 20 m) / complex image 2.5–40 m | ✓ GUNW PROVISIONAL | ASF, EDL | coherence loss = earthworks; height change | M–H |
| **OPERA RTC-S1** | Sentinel-1 C-band backscatter, 30 m, 2016→ | ✓ (~1,700 granules) | ASF; **GEE** | multi-year radar history for the timeline | L |
| **OPERA DIST-ALERT-HLS** / DIST-ANN-HLS | vegetation-loss alerts from optical, 30 m, 2023→ | ✓ (to 5 Nov) | LP DAAC; annual in GEE | ready-made clearing alerts, cross-check | L |
| OPERA DIST-S1 | Sentinel-1 disturbance, 30 m | ⚠ only Jan–Feb 2026 so far | ASF | gap-prone, skip | M |
| OPERA DISP-S1 | InSAR displacement | ✗ North America only | — | use EGMS instead | — |
| HLS v2 / Landsat | optical 30 m | ✓ | GEE, Planetary Computer, LP DAAC | NDVI drop, pictures | L |
| GEDI (V3, Jul 2026) / ICESat-2 | canopy height, sparse footprints | ✓ | GEE `LARSE/GEDI` | was it mature forest? | M |
| NASADEM | DEM 30 m, year 2000 | ✓ | GEE | terrain baseline | L |
| FIRMS / MODIS MCD64A1 | active fire 375 m / burned area 500 m | ✓ | free MAP_KEY API; GEE | tell fire scars from clearing | L |
| Black Marble VNP46A2 | night lights 500 m, daily | ✓ | GEE | new lit development | L |
| Hansen Global Forest Change v1.13 | year of tree loss, 30 m, 2001–2025 | ✓ | GEE | past clearing history | L |

Not useful here: GLAD alerts (tropics only), SEDAC (frozen 2025), ECOSTRESS, EMIT.

## 2. Copernicus / EU
| Dataset | What | Access | Use for us | Effort |
|---|---|---|---|---|
| Sentinel-1 / Sentinel-2 | C-band radar / optical, 10 m | CDSE STAC, openEO, Sentinel Hub (free account); GEE `COPERNICUS/S1_GRD` | time series, pictures | L |
| **EGMS** | InSAR ground motion, mm/yr; Ortho = 100 m grid vertical + E-W; releases 2015–21 … 2020–24 (Apr 2026) | Explorer + API (login (unverified)) | subsidence / uplift layer, no processing | L |
| HRL Tree Cover Density / Imperviousness | 10 m tree cover (yearly from 2018); built-up 2021 + change 2018–21 | CDSE STAC, CLMS | was it forest / built before? | L–M |
| CORINE 2018, CLC+ Backbone 2021, Urban Atlas 2018 | land cover (Urban Atlas: cities only) | GEE / CDSE | coarse context | L |
| Copernicus DEM GLO-30 | terrain, 2011–15 | GEE / CDSE | terrain baseline | L |

## 3. Spain / Catalonia: the "is it documented?" layers
| Dataset | What | Machine query? | Use for us | Effort |
|---|---|---|---|---|
| **Cadastre buildings** (INSPIRE WFS) | footprints + construction date | ✓ WFS, ≤4 km² and ≤5,000 features per request, no login | new building with no record → flag | L |
| **ICGC orthophoto** | 25 cm, yearly 2016–2025 | WMS `geoserveis.icgc.cat/servei/catalunya/orto-territorial/wms` | before/after evidence pictures | L |
| ICGC land cover | 1 m, 41 classes: 2009, 2018, 2019–22, 2023, 2024 | WMS + GeoPackage | forest → built transitions | L |
| ICGC LiDAR (PNOA fallback) | ≥8 pts/m², flown 2021–23 | download only | cut/fill elevation differences | M–H |
| SIOSE AR | land use 2017 | WFS | baseline | M |
| **PEIN + Natura 2000** | protected areas (Natura 2000 boundaries from 2019) | ✓ ArcGIS REST, all Catalonia: `gissrv.diba.cat/arcgis/rest/services/SITXELL/PEIN_XN2000_ENPE/MapServer` | change inside → escalate | L |
| **Urban-planning map (MUC)** | urban / buildable / non-buildable land | shapefile + WMS; REST query only for Barcelona province; development sectors on open-data API `6wpu-9y2e` | change on non-buildable land → flag | M |
| Solar PV plants (open data `ggx8-jkp4`) | status, ha, environmental-assessment procedure; municipality only | ✓ Socrata API, no login | explains many clearings | L |
| Planning register (RPUC), environmental assessments, forest-cutting permits, ICGC InSAR | PDFs / county aggregates / not public | ✗ | manual check only | H |

Open-data portal: `analisi.transparenciacatalunya.cat` (Socrata API).

## Ranked for the MVP (research view, not yet a team decision)
1. OPERA DIST-ALERT-HLS: clearing alerts with zero processing
2. OPERA RTC-S1 (GEE): multi-year radar history that clouds don't block
3. NISAR GCOV: the L-band change signal the challenge requires
4. ICGC orthophoto WMS: yearly photo evidence
5. Cadastre WFS: is the building registered, and since when
6. PEIN / Natura 2000 REST: protected-area flag in one query
7. MUC zoning: buildable vs non-buildable land
8. EGMS Ortho: ready subsidence / uplift layer

## Risks
- **Legal layers are thin:** permits and environmental assessments are PDFs or not public, so "documented" can only be
  partly automated. The rest falls back to rules (protected area, zoning, cadastre).
- **NISAR is new and bulky:** ~5 months of calibrated data, mixed maturity (BETA / PROVISIONAL / VALIDATED) can make
  fake change. Compare like with like (same track/frame, same maturity) and keep subsets small.
- **Partial or stale baselines:** zoning REST covers Barcelona province only; Natura 2000 boundaries from 2019; EGMS ends 2024.

<sub>Written by Claude</sub>
