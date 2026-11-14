# SAR primer for engineers

_Written by Claude for the team; edit freely. Last updated 2026-11-14._

Goal: enough radar background to read NISAR products and interpret what we see over datacenter sites. Assumes EM waves, complex signals, correlation, covariance matrices; assumes no geology or remote sensing.

## 1. What SAR is

**SAR = Synthetic Aperture Radar**: an active microwave imager. The satellite transmits pulses, records the echoes (amplitude **and** phase), and processes them into an image. Active means it brings its own illumination: works day and night, and microwaves pass through clouds.

- **Side-looking**: the antenna points sideways and down, not nadir (straight down). Echoes from ground at different distances arrive at different times, so time delay maps to **slant range** (distance along the line of sight, LOS). Looking straight down would make left and right of the track ambiguous (equal range).
- **Range** = cross-track direction (across the beam). Resolution is set by pulse bandwidth: a chirp (linearly swept-frequency pulse) is pulse-compressed by matched filtering; range resolution ~ c / (2B).
- **Azimuth** = along-track direction (satellite motion). A real antenna this size would give kilometre-scale footprints. Instead, as the platform moves, each ground point is seen over many pulses, each with a slightly different Doppler shift (a chirp in slow time). Matched-filtering that history is equivalent to a very long **synthetic aperture**, giving meter-scale azimuth resolution independent of range.
- Output of focusing: an **SLC** (single-look complex) image, one complex number per pixel: `s = A e^{jφ}`. Amplitude is reflectivity; phase is (mostly) two-way path length mod 2π plus a random scatterer term. A single SLC phase is useless; the *difference* between two SLCs is the signal (see section 6).
- **Wide swath**: NISAR uses SweepSAR (digital beamforming on receive) to get a 242 km swath at high resolution.

## 2. Backscatter: what controls the brightness

**Backscatter** = fraction of transmitted power returned toward the radar. Pixel value is proportional to the radar cross-section per unit area. Think of it as the bidirectional reflectance of the surface at the radar wavelength, and angle.

| Factor | Effect |
|---|---|
| Roughness relative to wavelength | A surface is "smooth" if height variations << λ (rule of thumb; Rayleigh-type criterion depends on incidence angle). Smooth surface acts as a mirror: energy bounces away from the radar, pixel is **dark**. Rough surface scatters diffusely, some returns, **brighter**. Same ground can look smooth at L-band (24 cm) and rough at C-band (5.6 cm). |
| Dielectric constant (mostly moisture) | Water has a very high permittivity vs dry soil; wet ground reflects more and penetrates less. Rain or irrigation brightens bare soil. Standing water is smooth, so it is dark (specular). Metal is effectively very high permittivity: very bright. |
| Geometry / scattering mechanism | See below. Often the dominant factor for man-made structures. |
| Incidence angle | Angle between radar ray and local surface normal-ish; steeper (smaller) gives brighter returns in general. Comparing images requires the same geometry (see section 5). |

**Scattering mechanisms** (what the wave does before returning):

- **Surface scattering**: single bounce off bare soil, water, roads. Smooth gives dark, rough gives medium. Dominant in co-pol (see section 3).
- **Volume scattering**: many bounces inside a canopy of leaves, branches and stems. Randomizes polarization, so it produces cross-pol power. Longer wavelengths penetrate deeper into the volume.
- **Double-bounce**: ground to vertical wall (or trunk) to radar, a dihedral corner reflector. Returns strongly toward the source, very bright, mostly in co-pol (HH especially). Buildings, steel frames, and flooded forest do this.
- **Corner reflectors / metal**: strong point targets (trihedrals, gantries, cranes, solar panel racks) can saturate a pixel and leak sidelobes.

## 3. Polarization

The radar transmits and receives with linear polarization: **H** (horizontal) or **V** (vertical) E-field orientation. Channel name = receive + transmit letters: **HH, VV** (co-pol: same on transmit and receive), **HV, VH** (cross-pol: different).

- NISAR is **quad-capable**; in practice most datasets are dual-pol (e.g. HH+HV), check per frame. Quad-pol = full 2x2 scattering matrix S per pixel.
- Co-pol (HH, VV) is dominated by surface and double-bounce. Cross-pol (HV) needs a depolarizing mechanism, which mostly means volume scattering from vegetation (or very rough surfaces). So **HV is a proxy for vegetation volume/biomass**; **HH/VV vs HV contrast** separates built/bare from vegetated.
- Monostatic reciprocity makes HV = VH, so they are redundant.
- Cross-pol is weaker than co-pol and sits closer to the noise floor (see NESZ in the glossary), so SNR matters most there.
- Useful derived products: HV/HH ratio (in dB, simply HV_dB - HH_dB), dB differences between dates, polarimetric decompositions (not needed for the MVP).

