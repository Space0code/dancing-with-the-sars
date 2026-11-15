# Submission form: paste-ready texts

The final text for each field of the Space Apps project form, for the product as it is on `main` (Parallax, a tool with two example sites). Last updated 2026-11-15, 13:30. **Not submitted yet: Tian and Tomi review first.** Rules and the checklist: [`submission.md`](submission.md) · the official guide: [`../docs/rules/project-submission-guide-2026-11-13.pdf`](../docs/rules/project-submission-guide-2026-11-13.pdf). Numbers were recomputed from `app/data` on 15 Nov; wording follows [`evidence-check.md`](evidence-check.md).

Where: profile icon → My Team → **Project** tab → Edit → turn the **Lock** on (one editor at a time; "Save Progress" is visible to the team only). All text in English. The form can be edited and resubmitted until 23:59; the last save counts.

## 1. Project Name
Parallax

## 2. High-Level Project Summary
Regulators cannot inspect every hectare, and optical satellites see nothing under cloud. Parallax is a web app that turns radar satellite data into a short, explained list of land changes to look at first. It reads NASA–ISRO's NISAR and Sentinel-1 radar through NASA's data products, finds where the land surface changed and when, and checks each change against public records such as protected areas, zoning and registered buildings. Every change gets a label, Expected, Needs review or High concern, with its reasons, sources and before-and-after pictures. Parallax never says a rule was broken; it says where to look. Two example sites are live. In northern Finland, satellites show a 359-hectare forest clearing still growing in July and August 2026, after the developer was told an environmental assessment was required. Around Barcelona, 100 changes since 2016 are labelled from public records. Results export as a report or GIS files.

## 3. Link to Project Demo
`<public link to the 7-slide deck: Andrea; must open in a private window without login>`

## 4. Link to Final Project
https://space0code.github.io/dancing-with-the-sars/

