# NISAR GCOV: file layout and how we read it

What a NISAR L2 GCOV file contains, how to find granules, how `sarwatch.nisar` reads a small window over HTTPS, and
the traps. Last updated 2026-11-14. Terms: [glossary.md](glossary.md) (RTC, sigma0 / gamma0, track / frame).

Sources: ASF NISAR user guide (nisar-docs.asf.alaska.edu: GCOV, Projections, Data format, earthaccess, GDAL, S3
access, known-issues pages), the GCOV product specification JPL D-102274 Rev F, v1.5.0, 8 Jul 2026 ("spec"), live ASF
search and `curl` header checks on 14 Nov 2026. Anything not checked against those is marked (unverified).

## What the numbers are
- Each pixel holds a **polarimetric covariance matrix**, multilooked, radiometrically terrain-corrected (area-based RTC,
  Copernicus DEM) and geocoded. The diagonal terms are real **float32 linear power, normalised as gamma0**
  (`units = "1"`, `valid_min = 0`): `HHHH` = HH backscatter power, `HVHV` = HV. dB = `10*log10(value)`.
- Off-diagonal terms (`HHHV`, `HHVV`, ...) are complex64 and exist only for quad-pol; our sites are dual-pol `DHDH`
  (HH + HV), so only `HHHH` and `HVHV` are there.
- sigma0 ≈ gamma0 × `rtcGammaToSigmaFactor` (an approximation, spec §4.3.1). We keep gamma0, like OPERA RTC.
- Very dark areas (water, smooth bare soil) sit near the noise floor, mostly in HV.

## HDF5 layout (spec §3.2.5, §4.3, tables 5-2 and 5-3)
| Path (under `/science/LSAR/`) | Type | Meaning |
|---|---|---|
| `GCOV/grids/frequencyA/HHHH`, `HVHV` | float32 (rows, cols) | backscatter power; `_FillValue = NaN`; attr `grid_mapping = "projection"` |
| `GCOV/grids/frequencyA/mask` | uint8 | 0 = partly focused or invalid, 1-5 = valid (sub-swath number), 255 = outside the swath (`_FillValue`) |
| `GCOV/grids/frequencyA/numberOfLooks`, `rtcGammaToSigmaFactor` | float32 | looks averaged per pixel; gamma0 → sigma0 factor |
| `GCOV/grids/frequencyA/xCoordinates`, `yCoordinates` | float64 vectors | metres, **pixel centres** (`pixel_coordinate_convention = "center"`) |
| `GCOV/grids/frequencyA/xCoordinateSpacing`, `yCoordinateSpacing` | float64 scalar | nominal spacing, metres |
| `GCOV/grids/frequencyA/projection` | uint32 scalar | **value = EPSG code**; attrs `epsg_code`, `spatial_ref` (WKT), `utm_zone_number`, ... |
| `GCOV/grids/frequencyA/listOfPolarizations`, `listOfCovarianceTerms` | strings | what this granule has |
| `GCOV/metadata/radarGrid/` | 3-D cubes | incidence angle, line of sight, ... on a coarse (x, y, height) grid |
| `GCOV/metadata/processingInformation/parameters/` | flags | `radiometricTerrainCorrectionApplied`, `isFullCovariance`, ... |
| `identification/trackNumber`, `frameNumber` | uint32, uint16 | track 1-173, frame 1-176 |
| `identification/orbitPassDirection` | string | `"Ascending"` / `"Descending"` |
| `identification/zeroDopplerStartTime` | string | UTC, `YYYY-mm-ddTHH:MM:SS.sssssssss` (nanoseconds) |
| `identification/boundingPolygon`, `isFullFrame`, `compositeReleaseId` | strings | footprint WKT (lon lat), full or partial frame, CRID |

`frequencyB` (5 MHz side band, 80 m) has the same layout; it is less well calibrated (PROVISIONAL known issues).

## Grid
- North-up (spec §3.6): row index goes south (y decreases), column index goes east. Corner of pixel (row, col):
  `x = x_c[0] - dx/2 + dx*col`, `y = y_c[0] - dy/2 + dy*row` with `dy < 0` (we derive dx, dy from the coordinate
  vectors; the sign stored in `yCoordinateSpacing` is (unverified)).