## 4. dB and speckle

**dB**: `10 log10(power)`. Backscatter spans orders of magnitude, so we display and difference in dB. A change of 3 dB is a factor of 2 in power. Never average in dB (average in linear power, then convert); do arithmetic on ratios as dB subtraction. Amplitude vs power vs dB: power = |s|^2.

**Speckle**: each pixel contains many sub-resolution scatterers whose returns add coherently with random phases. The sum's amplitude fluctuates wildly (Rayleigh amplitude / exponential intensity for fully developed speckle), even over a perfectly uniform field. For single-look intensity, std = mean (SNR of 1, or about 0 dB). It behaves like **multiplicative noise**: `I = σ · n`, with n ~ unit-mean exponential. It is deterministic given geometry (same pass gives same speckle), but looks random across pixels and across dates if the scene changed.

**Multilooking** = averaging N independent looks (neighbouring pixels, or sub-apertures) in **linear power**. For N independent looks, std/mean falls as 1/sqrt(N), at the cost of resolution (a factor N in pixels). Gridded products like GCOV are already multilooked. Further, filtering (Lee, etc.) or temporal averaging across dates are options; **temporal** averaging preserves spatial detail.

A "texture is noise, not terrain" rule: in a single-look SAR image, pixel-to-pixel salt-and-pepper is speckle. Compare **regional means** (zonal stats over polygons), not individual pixels.

## 5. Geometry distortions, and why terrain-corrected products matter

Since range is a time delay, the image is in (slant range, azimuth) coordinates, not map coordinates. Tall or sloped features are distorted:

| Effect | What happens | Appearance |
|---|---|---|
| **Foreshortening** | Slope facing the radar is compressed in slant range. | Bright, narrow. |
| **Layover** | Slope steep enough (or a tall building) that its top is closer in range than its base: top maps in front of the base. | Overlapping, very bright smear towards the radar. |
| **Shadow** | Back slope (or area behind a tall structure) is not illuminated. | Black, no data, no information. |

Datacenters are large, low-rise (tens of metres) boxes, so layover is minor at 10-20 m pixels but double-bounce and shadows next to buildings still matter. Mountainous terrain is where geometry hurts, much less for our flat sites.

**Geocoded + terrain-corrected (GTC / RTC)** products resample to a map grid (e.g. UTM) using a DEM (digital elevation model), and (for RTC) normalize radiometry by the local illuminated area. Consequences:

- Pixels from different dates line up on the same grid, so no manual **image registration** needed for GCOV/GUNW; that is half the reason to use them over RSLC/SLC.
- Backscatter is comparable across slopes; layover/shadow pixels are masked or flagged (check the mask layer).
- **Still**: only compare images from the **same track and look direction** (same orbit, same ascending/descending). Different geometry changes the scatterer response (the building faces the radar differently), producing fake changes.

## 6. Interferometry (InSAR) in brief

Two SLC acquisitions of the same area from nearly the same orbit position (a 12-day repeat for NISAR). Form the **interferogram** `s1 · conj(s2)`.

- **Phase difference** `Δφ = (4π/λ) · d_LOS` for displacement `d_LOS` along the line of sight (plus atmosphere, orbit, topography terms to be removed). One full 2π fringe means λ/2 of LOS motion: ~12 cm at L-band, ~2.8 cm at C-band. Sub-cm precision is possible, which is why InSAR detects subsidence (ground sinking) or uplift.
- Phase is measured mod 2π, so we **unwrap** (recover the integer cycle count). Unwrapping fails with noisy phase or large gradients.
- **Coherence** `γ = |E[s1 s2*]| / sqrt(E|s1|^2 · E|s2|^2)`, in [0, 1]: the magnitude of the **normalized complex cross-correlation**, estimated over a small window. 1 = identical scatterer phase (stable, phase trustworthy); near 0 = decorrelated (phase is noise).
- Coherence drops from: **temporal change** (scatterers moved, vegetation grew, soil changed, surface wetted), **geometric baseline** (orbits too far apart), **thermal noise** (low SNR), and processing error (misregistration).
- **Why construction kills coherence**: earth-moving, vehicles, new structures and fill change the sub-pixel scatterer arrangement between dates, so the correlation collapses. Stable finished buildings, pavement and roofs keep high coherence. Vegetation also decorrelates but more slowly at L-band. So **a coherence time series is a built-in activity detector**: low coherence = being disturbed; high and stable = finished/unchanged.