(Code: https://github.com/Space0code/dancing-with-the-sars, linked from the app's About page.)

## 5. Detailed Project Description

**What it does**

Parallax is for the people who decide where to inspect: environmental regulators, planning officers, decision makers. It opens on a full-width map of one site with a timeline. Press play and the map becomes a time-lapse of satellite pictures, in a Radar view or a Satellite view, and each marked change appears on the date it was first seen. "Compare" turns the map into a swipe between a before and an after picture.

Clicking a change opens a card: what changed, between which dates, how large it is, which satellites saw it, its label, and "Why this label?", a checklist of the reasons with a link to each source. The card also shows the radar signal over time, a greenness check (NDVI) from optical data, and a note when snow or flooding could explain the signal.

A user can limit the view to a time frame and an area (draw a box, type coordinates, or upload GeoJSON, a zipped shapefile, KML or GPX) and export the result: a PDF report with the map, the key numbers, a short summary and the changes to check first, or the data as CSV, GeoJSON, shapefile or GeoTIFF for the GIS tools experts already use. Every view has a link that restores it.

A label is a reason to look, with the evidence attached. Parallax never says that a rule was broken, and never names who made a change.

**How it works**

1. *Radar that sees through cloud.* NISAR L2 GCOV (NASA–ISRO, L-band, 24 cm wavelength, 20 m pixels) and Sentinel-1 through NASA's OPERA RTC-S1 product (C-band, 30 m, from 2016). We read small windows of each file over HTTPS instead of downloading multi-gigabyte granules.
2. *Change detection.* Radar pictures are grainy (speckle), so we average neighbouring pixels in linear power, compare each pass with a baseline in dB, keep the changes that persist across passes, date each pixel by the first pass that shows it, and group pixels into areas. A rule on the two polarisations gives the type: forest clearing (the cross-polarised "vegetation echo" drops), a new structure (the co-polarised echo jumps) or earthworks (both unstable).
3. *Optical data as a second witness.* NASA's OPERA DIST-ALERT-HLS vegetation-loss alerts date clearings on clear days, and NASA's HLS (Harmonized Landsat Sentinel-2) gives the dated photos and the NDVI for a same-season greenness check. Each source keeps its own name and date. Where they disagree on hectares we show each one and never add them up.
4. *Physics, stated as a hypothesis.* Cross-polarised power comes mostly from volume scattering in branches and trunks, and L-band passes through leaves, so cut forest shows as a drop in that echo. Wet snow, flooding and harvested fields can look similar, so the app notes those cases on the card.
5. *Record check, then a label.* Fixed, visible rules (no trained model) compare each change with public records. For the Barcelona region the records are looked up automatically: protected areas (PEIN, Natura 2000), the Catalan zoning map, building outlines derived from Spanish Catastro data, the Catalan solar-plant register and recorded wildfires (EFFIS). A new building where a building is registered or planned comes out Expected. A change inside a protected area, or a large clearing on land zoned as non-buildable, comes out High concern. A change of two hectares or more with nothing on record comes out Needs review. Finland has no register we can query, so there we entered the regulator's published notice by hand, with its sources, and the app says so.
6. *A static web app.* All results are precomputed into small GeoJSON, JSON and image files. The app is plain HTML, CSS and JavaScript with MapLibre GL JS, with no server and no build step, published on GitHub Pages. One online service is optional: the report's short summary is written by Google's Gemini model through a small proxy that receives only the facts of the changes. It is labelled "AI-written summary (Google Gemini)", and if the service does not answer, a rule-based summary is used.

**What it shows at the two example sites**

*Muhos, northern Finland* (June 2025 to October 2026; 40 radar pictures, 24 dated photos). As Finnish media reported, about 330 hectares of forest were cleared here in 2026 for a data centre; the developer was told in May that an environmental assessment was required, and on 6 October the regulator called for the work to be suspended. What the satellites show:
- Sentinel-1 radar first shows the cleared block on its pass of 4 April 2026.
- NASA's optical alerts confirm about 109 ha by 29 April and one block of about 359 ha by 23 October, close to the reported 330 ha.
- All three satellites show the block still growing in July and August, after the May notice: by at least 70 ha after the end of May. NISAR shows the bare area growing between its passes of 7 July and 12 August.
- Between 29 May and 30 July there was no usable optical picture, while radar passed six times.
- Parallax lists 19 changes: the clearing's 7 dated parts (359 ha) are High concern, 3 are Needs review and 9 small cuts are Expected.

*Barcelona and its region, Catalonia* (2016 to November 2026; 63 radar pictures from Sentinel-1 and NISAR). Parallax lists 100 changes covering 541 ha: 73 new structures, 17 clearings, 8 earthworks and 2 other. From the public records, 70 are Expected, 22 are Needs review and 8 are High concern (29 ha). Here the list does what it is for: most changes in a growing city are ordinary, and the tool says so, leaving a short list to look at.

**Limits we state**

- A first-seen date is the first usable satellite view, not the day the change happened.
- NISAR GCOV is a provisional product (acquisitions from 17 June 2026), so its figures are early evidence, not validated measurements. At Muhos NISAR confirms the bare block and its growth but flags no change of its own.
- "Through cloud" is the only weather claim we make. At Muhos we do not use Sentinel-1 from October to March, when snow disturbs the signal.
- The data were processed in November 2026: nothing was detected live. The two sites are precomputed; running a new area on demand is the next step.
- The Finnish record was entered by hand from the published sources.

**Benefits**

An inspector sees where and when to look, with the evidence and the reason, in plain language and under cloud. An expert can check every line and take the data into their own tools. Everything rests on free, open satellite data, so the same pipeline can be set up for any region.

**What is next**

Detection on demand for any area a user draws; an alert when a new change appears, with its size and label as the trigger; more public registers; ground motion from NISAR interferograms.

**Tools**

Python 3.11 (numpy, scipy, h5py, rasterio, shapely, pyproj, asf_search, earthaccess, Pillow, pytest), NASA Earthdata Login, JavaScript (MapLibre GL JS, Turf, jsPDF, geotiff.js, shpjs), HTML and CSS, GitHub Pages and GitHub Actions, a Cloudflare Worker, the Google Gemini API, and Claude Code as an AI programming assistant (see "Use of SI"). No special hardware: radar files are read remotely in small windows from a laptop.

## 6. Use of Super Intelligence (SI)
The idea is the team's own: we chose the challenge and the product (radar finds land changes, public records say which need a regulator's look). We used Claude (Anthropic's AI models, through Claude Code) as a programming and writing assistant under our direction: it wrote most of the code and documentation, searched for example sites and data sources (the team picked the two sites from them), read and checked the cited sources, drafted the slides' text and layout, and reviewed its own pull requests with a second AI reviewer. Humans set the goals, decided every design question and checked the results. Every file Claude wrote carries a "Written by Claude" note, and the git history shows who made each change.

The satellite results come from NASA and ESA data processed by our code, and the labels come from fixed rules, not from an AI model. One part of the product uses AI at run time: the short summary in the exported PDF report is written by Google's Gemini models (`gemini-flash-lite-latest`, with `gemini-flash-latest` as the second try) through a small proxy that receives only the facts of the changes. The report labels it "AI-written summary (Google Gemini)"; if the service does not answer, a rule-based summary is used instead. No AI-generated images, video or audio are used in the app or in the slides: every picture is satellite data or a screenshot of the app.

## 7. NASA Data
- **NISAR L2 GCOV** (NASA–ISRO, L-band radar backscatter, HH and HV): radar pictures and change detection from June 2026. https://search.asf.alaska.edu/#/?dataset=NISAR · https://nisar-docs.asf.alaska.edu/
- **OPERA RTC-S1** (NASA JPL; radiometric terrain-corrected Sentinel-1 backscatter, 30 m, 2016 on): the radar history, the time-lapse pictures and change detection. https://hyp3-docs.asf.alaska.edu/guides/opera_rtc_product_guide/
- **OPERA DIST-ALERT-HLS** (NASA JPL; vegetation-loss alerts, 30 m): dating the Finnish clearing month by month and its outline. https://lpdaac.usgs.gov/products/opera_l3_dist-alert-hls_v1v001/
- **HLS, Harmonized Landsat Sentinel-2** (NASA): the dated photos, the greenness (NDVI) check, the snow and water notes. https://www.earthdata.nasa.gov/data/projects/hls
- **NASA Worldview / GIBS**: one picture in the slides (the optical scene under cloud, 20 Oct 2026). https://worldview.earthdata.nasa.gov/
- Access: NASA Earthdata Login, Alaska Satellite Facility (ASF) DAAC, LP DAAC.

## 8. Space Agency Partner Data and Other References
Paste the table of [`submission.md` section 4](submission.md#4-data-used) ("Space agency partners and others": every item with its use and its licence), then these references:

- Challenge: https://www.spaceappschallenge.org/2026/challenges/dancing-with-the-sars/
- ESA / European Commission: Copernicus Sentinel-1 and Sentinel-2 (inside OPERA RTC-S1, HLS and DIST-ALERT). Contains modified Copernicus Sentinel data (2016–2026).
- ISRO: NISAR is a joint NASA–ISRO mission.
- Finland, reported facts: Lupa- ja valvontavirasto press release, 6 Oct 2026 (https://www.sttinfo.fi/tiedote/72390663/lupa-ja-valvontavirasto-kehottaa-tuike-finland-oyta-keskeyttamaan-muhoksen-ja-kajaanin-datakeskushankkeiden-valmistelutoimet) · Helsingin Sanomat via Kaleva, 28 Sep 2026 (https://www.kaleva.fi/hs-google-yritti-saada-poikkeusluvan-muhoksen-hakk/13686840) · Yle News, 29 Oct 2026 (https://yle.fi/a/74-20254086).
- NISAR documentation: https://nisar-docs.asf.alaska.edu/
- Our code and derived data: MIT licence, https://github.com/Space0code/dancing-with-the-sars

## 9. Images to upload
From [`../docs/screenshots/submission/`](../docs/screenshots/submission/) (taken from the live app on 15 Nov), in this order: `01-finland-radar.png` · `02b-finland-card-top.png` (the label) · `02-finland-card.png` ("Why this label?") · `03-finland-compare.png` · `04-barcelona-map.png` · `05-barcelona-card-records.png` · `07-filter-export.png` · `08-report-pdf.png`. Plus `../docs/pitch/barcelona-demo.gif` (the app working on Barcelona, 7.2 MB) and `../docs/pitch/cloud-pair.jpg` (optical under cloud next to radar). JPG, PNG or GIF, up to 10 MB each; the guide sets no number.

## 10. Before pressing "Submit for Judging"
- [ ] Team page: team name "4", all three members on the Members tab and confirmed for the Barcelona event.
- [ ] The deck link opens in a private window without login; the deck has at most 7 slides and names the team, the members and the challenge.
- [ ] The app link opens in a private window.
- [ ] Both tick boxes ("Terms and Conditions", "Confirm All Work is Original"), then "Submit for Judging", then check the confirmation banner.
- [ ] After any later change to the app or the deck: re-read sections 6 to 8 and save again before 23:59.

<sub>Written by Claude</sub>