- Spacing, frequency A: **20 m** for 20 MHz and 77 MHz modes, **10 m** for 40 MHz; frequency B: 80 m. The mode is in
  the file name: `2005` = 20 MHz A + 5 MHz B, so Muhos 157/35 and Agroparc 130/22 should be 20 m (confirm on first read).
- Size: an example 40 MHz frame is 35,928 × 36,288 px (ASF GDAL page). Files are ~2.05 GB full frame (Muhos), ~0.9 GB
  partial frame (Agroparc).
- **Projection:** UTM north/south (EPSG 32601-32660 / 32701-32760), NSIDC polar stereographic north (EPSG 3413) or
  Antarctic polar stereographic (3031). The ASF projections page says "north of 60°N → 3413"; spec Appendix B says
  3413 is for "Greenland and Northern Hemisphere sea ice" and UTM for "Northern Hemisphere land except Greenland".
  So Muhos (64.8°N) is either 32635 or 3413 (unverified); the reader takes the EPSG from the file and handles both.
  Appendix B prints `+lon_0=45` for 3413; the real EPSG:3413 uses `-45` (we use -45, pyproj agrees).
- Each frame has a fixed projection for the whole mission (spec App. B), so one track + frame should give the same
  lattice on every date (unverified until the first stack read; `read_stack` checks it and raises if not).
- **Storage:** chunked, nominally 512 × 512 px, compressed; the file uses HDF5 **paged** file-space aggregation with a
  page larger than one chunk, so a chunk plus its index metadata can come in one request (spec §3.8). Actual page size
  (unverified).

## Names, collections, maturity
- `NISAR_L2_PR_GCOV_<cycle>_<track>_<A|D>_<frame>_<mode>_<pol>_<src>_<start>_<end>_<CRID>_<orbit>_<F|P>_J_<counter>`;
  `F|P` = full or partial frame coverage, `counter` = product counter (a re-generated product gets `002`).
- Collection in the URL path = maturity: `NISAR_L2_GCOV_BETA_V1` (pre-calibration, Oct 2025-Jan 2026, CRID < P05023),
  `NISAR_L2_GCOV_PROVISIONAL_V1` (calibrated, acquisitions from 17 Jun 2026, CRID P05023), `NISAR_L2_GCOV_V1`
  (validated; seen with CRID P05036 from late Oct 2026).
- Some granules have no frequency A (e.g. mode `0005`, pol `NASV`, track 85 at Muhos); `read_crop` then raises.

## Finding granules (no login)
- `GET https://api.daac.asf.alaska.edu/services/search/param?dataset=NISAR&processingLevel=GCOV&intersectsWith=POLYGON((w s,e s,e n,w n,w s))&output=jsonlite`
  plus optional `start=` / `end=` (ISO, `Z`).
- jsonlite fields we use: `granuleName`, `downloadUrl`, `startTime`, `path` (= track), `frame`, `flightDirection`,
  `collectionName`, `nisar.sizeMB[<fileName>].bytes` (top-level `sizeMB` is null for NISAR). Also there:
  `nisar.frameCoverage`, `nisar.crid`, `nisar.rangeBandwidth` (`"20+5"`), `nisar.mainBandPolarization`, `wkt`.
- Live result, 14 Nov, acquisitions up to 10 Nov (`SARWATCH_LIVE=1` test):

| Site | Picked stack | Dates | Maturity | Total |
|---|---|---|---|---|
| Muhos (~1 km box at 26.044, 64.843) | track 157 / frame 35 ascending | **11** dates (12 granules: 2026-09-05 has counters 001 and 002), 25 Jun → 4 Nov, no 31 Jul | 9 PROVISIONAL + 2 VALIDATED (23 Oct, 4 Nov) | 22.6 GB |
| Agroparc (1.84-1.86, 41.44-41.46) | track 130 / frame 22 ascending | 11 dates, 23 Jun → 2 Nov, all partial frames | 10 PROVISIONAL + 1 VALIDATED (2 Nov) | 10.1 GB |

  Agroparc is a tie: 66 / 68 descending also has 11 PROVISIONAL-or-later dates (18 Jun → 28 Oct, full frames) plus
  5 BETA dates (Nov 2025-Jan 2026). `pick_track` breaks ties by the most recent last date.

## Reading over HTTPS
- Granule URL: `https://nisar.asf.earthdatacloud.nasa.gov/NISAR/<collection>/<granule>/<granule>.h5` (Earthdata
  Cloud, AWS us-west-2).
