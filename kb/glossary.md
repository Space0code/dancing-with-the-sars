# Glossary

_Written by Claude for the team; edit freely. Last updated 2026-11-14._

| Term | Meaning (engineer-friendly) | Why we care |
|---|---|---|
| Amplitude / intensity | Amplitude = abs(s) of the complex pixel; intensity (power) = abs(s)^2. Backscatter maps are power. | Know which one a layer stores before averaging or taking dB. |
| ASF | Alaska Satellite Facility, the NASA data centre (DAAC) hosting NISAR L-band and Sentinel-1. Provides Vertex (search UI) and `asf_search` API. | Where we get data. |
| Ascending / descending | Orbit pass direction: satellite moving roughly north (ascending) or south (descending). Different look directions and times of day. | Only compare images with the same direction and track. |
| Azimuth | Along-track axis (satellite motion direction). Resolution from the synthetic aperture. | Axis naming in raw geometry. |
| Backscatter | Share of transmitted power returned to the radar, per unit area. The "brightness" of a SAR image. | Primary signal for land clearing and buildings. |
| Baseline (orbital) | Spatial separation between the two orbit positions used for an interferogram. | Large baseline lowers coherence; NISAR's orbit is tightly controlled. |
| C-band | Radar band, ~5.6 cm wavelength (~5.4 GHz). Sentinel-1. | Long record (2014+), baseline for pre-NISAR years. |
| Co-pol / cross-pol | Co-pol: transmit and receive same polarization (HH, VV). Cross-pol: different (HV, VH). | Co-pol: surfaces, double-bounce. Cross-pol: vegetation volume. |
| COG | Cloud-Optimized GeoTIFF: tiled GeoTIFF with overviews, readable by HTTP range requests. | Format for our precomputed web-map layers. |
| Coherence | Magnitude of the normalized complex cross-correlation of two SLCs over a window, in [0, 1]. | Low where the surface changed (construction), high on stable structures. |
| DAAC | Distributed Active Archive Center: NASA data archive for a science domain. | NISAR L-band lives at ASF DAAC. |
| Dielectric constant | How strongly a material responds to the E-field; for ground, driven mostly by water content. Metal behaves like very high. | Wet soil and metal look bright; smooth water dark. |
| dB | `10 log10(power ratio)`. +3 dB is about x2 power. | Standard display/difference scale; average in linear first. |
| DEM | Digital elevation model; height grid. | Needed for terrain correction. |
| Double-bounce | Ground-to-wall corner reflection returning toward the radar; strong in co-pol (HH). | Signature of buildings and steel frames. |
| Earthdata Login | Free NASA account needed to download. | Each team member needs one; credentials in `~/.netrc`. |
| Foreshortening | Slopes facing the radar compress in slant range and appear bright and narrow. | Terrain-related brightness artifact. |
| Frame / track / path | Track (path): a repeating orbit ground track; frame: a fixed along-track segment of it. Same track + frame number = same geometry each 12 days. | Key filter for time series: pick one track/frame. |
| GCOV | NISAR L2 Geocoded polarimetric Covariance: terrain-corrected multilooked backscatter (diagonal terms HHHH, HVHV, ...), 10/20/80 m grids. | Main product. |
| GDAL `/vsicurl/` | GDAL virtual filesystem for reading remote files with range requests. | Subset huge HDF5 frames without downloading. |
| Geocoding | Resampling from radar geometry to a map projection. | Aligned grids, no manual registration. |
| GSLC | NISAR L2 Geocoded SLC: complex image on a map grid. | Custom coherence / InSAR at fine resolution. |
| GUNW | NISAR L2 Geocoded UNWrapped interferogram, with coherence and masks (80 m unwrapped, 20 m wrapped). | Coherence activity maps; subsidence. |
| HDF5 | Hierarchical Data Format: tree of groups/datasets/attributes, chunked and compressed. | NISAR's container format. |
| Incidence angle | Angle between radar ray and the vertical (or local normal) at the ground. | Affects brightness; compare same geometry or use normalized products. |
| InSAR | Interferometric SAR: phase difference between two SLCs gives path-length change. | Displacement (mm-cm) and coherence. |
| L-band | Radar band, 24 cm (1.25 GHz). NISAR's NASA radar. | Better vegetation penetration, higher temporal coherence than C. |
| Layover | A tall or steep feature's top maps closer in range than its base, so returns overlap. | Distorts tall structures; flagged in masks. |
| Look (multilook) | One independent estimate of reflectivity. Multilook: average N looks in linear power. | Reduces speckle by ~1/sqrt(N), costs resolution. |
| LOS | Line of sight, radar-to-ground direction. InSAR measures displacement only along it. | Vertical vs horizontal ambiguity in displacement maps. |
| NESZ | Noise-equivalent sigma-zero: the backscatter level equal to the instrument noise floor (dB). | Pixels near it, typically cross-pol over smooth surfaces, are mostly noise. |
| NISAR | NASA-ISRO SAR satellite, launched 30 Jul 2025; L-band and S-band; 12-day repeat. | Our core sensor. |
| OPERA | NASA/JPL project producing analysis-ready products from Sentinel-1 and others: RTC-S1 (backscatter), DIST-S1 (disturbance), DISP-S1 (displacement, N. America). | Long baseline back to 2022. |
| Polarization | Orientation of the E-field: H or V. Channel name = receive, transmit (HH, HV, VV). | Separates vegetation from built surfaces. |
| Provisional / Beta / validated | Calibration maturity of NISAR products (beta first, provisional calibrated, validated last). | Use provisional or later; beta has known issues. |
| Range (slant / ground) | Cross-track axis. Slant range: distance along the line of sight; ground range: projected on the ground. | Raw SAR images are in slant range. |
| Registration | Aligning two images to sub-pixel accuracy. | Needed for coherence; handled in geocoded products. |
| RTC | Radiometric Terrain Correction: normalizes backscatter for local slope-induced illuminated area. | Makes images comparable on slopes. |
| Shadow | Area not illuminated behind a slope or tall structure; no signal. | Masked pixels; black areas next to tall features. |
| Sigma0 / gamma0 | Normalized backscatter: sigma0 per unit ground area, gamma0 per unit area perpendicular to the beam (less incidence-dependent). | Know which a product uses before comparing sources. |
| SLC | Single-look complex: focused image with a complex value (amplitude + phase) per pixel. | Input to InSAR. |
| SNR | Signal-to-noise ratio of the data vs the instrument's thermal noise. | Limits cross-pol and dark-area quality. |
| Speckle | Multiplicative noise from coherent summation of random scatterers within a pixel; single-look std equals mean. | Why we average and never read single pixels. |
| Subsidence | Ground sinking, e.g. from groundwater pumping or compaction. | Possible datacenter side effect measured by InSAR. |
| Swath | Strip of ground imaged in one pass (NISAR: 242 km). | Determines coverage per acquisition. |
| Terrain correction | Using a DEM to put pixels on the map and fix distortion. | Aligned, comparable products. |
| Unwrapping | Recovering absolute phase from phase known only mod 2π. | Needed to convert phase to displacement; can fail in noisy areas. |
| Volume scattering | Multiple scattering inside a canopy or rough medium; depolarizes the wave. | Source of HV; disappears when vegetation is cleared. |
| Wrapped phase | Phase restricted to [-π, π). | Raw interferogram form. |

_Reference: see sar-primer.md._
