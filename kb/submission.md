# Submission pack (first draft)

Everything the Space Apps 2026 project form asks for, drafted so the humans edit instead of writing from zero.
Last updated 2026-11-14 (#49). Numbers that depend on radar results are `[TBD: …]`. Wording rules: `product.md`.

## 1. What the form requires (read from the official guides, 14 Nov 2026)
Sources: [Project Submission Guide](https://www.spaceappschallenge.org/resources/project-submission-guide/) ·
[Judging & Awards Guide](https://www.spaceappschallenge.org/resources/judging-awards-guide/) (both dated 13 Nov 2026).

**Deadline:** click "Submit for Judging" before **Sun 15 Nov, 23:59 local time** of our Local Event (Barcelona).
Our own target stays Sun 22:00 (`plan.md`). Resubmitting is allowed until the deadline; the last save counts.
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
| Criterion | What earns a 5 | How we answer it |
|---|---|---|
| Impact | significant problem, broad reach | regulators can't inspect everything; Muhos shows months of change before anyone stepped in |
| Creativity | new approach or meaningful improvement | change detection + automatic record check + a plain-language label, not just a change map |
| Validity | scientifically sound, feasible, usable | physics per change type (`sar-primer.md` §8), real NISAR passes, labels with reasons, made for non-experts |
| Relevance | NASA data is the core, not decoration | NISAR GCOV finds and dates the changes; OPERA fills the years before NISAR |
| Presentation | clear, engaging story | the guided tour is the demo; one story per site |

## 2. Name, summary, description

**Name options** (one-line taglines; the Python package is already called `sarwatch`):
1. **SARwatch**: "Radar finds where the land changed. Public records say which changes need a second look."
2. **Second Look**: "Every change on the ground, sorted by how much it deserves a regulator's attention."
3. **Through the Clouds**: "Satellite radar keeps watch over forests and fields in any weather, and explains what it saw."

**High-level summary (≤150 words):**
> We built a web app that watches land with satellite radar and tells regulators, in plain language, which changes
> look expected and which deserve a closer look. NASA–ISRO's NISAR radar sees through clouds and darkness, so the app
> detects forest clearing, new buildings and earthworks every few days, whatever the weather. For each change it
> checks public records: protected areas, zoning, the land registry, solar-plant permits, recorded wildfires. It then
> labels the change Expected, Needs review or High concern, always with the reason and the before-and-after evidence.
> A timeline shows changes piling up over months and years. We tested it on Muhos, Finland, where about 330 hectares
> of forest were cleared for a data centre before the required environmental assessment was finished, and applied it
> to Catalonia. Regulators cannot inspect every hectare; this shows them where to look first.

(≈140 words.)

**Detailed description** (draft for the form; plain engineering language):

*What it does.* The app shows a map of a region with every detected land change drawn as a coloured shape. Colour =
label: Expected, Needs review, High concern. Clicking a change opens a card: what changed (forest cleared, new
structure, earth moved), where, roughly when, how big, the label and the reason behind it, before-and-after pictures,
and a chart of the radar signal over time with one plain sentence explaining it. A timeline slider replays when each
change first appeared. A guided tour walks a first-time user through three places: Muhos (Finland), Agroparc Penedès
(Catalonia) and an overview of Catalonia. The app never decides whether a change breaks a rule; a label is a reason to
look, with the evidence attached.

*How it works.*
1. **Radar stack.** For each site we read small windows of NISAR GCOV images (L-band, 24 cm wavelength, calibrated
   backscatter, 20 m pixels) over HTTPS without downloading the multi-GB files: 11 passes from late June to early
   November 2026 per site [TBD: final count]. Older years come from OPERA RTC-S1 (Sentinel-1, C-band, 30 m, from 2016).
2. **Change detection.** Radar images are grainy (speckle), so we average neighbouring pixels in linear power, compare
   the early-period median with the late-period median in dB, keep changes above a threshold that persist across
   passes, date each pixel by the first pass where the change shows, and group pixels into regions of at least 0.5 ha.
3. **Change type from physics.** Cross-polarised power (HV) comes from volume scattering in canopy, so a large HV drop
   means trees are gone. A jump in co-polarised power (HH) that stays means walls and ground now form corner
   reflectors: a new structure. Unstable signal in both means the ground surface keeps being reshaped: earthworks.
   L-band reaches through leaves to branches and trunks, which makes forest loss clearer than at C-band.
4. **Optical cross-check.** OPERA DIST-ALERT-HLS vegetation-loss alerts (from Landsat and Sentinel-2) date clearing
   before NISAR's calibrated record starts and give candidate areas across all of Catalonia; radar confirms them
   through cloud.
5. **Record check → label.** Each change is checked against public records: protected areas (PEIN / Natura 2000),
   the urban-planning map (urban, buildable or protected land), cadastre buildings, the solar-plant register and
   recorded wildfires. Inside a protected area, or a large clearing on non-buildable land with no record → High
   concern. No record explains it → Needs review. Matching record, or natural (a recorded fire) → Expected.
6. **Static web app.** All results are precomputed into small GeoJSON / JSON / PNG files. The app is plain HTML and
   JavaScript with MapLibre GL JS, no server and no build step, so it runs from GitHub Pages.

*Results.* Muhos: [TBD: hectares detected, first-seen dates vs. the reported March–August clearing]. Agroparc:
[TBD: earthworks area and dates]. Catalonia: [TBD: number of changes per label]. False-positive check: recorded
wildfires come out Expected [TBD: confirm on real data].

*Benefits.* Regulators see where to look first instead of searching everywhere; every label carries its reason and
evidence; it works in winter and under cloud; it uses only free, open data, so any region can run it.

*What's next.* Run it continuously over a whole region; add ground sinking and rising from InSAR (EGMS, NISAR
interferograms); connect permit registers as they go online; let inspectors mark a change as checked.

*Tools.* Python (h5py, rasterio, numpy, asf-search, earthaccess), NASA Earthdata Login, GitHub, MapLibre GL JS,
plain HTML / CSS / JavaScript, Claude Code (see §5).

## 3. Demo (video, ≤30 s)
The strategy, the 30-second storyboard and the 3-minute live pitch are in [`demo-strategy.md`](demo-strategy.md): one
story (Muhos), one card, one wide shot of Catalonia; the tour in `app/tour.json` drives both the video and the pitch.

If the team prefers slides: 7 slides (title + team and challenge · the Muhos problem · the app · how it works · a
Catalan card · Catalonia overview · what's next), one screenshot each.
Caution: the narration must not say anyone did something unlawful; it states what was reported (§6 sources).

## 4. Data used
**NASA** (all free and open under NASA's Earth science data policy; access via [Earthdata Login](https://urs.earthdata.nasa.gov)):
| Dataset | Used for | Link |
|---|---|---|
| NISAR L2 GCOV (L-band backscatter HH/HV, provisional and validated) | detecting and dating changes, Jun–Nov 2026 | [ASF](https://search.asf.alaska.edu/#/?dataset=NISAR) · [docs](https://nisar-docs.asf.alaska.edu/) |
| OPERA RTC-S1 (Sentinel-1 backscatter, 30 m, 2016→) | the radar history before NISAR | [guide](https://hyp3-docs.asf.alaska.edu/guides/opera_rtc_product_guide/) |
| OPERA DIST-ALERT-HLS (vegetation-loss alerts, 30 m, 2023→) | dating the Muhos clearing before June; Catalonia candidates | [LP DAAC](https://www.earthdata.nasa.gov/data/catalog/lpcloud-opera-l3-dist-alert-hls-v1-1) |
| NISAR mission resources, Earthdata SAR intro | background and wording | [NISAR applications](https://nisar.jpl.nasa.gov/applications/societal-benefit/) |

**Space agency partners and others:**
| Dataset | Used for | Licence |
|---|---|---|
| Copernicus Sentinel-1 (ESA; inside OPERA RTC-S1) | radar history | free and open; credit "contains modified Copernicus Sentinel data" |
| Copernicus Sentinel-2 via EOX Sentinel-2 cloudless (2017–2025) | yearly photo basemap outside Catalonia | CC BY-NC-SA 4.0 for most years (unverified per year): credit EOX |
| ICGC orthophotos (aerial photos, yearly) | yearly photo basemap and before/after pictures in Catalonia | CC BY 4.0 (unverified): credit ICGC |
| PEIN + Natura 2000 (Generalitat / Diputació de Barcelona) | protected-area check | Catalan open data (unverified) |
| Urban-planning map MUC, development sectors, solar-plant register (Generalitat open data) | zoning and permit checks | Catalan open data (unverified) |
| Spanish cadastre, INSPIRE buildings WFS (Dirección General del Catastro) | building records | open, attribution required (unverified) |
| Esri World Imagery, OpenStreetMap | modern basemap | Esri terms (attribution shown) · ODbL |
| MapLibre GL JS | map rendering | BSD-3-Clause |

The full list of datasets and how we query them is in `data-sources.md`.

## 5. AI-use disclosure (for the "Use of SI" field and the README)
> The team chose the challenge, the idea and the sites. We used Claude (Anthropic's AI models, through Claude Code)
> as a programming and writing assistant under our direction: it wrote most of the code and documentation, researched
> candidate cases and data sources for us to choose from, and checked cited sources. Humans set the goals, decided
> every design question and reviewed the results. Every file Claude wrote carries a "Written by Claude" note, and
> the git history shows who made each change. No AI-generated images, video or audio are used. The radar results
> come from NASA data processed by our code, not from an AI model.

Before submitting: confirm the last two sentences still hold (if the video uses an AI voice or generated pictures,
they need a watermark and a mention).

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
2. Which project name: SARwatch, Second Look, or Through the Clouds? (Recommendation: SARwatch; it matches the code.)
3. Demo as a 30-second video? (Recommendation: yes; the timeline replay is the strongest moment and needs motion.)
4. Narrate with our own voices (no AI voice), so no watermark is needed? (Recommendation: yes.)
5. "Link to Final Project" = the GitHub Pages app, with the repo linked from its README? (Recommendation: yes.)

<sub>Written by Claude</sub>