## 7. L-band (NISAR) vs C-band (Sentinel-1)

| | NISAR L-band | Sentinel-1 C-band |
|---|---|---|
| Wavelength / frequency | 24 cm / 1.25 GHz | 5.6 cm / ~5.4 GHz |
| Canopy penetration | Deeper: sees trunks/ground through many crops and forests | Mostly stops in the leaves and top canopy |
| Temporal coherence over vegetation | Stays higher for longer | Decorrelates quickly |
| Sensitivity to small surface roughness | Smoother at L (soil looks darker) | Rougher at C |
| LOS displacement per fringe | ~12 cm | ~2.8 cm |
| Record | 2025 onward; good data from Jun 2026 | 2014 onward |
| Repeat | 12 days | 6-12 days |

Plan: Sentinel-1 / OPERA products for the multi-year baseline; NISAR for sharper, more robust recent change.

## 8. Mapping to datacenter construction

| Phase | Ground truth | Expected SAR signature (hypothesis; verify) |
|---|---|---|
| Before | Farmland / scrub / forest | Moderate HH, relatively high HV (volume). Seasonal variation (crop cycle, moisture). Coherence moderate/low and seasonal. |
| Clearing + grading | Vegetation removed, earthworks, bare soil, heavy machinery | HV drops (volume gone); bare smooth soil dark in co-pol, or rough fill brighter; coherence low and erratic. |
| Steel + walls | Frames, slabs, walls, cranes | Bright HH spots from double-bounce and corners; patchy coherence. |
| Finished | Roofs, parking, substations, cooling plant | Stable bright returns; high, persistent coherence; no HV volume signal. |
| Secondary | New substations, roads, turbines/solar, ponds | Bright metal clutter, linear features, dark flat water. Possibly slow subsidence in InSAR (mm-cm). |

Caveats: rain and soil moisture changes cause brightness changes unrelated to construction; compare same season/geometry; confirm with optical imagery.

## 9. What NISAR products mean in engineering terms

| Product | Engineering view | Our use |
|---|---|---|
| **GCOV** | Per-pixel **polarimetric covariance matrix** C = E[s s^H] with s = [S_HH, S_HV, ...]^T, multilooked, terrain-corrected, on a map grid. Diagonals = real power per channel (HHHH, HVHV) = the backscatter we map; off-diagonals = complex cross-channel correlations (phase info, rarely needed). Radiometry is gamma-nought-style, terrain-normalized; confirm in the product spec. | Main product: change maps, HV/HH, time series. |
| **GUNW** | **Geocoded unwrapped interferogram**: unwrapped phase between two dates (12 days or multiples), plus **coherence**, plus ancillary layers (connected components, masks). Coarser grid (~80 m unwrapped). | Coherence as activity detector; displacement as subsidence. |
| **GSLC** | Geocoded complex image (amplitude + phase) on a map grid. | DIY coherence/InSAR at finer resolution; heavier. |
| RSLC | Radar-geometry complex image (pre-geocoding). | Skip. |

Version suffix in collection names (BETA, PROVISIONAL, validated) tells calibration maturity; prefer PROVISIONAL or later.

### HDF5 in brief

Each product is one HDF5 file: a filesystem-like tree of **groups** (folders) and **datasets** (n-d arrays, chunked and compressed), with **attributes** (metadata). Roughly: `science/LSAR/<product>/grids/frequencyA/...` holds the arrays (e.g. HHHH, HVHV, plus mask, projection/coordinate datasets), and `identification` / metadata groups hold frame, track, times, orbit direction. Because of chunking, one can read a window **without downloading the whole file** (HTTP range requests via GDAL `/vsicurl/`, or `h5py`/`xarray` over fsspec). Frames are 10-25 GB: always subset. Inspect with `h5ls -r`, `h5dump -H`, or `h5py` before assuming layout; paths vary by product.

## 10. Further reading

- NASA Intro to SAR: https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/sar
- NASA Intro to Remote Sensing: https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/remote-sensing
- NISAR Data User Guide (ASF): https://nisar-docs.asf.alaska.edu/
- NISAR StoryMaps: https://nisar.jpl.nasa.gov/applications/arcgis-storymaps/
- NISAR application white papers: https://nisar.jpl.nasa.gov/applications/societal-benefit/
- NASA ARSET trainings (including the 2026 NISAR course): see the challenge page, https://www.spaceappschallenge.org/2026/challenges/dancing-with-the-sars/
