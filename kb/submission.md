# Submission pack (Finland as the worked example)

Everything the Space Apps 2026 project form asks for, drafted so the humans edit instead of writing from zero.
Last updated 2026-11-14 (#49; rewritten around Finland per Tian's 17:24 note on #9). All numbers are from the final Muhos data
(PRs #95, #100, #107) and `evidence-check.md`. Wording rules: `product.md`.

## 1. What the form requires (read from the official guides, 14 Nov 2026)
Sources: [Project Submission Guide](https://www.spaceappschallenge.org/resources/project-submission-guide/) ·
[Judging & Awards Guide](https://www.spaceappschallenge.org/resources/judging-awards-guide/) (both dated 13 Nov 2026).

**Deadline:** the global form closes **Sun 15 Nov, 23:59** Barcelona time, but **Barcelona wants projects and
presentations by Sun 16:00**, with live pitches to the local jury at 16:30 (Local Lead's email, 12 Nov; details and
sources in [`official-rules.md`](official-rules.md)). The local jury picks the Global Nominees, so submit before 16:00.
Resubmitting is allowed until 23:59; the last save counts.
Where: profile icon → My Team → **Project** tab → Edit. Turn the edit **Lock** on; only one person edits at a time.

Form fields (all required ones must be filled, all in **English**):
- [ ] **Project Name**
- [ ] **High-Level Project Summary**: what we built, how it addresses the challenge, why it matters
- [ ] **Link to Project Demo**: public link, no login (YouTube, Drive, GitHub…). Videos and documents can't be uploaded
- [ ] **Link to Final Project**: public link, no login (the GitHub Pages app and/or the repo)
- [ ] **Detailed Project Description**: what it does, how it works, benefits, goals, tools and languages
- [ ] **Use of Super Intelligence (SI)**: whether and how AI tools were used. Not shown to judges (data collection only)
- [ ] **NASA Data**: which NASA data and resources. **At least one is required for a Global Award**
- [ ] **Space Agency Partner Data and Other References**: every dataset, tool, code, text and image used, even if open
- [ ] Images on the page: JPG / PNG / GIF up to 10 MB each (screenshots go here)
- [ ] Tick "Terms and Conditions" and "Confirm All Work is Original", then **Submit for Judging**; check the banner

**Our choice (15 Nov, mentor talk, team agreed): the slide deck route, with 1–2 clips of ≤ 10 s in it; no 30 s video (see `demo-strategy.md`). The § 3 shot list is clip material now.**

**Demo (hard limit, else no Global Judging):** a **video of 30 seconds or less**, or a **slide deck of at most 7
slides** (title and intro slides included). English; a video in another language needs English subtitles. Slides must
show the team name, the members' names and the challenge. The demo counts mostly toward Presentation; the project page
carries most of the score.

**Other rules that touch us:**
- AI-generated images and video need a **visible watermark**; AI-generated code and data must be acknowledged in text
  and metadata (our "Written by Claude" footers do this, see §5). AI must not be used to come up with the idea.
- No NASA logos, flags or mission marks in AI-generated content.
- No images, video or voices of anyone under 18 in the demo or project.
- All members registered at the same Local Event and listed on the team page (max 6).
- Optional: request a FortiGuard web-filter classification for the Pages site so judges' networks don't block it.

**Judging criteria** (each scored 1–5, at local and global level):
| Criterion | What earns a 5 | How we answer it (Finland as the worked example) |
|---|---|---|
| Impact | significant problem, broad reach | regulators cannot inspect every hectare; at Muhos the satellites date a clearing that went on after the assessment was required |
| Creativity | new approach or meaningful improvement | not just a change map: three satellites on one timeline, each change checked against the record and labelled with its reason |
| Validity | scientifically sound, feasible, usable | the vegetation echo drop is stated as a hypothesis; sources disagree on hectares and we show that instead of hiding it (`evidence-check.md`) |
| Relevance | NASA data is the core, not decoration | NISAR shows the block through cloud from late June; NASA's optical alerts (OPERA DIST-ALERT, HLS) date the spring; HLS gives the colour photos |
| Presentation | clear, engaging story | one site, one time-lapse, one card; the main view is understood in ten seconds (#89) |

## 0. Must-dos before 16:00 (checked 15 Nov 11:00; tick when done)
Deck route, so these replace the 30 s video items below. Owner in brackets. **Order matters: 16:00 is the local cut-off, the form stays editable until 23:59.**
- [ ] **Deck ≤ 7 slides, public link, no login** (Andrea, #9). Slide 1 shows project name, tagline, **team name, all members' names and the challenge** (rule). Sell the idea: problem and user, the Muhos case, the live app, why radar, limits stated, what's next. 1–2 clips ≤ 10 s. English only. No NASA logos; AI images watermarked (none planned). Test the link in a private window (a navigator claims Drive may be refused, forum #2216: **Google Slides "anyone with the link" or a PDF in the repo/Release is safest**).
- [ ] **Pages app works with the final data** (Tomi + Tian). #140 merged 15 Nov 11:31, so the Gemini sentence in §5 and all licences in §4 apply.
- [ ] **Team page** (any human): rename team "4" to **Parallax** and replace "We will win (team 4 is the best)" by the tagline; all members on the **Members** tab and confirmed for Barcelona (`official-rules.md` §2, §3).
- [ ] **Form filled and "Submit for Judging" pressed** (one human, edit **Lock** on): name, summary (§2), demo link = the deck, final-project link = the Pages app, description, **SI field (§5)**, NASA data (§4), references **with a licence per item** (§4), screenshots, both tick boxes. Then check the banner. Aim: submitted by 15:00, edit afterwards.
- [x] **Licences named** for every non-NASA material (T&Cs, forum #2001; "no licence documentation = not accepted"): verified per item in §4 (#160); copy that table into the references field. No EOX / non-commercial material is used.
- [ ] **SI field matches reality** (forum #1849, #2123): says Claude wrote code and docs, and names Gemini if the report summary ships.
- [x] **NISAR maturity** stated in the description (provisional product, from 17 Jun 2026): added to §2 below.
- [x] **SI text says the idea is the team's** (the rules forbid SI for the idea): §5 reworded (#160).
- [ ] **Attribution "Contains modified Copernicus Sentinel data"** visible in the app (How it works or map credit).
- [ ] **Confirm with the Local Lead**: pitch format and length at 16:30, 16:00 hard cut-off, screen / HDMI. Bring a PDF copy of the deck and the app offline fallback.
- [ ] **Talk rehearsed twice, 2–3 min** (all). Script base: `demo-strategy.md` §4.

## 2. Name, summary, description

**Name:** **Parallax** (decided by Tian on 14 Nov 2026; the Python package keeps its old name `sarwatch`). Earlier options, for reference:
1. **SARwatch (old working title)**: "Radar finds where the land changed. Public records say which changes need a second look."
2. **Second Look**: "Every change on the ground, sorted by how much it deserves a regulator's attention."
3. **Through the Clouds**: "Satellite radar keeps watch over forests in any weather, and explains what it saw."

**High-level summary (≤150 words):**
> We built a web app that turns what satellites see into a short, explained list of land changes a regulator should
> look at first. Our worked example is Muhos, Finland, where about 330 hectares of forest were cleared for a data
> centre in 2026, as reported, while an environmental assessment was required. The app puts three satellites on one
> timeline: Sentinel-1 radar first shows the cleared block in early April, NASA's optical alerts date it month by
> month, and NASA–ISRO's NISAR radar, seeing through cloud, shows it still growing in July and August, after the
> company had learned an assessment was required. Each change is checked against the public record and labelled
> Expected, Needs review or High concern, always with the reason and before-and-after pictures. The app never decides
> whether a rule was broken. Next step: Catalonia, where the record checks already query the public registers.

(≈145 words.)

**Detailed description** (draft for the form; plain engineering language):

*What it does.* The app opens on one place, Muhos in northern Finland, with a timeline slider. Press play and the map
becomes a time-lapse: one satellite picture at a time (switch between "Radar" and "Satellite photo"), and the marked
clearing grows on the date each part was first seen, with a running "hectares so far". "Compare before and after"
turns the whole map into a swipe between the first and the current picture. Clicking the marked area opens a card:
what changed, between which dates, how sure we are, which satellites saw it, the label and the reasons behind it,
and a chart of the signal over time with one plain sentence explaining it. Reported steps (the request to skip the
assessment, the notice to suspend, the police investigation) appear as flags on the timeline. A label is a reason to
look, with the evidence attached; the app never says a change is unlawful.

*How it works.*
1. **Three satellites, one timeline.** Sentinel-1 radar (C-band, from the OPERA RTC-S1 archive, 2016 on) gives the
   long history and the first radar sighting; NASA's OPERA DIST-ALERT-HLS optical vegetation-loss alerts (Landsat and
   Sentinel-2, 30 m) date loss month by month on clear days; NISAR GCOV (L-band, 24 cm wavelength, calibrated
   backscatter, 20 m) watches from late June 2026, through cloud. We read small windows of each file over HTTPS
   instead of downloading the multi-GB granules.
2. **Change detection.** Radar images are grainy (speckle), so we average neighbouring pixels in linear power, compare
   each pass with a baseline in dB, keep drops that persist across passes, date each pixel by the first pass where the
   change shows, and group pixels into regions. Each part of the clearing carries its own first-seen date, so the
   time-lapse grows step by step.
3. **Physics, stated as a hypothesis.** Cross-polarised power (HV) comes mostly from volume scattering in branches and
   trunks; L-band reaches through the leaves, so cut forest shows as a drop in this "vegetation echo". Ordinary
   forestry or open ground nearby can look similar, so we say "the cleared block", not who cleared it.
4. **Sources kept apart.** Optical and radar disagree on hectares in June (radar marks more low-echo ground than the
   optical alerts count as new loss). The app gives each source its own name and line and never adds them up.
5. **Record check → label.** Each change is compared with the public record. Finland has no register we can query,
   so the regulator's notice and its dates were entered by hand from the published sources, with the area it covers.
   A large clearing inside that area, while an assessment was required → High concern; nothing on record → Needs
   review; a matching record or a natural cause (a recorded wildfire) → Expected. Every reason links its source.
6. **Static web app.** All results are precomputed into small GeoJSON / JSON / image files; plain HTML and JavaScript
   with MapLibre GL JS, no server and no build step, published on GitHub Pages.

*Results at Muhos* (details and limits: `evidence-check.md`):
- Sentinel-1 first shows the cleared block on its pass of 4 April 2026 (previous usable pass: September 2025).
- NASA's optical alerts confirm about 109 ha by 29 April and one block of about 359 ha by late October, close to the
  reported 330 ha: 137 ha first seen by the end of May, about half of the block first seen from July on, two months
  after the assessment was required.
- NISAR shows the block still growing between its passes of 7 July and 12 August.
- The app's chart (`app/data/muhos/story_series.json`) draws the three sources as separate lines, never added up.
- Labels on the final data (19 changes, PR #107): the clearing's **7 dated parts (359 ha) are High concern**: inside
  the area of the regulator's notice while an assessment was required. Outside it, **9 small cuts (2–3 ha) are
  Expected** ("too small to flag on its own; no land records connected for Finland") and **3 are Needs review** (two
  clearings of 5–6 ha and one 2 ha "other" change): with no Finnish register to check, their size alone puts them on
  the list.
- Limits we state: a first-seen date is the first clear view, not the cutting day; the project boundary is not
  published; we processed the data in November, nothing was detected live.

*Benefits.* A regulator sees where and when to look, with evidence and a reason; it works under cloud; it uses only
free, open data, so any region can run it.

*What's next: Catalonia.* The same pipeline with live record checks: protected areas (PEIN / Natura 2000), the
urban-planning map, the land registry, the solar-plant register and recorded wildfires already answer automatically
for any Catalan change (built and tested, `src/sarwatch/context/`). Then: run it continuously over a whole region,
add ground motion from InSAR (EGMS, NISAR interferograms), and let inspectors mark a change as checked.

*Data maturity.* NISAR GCOV is a provisional product (acquisitions from 17 Jun 2026, calibration still maturing), so every NISAR figure is read as early evidence, not a validated measurement.

*Tools.* Python (numpy, h5py, rasterio, asf-search, earthaccess, shapely, pyproj), NASA Earthdata Login, GitHub
Pages, MapLibre GL JS, plain HTML / CSS / JavaScript, Claude Code (see §5).

## 3. Clip material (the demo is now the deck; no 30 s video): shot list on the main view
Wording follows `evidence-check.md`: no NISAR hectares, "through cloud" (never snow or winter), "called on to
suspend" (not "ordered"), "as reported" for the 330 ha, no "nobody was looking". Strategy and the 3-minute pitch:
[`demo-strategy.md`](demo-strategy.md) (its §3 storyboard predates the new main view; this list replaces it).

| # | Time | Screen (1080p screen recording of the app, Muhos) | Narration (own voice, ~65 words) |
|---|---|---|---|
| 1 | 0–4 s | Muhos opens on "Satellite photo", slider at early March, forest intact. Corner label for the whole video: "Parallax · <team> · NASA Space Apps 2026" | "Northern Finland, spring 2026. A forest is being cleared for a data centre." |
| 2 | 4–10 s | Switch to "Radar", press play: frames advance, the marked block appears in early April and grows; "ha so far" counter visible; red flag "May: assessment required" passes | "Radar satellites date it pass by pass, through cloud." |
| 3 | 10–16 s | Play continues into July–August on NISAR frames; the block's edge still moving after the May flag | "NASA's NISAR shows it still growing in July and August, after an assessment was required." |
| 4 | 16–21 s | "Compare before and after": drag the full-map swipe from March to August | "Before. After." |
| 5 | 21–27 s | Click the block: card with label, the top two reasons with sources, "between … and …", the satellites listed | "Parallax checks each change against the public record and says, in plain words, why it needs a second look." |
| 6 | 27–30 s | End card: name, tagline "Know where to look first", link | "Next: Catalonia. Know where to look first." |

Recording notes: script the slider (tour or keyboard) so every take is identical; captions burned in; no music with
lyrics; no AI images or voice (no watermark needed); cut to 29 s, since over 30 s means no global judging. Slides
fallback (≤ 7): title + team + challenge · the Muhos case · the time-lapse (4 frames) · the card · how it works ·
limits we state · next: Catalonia.

## 4. Data used
**NASA** (free and open under NASA's Earth science data policy; access via [Earthdata Login](https://urs.earthdata.nasa.gov)):
| Dataset | Used for | Link |
|---|---|---|
| NISAR L2 GCOV (L-band backscatter HH/HV) | the block through cloud from late June 2026; radar frames | [ASF](https://search.asf.alaska.edu/#/?dataset=NISAR) · [docs](https://nisar-docs.asf.alaska.edu/) |
| OPERA RTC-S1 (Sentinel-1 backscatter, 30 m, 2016 on) | radar history and the first radar sighting (March 2026) | [guide](https://hyp3-docs.asf.alaska.edu/guides/opera_rtc_product_guide/) |
| OPERA DIST-ALERT-HLS (vegetation-loss alerts, 30 m) | dating the clearing month by month; the block's outline | [LP DAAC](https://lpdaac.usgs.gov/products/opera_l3_dist-alert-hls_v1v001/) |
| HLS (Harmonized Landsat Sentinel-2) | the "Satellite photo" frames of the time-lapse | [Earthdata](https://www.earthdata.nasa.gov/data/projects/hls) |

**Space agency partners and others** (paste into "Space Agency Partner Data and Other References"; the T&Cs require
a licence for every non-NASA item, forum #2001; checked 15 Nov, #160). No EOX or ICGC imagery is used: the year
photos are NASA HLS (`src/sarwatch/frames.py`).
| Item | Used for | Licence |
|---|---|---|
| Copernicus Sentinel-1 / Sentinel-2 (ESA, European Commission; inside OPERA RTC-S1, HLS, DIST-ALERT) | radar history, optical alerts, photos | Copernicus free, full and open licence (Reg. (EU) 1159/2013); "Contains modified Copernicus Sentinel data [2016–2026]" |
| Landsat 8 / 9 (USGS / NASA; inside HLS) | photos, alerts | public domain (USGS) |
| Esri World Imagery tiles | satellite background | Esri terms of use (free, no key; not an open licence); credit shown in the map: "© Esri, Maxar, Earthstar Geographics and the GIS User Community" |
| Esri World Light Gray Canvas tiles | grey background | Esri terms of use; credit shown in the map: "© Esri, HERE, Garmin, © OpenStreetMap contributors and the GIS User Community" |
| OpenStreetMap data (inside the grey map) | background map | ODbL 1.0, "© OpenStreetMap contributors" |
| Finnish sources: Lupa- ja valvontavirasto press release (6 Oct 2026), Helsingin Sanomat via Kaleva (28 Sep 2026), Yle News (29 Oct 2026) | reported steps and the hand-entered record | © each publisher; cited and linked, short facts only, not redistributed |
| MapLibre GL JS 4.7.1 | map rendering | BSD-3-Clause |
| Turf 7.2.0, shpjs 4.0.4, geotiff 2.1.3, jsPDF 2.5.1, jspdf-autotable 3.8.2 | area tools, uploads/downloads, PDF report | MIT |
| @tmcw/togeojson 5.8.1 · @mapbox/shp-write 0.4.3 | KML upload · shapefile download | BSD-2-Clause · BSD-3-Clause |
| Funnel Display / Funnel Sans fonts (self-hosted, `app/fonts/OFL.txt`) | app text | SIL OFL 1.1 |
| Python: numpy, scipy, h5py, rasterio, shapely, asf_search, fsspec · pyproj, earthaccess, pytest · requests, aiohttp · pillow | processing pipeline | BSD-3-Clause · MIT · Apache-2.0 · MIT-CMU |
| Gemini API (Google Generative Language API: `gemini-flash-lite-latest`, then `gemini-flash-latest` as second try), Cloudflare Workers, GitHub Pages | optional AI report summary, its proxy, hosting | service terms of each provider (used as services, nothing redistributed) |
| EFFIS burnt areas (European Commission JRC / Copernicus EMS) | wildfire record check: queried for every Catalan change, no burnt area matched, so no EFFIS data is shown | CC BY 4.0, "Contains data from EFFIS © European Union" ([terms](https://forest-fire.emergency.copernicus.eu/about-effis/data-license)) |
| PEIN / Natura 2000 (Generalitat de Catalunya, served by Diputació de Barcelona) | protected-area check | CC BY 4.0 per the INSPIRE record ([IDEE](https://www.idee.es/csw-codsi-idee/srv/api/records/inspire-pla-espais-interes-natural)); credit the Generalitat and the layer's update date |
| MUC zoning (sig.gencat.cat) · solar-plant register (Socrata ggx8-jkp4) | zoning and solar checks | Generalitat's "Llicència oberta d'ús d'informació – Catalunya" ([terms](https://web.gencat.cat/ca/generalitat/dades-indicadors/dades-obertes/llicencies)): reuse and derived works allowed, cite "Generalitat de Catalunya, Departament de Territori" + update date, no logos |
| Spanish Catastro INSPIRE buildings (Dirección General del Catastro) | Barcelona buildings layer | Catastro's own INSPIRE licence ([PDF](https://www.catastro.hacienda.gob.es/webinspire/documentos/Licencia.pdf)), **not CC BY**: only *transformed* data may be published, never the original records, and it must not be called "cartografía/información catastral". Our `buildings.geojson` (#152) is transformed: 7,090 footprints merged into 569 outlines with a summary label, no cadastral attributes; credit "derived from Dirección General del Catastro data" |
| Our code and derived data (`sarwatch`, the web app) | everything | MIT, in the public repo |

The web libraries are not bundled: the app loads the versions above at run time from public CDNs (unpkg, jsDelivr, cdnjs).
Esri is the one non-open item; if a reviewer objects, NASA GIBS imagery is the drop-in swap (counts as NASA data).

## 5. AI-use disclosure (for the "Use of SI" field and the README)
> The idea is the team's own: we chose the challenge and the product (radar finds land changes, public records say
> which need a regulator's look). We used Claude (Anthropic's AI models, through Claude Code) as a programming and
> writing assistant under our direction: it wrote most of the code and documentation, searched for example sites and
> data sources (the team picked Muhos and the Catalan pilot from them), checked cited sources and reviewed its own
> pull requests with a second AI reviewer. Humans set the goals, decided every design question and
> checked the results. Every file Claude wrote carries a "Written by Claude" note, and the git history shows who made
> each change. The satellite results come from NASA and ESA data processed by our code, not from an AI model, and no
> AI-generated images, video or audio are used.
>
> The optional report summary is written by Google's Gemini models (`gemini-flash-lite-latest`, falling back to `gemini-flash-latest`) through a small proxy; the app labels it "AI-written" and the rule-based summary is the default.

Before submitting: confirm the last sentence still holds (an AI voice or generated pictures would need a watermark
and a mention).

## 6. References
- Challenge: https://www.spaceappschallenge.org/2026/challenges/dancing-with-the-sars/
- Muhos: [Yle, 29 Oct 2026](https://yle.fi/a/74-20254086) · [Kaleva / HS, 28 Sep 2026](https://www.kaleva.fi/hs-google-yritti-saada-poikkeusluvan-muhoksen-hakk/13686840) ·
  [LVV press release, 6 Oct 2026](https://www.sttinfo.fi/tiedote/72390663/lupa-ja-valvontavirasto-kehottaa-tuike-finland-oyta-keskeyttamaan-muhoksen-ja-kajaanin-datakeskushankkeiden-valmistelutoimet)
- Agroparc: [ARA, 31 Jul 2025](https://en.ara.cat/economy/the-eagles-halt-the-ametller-agropark-judge-halts-the-work-until-their-transfer-is-confirmed_1_5460443.html) ·
  [VilaWeb, 7 Aug 2025](https://www.vilaweb.cat/noticies/ametller-origen-paralitza-els-treballs-a-lagroparc-de-gelida-per-la-pressio-veinal-i-la-resolucio-judicial/) ·
  [ARA, 9 Sep 2025](https://en.ara.cat/economy/almendro-origen-will-resume-construction-work-the-future-agropark-in-gelida_25_5491626.html) ·
  [ARA, 3 Aug 2026](https://en.ara.cat/economy/the-prosecution-files-the-complaint-against-the-works-of-agroparc-of-ametller-origen_25_5816220.html)
- NISAR: [ASF data user guide](https://nisar-docs.asf.alaska.edu/) · [JPL applications](https://nisar.jpl.nasa.gov/applications/societal-benefit/)
- Code: https://github.com/Space0code/dancing-with-the-sars (public after #48)

## 7. Open questions for the humans
1. Team name on the Space Apps site: is it "[team name]"? (Needed for the title card and slides.)
2. ~~Which project name~~ Decided: Parallax (Tian, 14 Nov 2026).
3. ~~Demo as a 30-second video~~ Decided 15 Nov: slide deck + 1–2 clips of ≤ 10 s.
4. Narrate with our own voices (no AI voice), so no watermark is needed? (Recommendation: yes.)
5. "Link to Final Project" = the GitHub Pages app, with the repo linked from its README? (Recommendation: yes.)

<sub>Written by Claude</sub>
