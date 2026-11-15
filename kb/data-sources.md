# Data sources

Which datasets help **detect** a land change or **judge** it (allowed? expected?), for Catalonia + the Finland test case.
Last updated 2026-11-14 (web research + live catalog checks + live service queries for #14; DIST-ALERT reads for #44). EDL = free NASA Earthdata Login. Effort L/M/H.

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
| **Urban-planning map (MUC)** | urban / buildable / non-buildable land | ✓ **WFS, all Catalonia** (see below); REST copy for Barcelona province only; development sectors on open-data API `6wpu-9y2e` | change on non-buildable land → flag | L |
| Solar PV plants (open data `ggx8-jkp4`) | status, ha, environmental-assessment procedure; municipality only | ✓ Socrata API, no login | explains many clearings | L |
| **EFFIS burnt areas** (EU, JRC / Copernicus) | wildfire perimeters 2016→, date, hectares, commune | ✓ WFS, no key, all Europe (Catalonia included, 2026 fires too) | burn scar → "expected (recorded wildfire)", not clearing | L |
| Planning register (RPUC), environmental assessments, forest-cutting permits, ICGC InSAR | PDFs / county aggregates / not public | ✗ | manual check only | H |

Open-data portal: `analisi.transparenciacatalunya.cat` (Socrata API).

### How we query them (verified live 14 Nov 2026; code: `src/sarwatch/context/`)
All Catalan / Spanish services answer in **EPSG:25831** (ETRS89 / UTM 31N, metres, x = easting). No login anywhere.
- **PEIN / Natura 2000** (`protected.py`): `…/PEIN_XN2000_ENPE/MapServer/{0,1,3}/query`, POST, polygon as esriJSON in
  EPSG:25831, `returnGeometry=true&outSR=25831&maxAllowableOffset=5` (outlines simplified to 5 m by the service, used to
  compute `overlap_share`; responses are 2-70 kB). Layers: 0 PEIN (`NOM_PEIN`, `CODI_PEIN`) · 1 Natura 2000 (`NOM_XN2`, `CODI_XN2`,
  `LIC_ZEC`/`ZEPA` = `S`/`No` for SAC/SPA, `FND_ZEC` = EEA site-sheet link) · 3 ENPE (`NOM_ESPAI`, `CODI_ESPAI`:
  pnac/pnat/pnin/rni/rnp/rnfs + buffer zones zpnac/zpnat/zrnp). Covers all Catalonia (Delta de l'Ebre answers).
  `outFields` naming a field the layer lacks → HTTP 200 with `{"error":…}`. Occasional random 400s → retry.
- **Cadastre** (`cadastre.py`): `ovc.catastro.meh.es/INSPIRE/wfsBU.aspx?service=WFS&version=2.0.0&request=GetFeature&
  typeNames=BU:Building&srsName=EPSG::25831&bbox=x0,y0,x1,y1`. A 9 km² box → `Area of extension out of limits`; we
  tile at 1.9 km. GML 3.2, ISO-8859-1. Construction date `dateOfConstruction/…/beginning` is **year precision** (1 Jan);
  `beginLifespanVersion` is the record-edit date, not construction.
- **MUC zoning** (`zoning.py`): GeoServer WFS `sig.gencat.cat/ows/PLANEJAMENT/wfs`, layer
  `PLANEJAMENT:MUC_CLASSIFICACIONS`, `bbox=…,urn:ogc:def:crs:EPSG::25831`, `outputFormat=application/json`.
  `CODI_CLAS_MUC` has 5 values across Catalonia: SUC / SNC (urban), SUD / SND (developable), SNU (non-buildable).
  Polygons can be big (a municipality's whole SNU area: ~200 kB for a 500 m box). Same server: WMS
  `…/PLANEJAMENT/wms` and other layers (qualifications, sectors, municipal boundaries).
- **Port and airport land** (`system.py`, verified 15 Nov 2026): same server, layer `PLANEJAMENT:MUC_QUALIFICACIONS`
  (what each piece of land is for). `CODI_QUAL_MUC` `SP` = "Sistemes, Portuari", `SA` = "Sistemes, Aeroportuari"
  (others seen: `A1` industrial, `A3` logistics, `SX1` / `SX2` roads, `SV` open spaces, `N2` / `N3` non-urbanisable
  protection). The port is often classed SNU in the classification layer above, so the plain zoning rule would flag its
  yards and terminals; the verdict step reads this layer instead.
- **Wildfires** (`fire.py`, verified 14 Nov 2026): EFFIS WFS 2.0.0 `maps.effis.emergency.copernicus.eu/effis`, layer
  `ms:modis.ba.poly` (burnt areas from MODIS, 2016 → a few days ago; yearly layers `…ba.poly.2016`…`.2025` exist too).
  Fields: `FIREDATE` / `FINALDATE` (`YYYY-MM-DD HH:MM:SS`, FINALDATE can be null), `AREA_HA` (a whole number *as a
  string*), `COMMUNE` (the only place name: no fire name), `COUNTRY` (ES / FR: fires over the border are in a Catalan
  bbox). **`bbox` takes latitude first**: `lat0,lon0,lat1,lon1,urn:ogc:def:crs:EPSG::4326` (lon, lat gives 0 hits); the
  GeoJSON it returns is lon, lat. No record cap seen up to 634 features. We send the polygon's bbox and intersect in
  metres ourselves. EFFIS area is ~6–8 % below press figures (Pont de Vilomara 2022: 1,635 vs 1,743 ha; Gavarres 2026:
  2,030 vs ~2,200 ha). MODIS does not map fires under ~20 ha. The `effis.nrt.ba.poly` layer answers with empty
  attributes: don't use it. Licence CC BY 4.0, credit "EFFIS, European Commission Joint Research Centre / Copernicus
  Emergency Management Service". Tried and rejected: Generalitat "Base cartogràfica d'incendis" (Socrata `dw2p-tke8`:
  only download links, 1986–2021) and `bks7-dkfd` (table without geometry, to 2024-12). Test fires: Colera, 4 Aug 2023,
  541 ha; Gavarres, 3 Jul 2026, 2,030 ha. NASA FIRMS (hotspots, needs a free key) was not needed.
- **Solar list** (`solar.py`): `…/resource/ggx8-jkp4.json?$where=starts_with(codi_municipi,'08091')`. 379 rows (Nov 2026);
  `estat`: En tramitació / Autoritzat / En servei / Aprovat / No autoritzat / Desistit. `codi_municipi` = 5-digit INE +
  check digit; one row per plant per municipality. Point → municipality: WFS layer `PLANEJAMENT:MUC_AMBIT_MUNICIPAL`
  (`CODI_INE`, `MUNICIPI`) + point-in-polygon.

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

## OPERA DIST-ALERT-HLS: how to read it
Reader: `src/sarwatch/distalert.py` (`search` → `pick_tile` → `latest` / `month_ends` → `read_window` → `combine` →
`hectares_by_month`); site numbers: `explore/optical-alerts/site_by_month.py <site>`. Checked 14 Nov 2026 against the
[product spec](https://lpdaac.usgs.gov/documents/1766/OPERA_DIST_HLS_Product_Specification_V1.pdf) (JPL D-108277 v1.0,
Feb 2024), the [ATBD](https://lpdaac.usgs.gov/documents/1835/OPERA_DIST_ATBD__V1.pdf), CMR records and live reads.
- **Granule** = one MGRS tile (109.8 km, UTM, fixed 3660 × 3660 grid of 30 m) × one HLS scene (Landsat 8/9, Sentinel-2A/B/C).
  Name `OPERA_L3_DIST-ALERT-HLS_T35WMM_<acq>_<produced>_<sensor>_30_v1`; 19 single-band COGs `<name>_<LAYER>.tif`,
  DEFLATE, 512 px tiles (DATA-MASK 256), overviews 2/4/8. V1 from 1 Jan 2023. Tiles overlap 4.9 km: Muhos is in
  35WMM and 35WMN, Agroparc in 31TCF/TDF/TCG/TDG; `pick_tile` keeps one that covers the whole window.
- **VEG-DIST-STATUS** (uint8): 0 none · 1 first <50% · 2 provisional <50% · 3 confirmed <50% · 4 first ≥50% ·
  5 provisional ≥50% · 6 confirmed ≥50% · 7 / 8 confirmed <50% / ≥50%, finished · 255 no data. "First" = one anomalous
  look; "provisional" = two or more, not yet sure; "confirmed" = confidence ≥ 400 (confidence = mean loss × number of
  loss looks²); "finished" = a confirmed alert followed by two normal looks, or one normal look ≥ 15 days after the last
  loss. <50% / ≥50% = largest vegetation-cover loss (VEG-ANOM-MAX, percent of cover).
- **VEG-DIST-DATE** (int16): day of the first loss look of the pixel's **most recent** alert, counted from 2020-12-31
  (2122 = 23 Oct 2026, checked against VEG-LAST-DATE of that day's granule); 0 none in the last year; -1 no data. Also
  VEG-DIST-CONF / -COUNT / -DUR (≤ 1 year), VEG-ANOM(-MAX), VEG-IND (current cover %), VEG-HIST, VEG-LAST-DATE,
  DATA-MASK (0 no data or masked: cloud, shadow, snow · 1 land · 2 water), and the same GEN-* set for spectral change.
- **Running state:** every granule carries the whole tile's state (all pixels, also those under cloud); tags
  `Input_DIST-ALERT_granule` (the previous state; since 21 Jul 2026 possibly several) and `Percent_Updated`. The newest
  granule holds about a year of alerts (oldest date in the 23 Oct 2026 Muhos state: 16 Oct 2025). Baseline: the same
  ±15 days in the 3 previous calendar years, so crop cycles shifted by > 15 days and drought years (Catalonia 2023)
  raise alerts on farmland. **Gotcha:** a new alert overwrites a finished one, so the newest state can date an April
  clearing in September (176 ha at Muhos): read month-end states and keep the earliest confirmed date (`combine`).
- **Winter at 65° N:** no granules from late Oct to late Feb (the Muhos state of 21 Oct 2025 is unchanged on 25 Feb
  2026). Clearing under snow shows when the snow melts: April alerts = cut any time in winter or early spring.
- **Annual summary** `OPERA_L3_DIST-ANN-HLS_V1`: one granule per tile and year, confirmed alerts only (status 9 / 10 =
  confirmed, first seen the previous year). Exists for 2023, 2024, 2025 at both sites (2025 produced 9 Jan 2026); 2026
  comes ~Jan 2027. Good for the Catalonia overview of past years.
- **Search, no login:** CMR `cmr.earthdata.nasa.gov/search/granules.umm_json?short_name=OPERA_L3_DIST-ALERT-HLS_V1&bounding_box=W,S,E,N&temporal=…&page_size=2000`,
  paging with the `CMR-Search-After` header. Fields: `MGRS_TILE_ID`, `SPATIAL_COVERAGE`, `HORIZONTAL_CS_CODE`,
  `CloudCover`, footprint polygon, per-layer `GET DATA` links.
- **Access (worked first time, no app approval asked):** `https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/…`
  with `Authorization: Bearer <token>` → **303 to a signed CloudFront URL** (`*.cloudfront.net`), range-read with no
  header (`s1.resolve_url` + GDAL `/vsicurl/`). No token → 302 to `urs.earthdata.nasa.gov`. `s3://` links work only
  inside AWS us-west-2 (unverified). Browse PNGs are public under `lp-prod-public`.
- **Measured cost (14 Nov 2026, home wifi):** whole VEG-DIST-STATUS file 1.2 MB. A 10 × 10 km window (Muhos, 341 ×
  338 px) reads 24–61 KB per layer (status 24, date 32, anom-max 40, conf 61), ~70 KB and ~6 s per state (status +
  date; ~3 s per layer, mostly the redirect and the GDAL open). Muhos, 10 monthly states: 0.69 MB, 16 s with 4 states
  in parallel; Agroparc, 47 monthly states 2023→: 3.5 MB, 63 s. CMR search: 3–5 s (461 granules) to 12–17 s (3,686).
- Tests: `python -m pytest tests/test_distalert.py`; live `SARWATCH_LIVE=1 python -m pytest tests/test_distalert.py -k live -s`.

## HLS: NDVI, snow and water per change (`src/sarwatch/ndvi.py`)
HLS (Harmonized Landsat Sentinel-2, 30 m, every 2-3 days) is a NASA product (LP DAAC) that corrects and aligns Landsat 8/9
(NASA/USGS, product HLSL30) and Sentinel-2 (ESA, HLSS30) onto one grid. NDVI = (NIR - red) / (NIR + red) with red B04 in both
and NIR B8A (S30) / B05 (L30). Quality layer Fmask (HLS User Guide v2.0): bit 1 cloud, 2 adjacent to cloud / shadow, 3 cloud
shadow, 4 snow / ice, 5 water (255 = no data). We count a date only when >= 60 % of the polygon is cloud-free; snow pixels are
left out of NDVI and give `snow_share`, water pixels give `water_share` (details in the module docstring). Both are caution
flags only: Fmask confuses thin snow, wet fields and shadows. Read cost: 0.02 GB for Muhos (24 dates, 19 changes), 0.05 GB for
Barcelona (2 areas, 20 dates each); run: `python -m sarwatch.ndvi <site> [--offline]`, cache in `data/hls/<site>/ndvi/`.

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