- Checked with `curl` and no credentials: a GET without a token, or with an invalid bearer token, gets **302 to
  `urs.earthdata.nasa.gov/oauth/authorize`**; a HEAD gets **303 to a signed CloudFront URL**
  (`*.cloudfront.net/.../sds-n-cumulus-prod-nisar-products.s3.us-west-2.amazonaws.com/...`), which answers 200 with
  `Content-Length: 2051014656` and `Accept-Ranges: bytes`. With a valid token, a GET should redirect to a signed URL
  the same way (unverified until we have a token). A signed URL for a public ASF file expired 1 h after issue; we assume
  the same for granules (unverified).
- Token: Earthdata Login → Generate Token. User tokens last **60 days**, at most two valid at once.
- **What `sarwatch.nisar` does:** one `GET` with `Authorization: Bearer <token>` and `Range: bytes=0-0`, redirects
  followed by hand; the token goes only to the archive host and is dropped once the host changes; a redirect to the
  login host raises `PermissionError`. All further reads are `Range` GETs on the signed URL without the token; a 401 /
  403 there (expiry) resolves again once. `requests.Session(trust_env=False)`: with `trust_env`, a `~/.netrc` entry
  for the host would replace the bearer header (earthaccess sets `trust_env=False` for the same reason). h5py opens a
  Python file object that caches 2 MiB aligned blocks (`BLOCK_SIZE`) and fetches neighbouring missing blocks in one
  request, so HDF5's many small metadata reads become a few large requests. `Crop.bytes_read` counts the bytes fetched.
- Other routes: earthaccess `get_fsspec_session()` builds `fsspec.filesystem("https", client_kwargs={"headers":
  {"Authorization": "Bearer ..."}, "trust_env": False})`, then xarray `engine="h5netcdf"`; ASF suggests
  `block_size=16 MB`, `cache_type="background"`. Both requests (hostname change) and aiohttp (origin change) strip the
  Authorization header on cross-host redirects (checked in requests 2.34 / aiohttp 3.14 source). GDAL ≥ 3.13 reads
  NISAR HDF5 natively (`/vsicurl/` + `.netrc`); older GDAL needs the `NETCDF:` driver prefix.
- S3 direct access (faster, temporary keys from `https://nisar.asf.earthdatacloud.nasa.gov/s3credentials`) works only
  from AWS us-west-2, so not from a GitHub Codespace.

## Invalid pixels → NaN in `Crop.data`
NaN where the mask is 0 or 255, the value is NaN (fill) or ≤ 0 (no dB), or the bbox reaches past the granule.

## Gotchas
- **Maturity switch inside a stack:** at both sites the last 1-2 dates are VALIDATED (CRID P05036), the rest PROVISIONAL
  (P05023). Different processing versions can cause a radiometric step at the switch (size unverified): check a stable
  area for a jump on that date before trusting late changes. Never mix BETA with later products.
- **Several granules per date** (re-generated counter `002`, partial `P` + full `F`): keep one, as `pick_track` does.
- Compare one track only: incidence angle and look direction differ between tracks even after RTC.
- High latitude (Muhos): residual ionospheric effects, incl. geolocation errors (PROVISIONAL known issues).
- RFI shows as bright blobs or range streaks, worst in HV; the PROVISIONAL RFI filter leaves residuals in places.
- BETA products: valid-data mask misaligned with the data (BETA known issues); for PROVISIONAL (unverified).
- Polarimetric phase calibration is off by 59° in PROVISIONAL; affects complex cross terms only, not `HHHH` / `HVHV`.

## Measured cost
To be measured by the orchestrator from the Codespace (live read test below): MB and seconds per crop, number of
requests, EPSG and pixel spacing at Muhos, whether a whole-stack read stays on one grid.

## Code
`src/sarwatch/nisar.py`: `search(bbox, start, end)` → `pick_track(granules, min_maturity)` → `read_crop(url, bbox)`
/ `read_stack(granules, bbox)`. bbox = (west, south, east, north) in degrees; UTM and polar stereographic maths are
built in (checked against pyproj in the tests), other EPSG codes need pyproj. Tests: `tests/test_nisar.py` (offline
on synthetic GCOV-shaped files and a fake archive that redirects to a signed URL). Live:
`SARWATCH_LIVE=1 python -m pytest tests/test_nisar.py -k live -s` (the read also needs `EARTHDATA_TOKEN`).

<sub>Written by Claude</sub>
