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

## OPERA RTC-S1: how to read it
Reader: `src/sarwatch/s1.py` (`search` → `pick_burst` → `thin` → `read_stack`). Checked 14 Nov 2026 against the product
spec (JPL D-108758 v1.0.3, Mar 2024, `d2pn8kiwq2w21t.cloudfront.net/documents/ProductSpec_RTC-S1.pdf`), ASF's
[RTC-S1 guide](https://hyp3-docs.asf.alaska.edu/guides/opera_rtc_product_guide/), the live search API and the
source of ASF's download gateway (TEA, `asfadmin/thin-egress-app`). No pixel read yet: no token on the dev machine.
- **One product = one burst on one date.** Files `<name>_VV.tif`, `<name>_VH.tif` (HH/HV in some regions),
  `<name>_mask.tif`, `<name>.h5` (metadata only, ~100 KB), `.iso.xml`, browse PNG. Name
  `OPERA_L2_RTC-S1_<burst T132-281622-IW2>_<start>_<produced>_<S1A|S1B|S1C|S1D>_30_v1.0`. VV / VH ≈ 7 MB each.
- **Pixels:** single-band Cloud-Optimized GeoTIFF, float32, DEFLATE; gamma0 backscatter, terrain-normalized (RTC), no
  speckle filter. Linear power: the spec lists a metadata field for the "equation to convert to dB", so not dB (the
  exact value is unverified until a read). Nodata of the VV/VH files: not stated in the docs; the reader takes NaN, the
  file's nodata value and ≤ 0 as invalid.
- **Mask** (uint8): 0 valid · 1 shadow · 2 layover · 3 both · 255 invalid (fill). Use the mask of each date, not the
  static one (layover/shadow can change between passes). The reader sets every non-zero to NaN.
- **Grid:** UTM (EPSG 326xx / 327xx), polar stereographic EPSG:3413 only above 75°N; 30 m, north-up, pixel-is-area,
  coordinates multiples of 30 m. Projection fixed per burst ID, and "bursts always have the same extent from one
  acquisition to the next" (ASF), so **one burst = one grid**: stack dates of one burst, never mix bursts. The API
  footprint (`wkt`) is that date's data outline and moves a little between dates. Expected EPSG: Agroparc 32631,
  Muhos 32635 (unverified until a read).
- **Archive:** dates from Apr 2016 (back-processed Sep 2025), forward processing since Jan 2022, new dates within ~12 h.
  Sentinel-1A / B (B to Dec 2021) / C / D. **Reprocessed copies:** the API lists several products for one burst and
  date (Agroparc, Jan-Feb 2024: 29 products, 15 burst-dates), so `output=count` overstates dates; keep the newest
  `produced` time (the reader does).
- **Search, no login:** `https://api.daac.asf.alaska.edu/services/search/param?dataset=OPERA-S1&processingLevel=RTC&intersectsWith=<WKT>&start=…&end=…&maxResults=2000&output=jsonlite`.
  Fields: `granuleName`, `startTime`, `path` (track), `flightDirection`, `wkt`, `polarization`,
  `opera.operaBurstID` (`T132_281622_IW2`: underscores, file names use hyphens), `opera.productVersion`, per-file
  URLs in `downloadUrl` + `opera.additionalUrls`, sizes in `opera.bytes`. Filter one burst: `operaBurstID=<id>`.
  ~0.3 KB per product gzipped. **Gotcha:** a query that would return more than 2,000 products gets HTTP 400 unless
  `maxResults` is set; the reader asks year by year.
- **Download hosts:** older products `datapool.asf.alaska.edu/RTC/OPERA-S1/<file>` → 307 → `cumulus.asf.alaska.edu/…`;
  recent ones `cumulus.asf.earthdatacloud.nasa.gov/OPERA/OPERA_L2_RTC-S1/<name>/<file>` directly. Without a token,
  or with an invalid one, the gateway answers 302 to `urs.earthdata.nasa.gov/oauth/authorize` (checked with curl).
- **Auth chain:** `Authorization: Bearer <Earthdata user token>` → the gateway checks it with Earthdata and answers
  **303 to a signed AWS URL valid ≤ 1 h** (TEA source). It signs for the method asked: resolve with GET, a HEAD gives
  a HEAD-only URL. Follow the redirects by hand: requests and curl drop the header on the datapool → cumulus host
  change, and S3 refuses a request that carries a second auth mechanism. Then GDAL `/vsicurl/` on the signed URL with
  `CPL_VSIL_CURL_USE_HEAD=NO`, `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`: one early-aborted GET for the size, a 16 KB
  header read, then one range GET per tile (checked offline with GDAL 3.12 against a fake gateway). The NISAR reader
  used the same chain live on 14 Nov (`data-nisar-gcov.md`); for RTC-S1 a live read is still unverified.
- **Cost:** a window read fetches whole compressed tiles. Tile size of the real files unverified; on a synthetic
  COG-like file (512 px tiles, float noise) a 3 × 3 km window cost ~3.7 MB per date (VV + VH + mask). After a read,
  `s1.last_read_stats` holds bytes (estimate from the tile index) and seconds.
- **Coverage (3 × 3 km boxes, live search 14 Nov):**

| Site | Products · bursts | Picked burst | Dates | Per year |
|---|---|---|---|---|
| Muhos | 2,976 · 12 | T160_341904_IW3, track 160 ascending | 424, 2016-07-01 → 2026-11-13 | 19 (2016), 29-48 |
| Agroparc | 3,381 · 9 | T132_281622_IW2, track 132 ascending (the only burst covering the whole box) | 465, 2016-04-18 → 2026-11-11 | 25-61 |

  Agroparc alternatives: descending T037_078155_IW3 (520 dates, covers ~98% of the box) and T110_234952_IW1 (519, ~85%).
  `thin(scenes, min_gap_days=30)` keeps about one date per month (~120 over ten years).
- Tests: `python -m pytest tests/test_s1.py`; live search `SARWATCH_LIVE=1 python -m pytest tests/test_s1.py -k live_search -s`;
  live read `EARTHDATA_TOKEN=… python -m pytest tests/test_s1.py -k live_read -s`.

## Where processing runs
The team is on mobile data: **never download NISAR to a laptop.** Radar processing runs in a GitHub Codespace
(`.devcontainer/`, Earthdata token as a Codespaces secret); only small results enter the repo. A whole-file route
for the demo sites would be ~50 granules ≈ 75 GB; window reads are estimated at 5–30 MB per date per site
(to be measured in #15). ASF Harmony subsetting for GCOV is not available yet.

## Risks
- **Legal layers are thin:** permits and environmental assessments are PDFs or not public, so "documented" can only be
  partly automated. The rest falls back to rules (protected area, zoning, cadastre).
- **NISAR is new and bulky:** ~5 months of calibrated data, mixed maturity (BETA / PROVISIONAL / VALIDATED) can make
  fake change. Compare like with like (same track/frame, same maturity) and keep subsets small.
- **Partial or stale baselines:** zoning REST covers Barcelona province only; Natura 2000 boundaries from 2019; EGMS ends 2024.

<sub>Written by Claude</sub>
