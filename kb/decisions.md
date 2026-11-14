# Decisions

One line each: `date · decision · why · issue`. Newest at the bottom.

- 2026-11-14 · Coordinate agents via GitHub Issues (no shared state files) · works across 3 machines, no merge conflicts · #1
- 2026-11-14 · Tian's Claude = orchestrator; Tomi's + Andrea's = workers · Tian runs the stronger model · #1
- 2026-11-14 · Self-merge kb/explore/docs PRs; Tian reviews shared code · speed without losing consistency · #1
- 2026-11-14 · No `@claude` GitHub Action for now · local CLIs cover it; no tokens in the repo; can add later · #1
- 2026-11-14 · Repo private now, public before submission (after a personal-data check) · #1
- 2026-11-14 · **Pivot:** drop the datacenter angle; build a radar land-change monitor that flags expected vs needs-review changes for regulators · broader impact, clearer story; inspired by Google's Finland clear-cut · #6
- 2026-11-14 · Pilot region **Catalonia**: overview of the whole region + 2–3 detailed hotspots · local relevance, data available, scope fits 30 h · #6
- 2026-11-14 · Detect 4 change types: forest clearing, new buildings, earthworks/flattening, ground height change · team choice · #6
- 2026-11-14 · Verdict = radar change + public government data where queryable, else simple rules; label "needs review", never "illegal" · radar sees change, not legality · #6
- 2026-11-14 · Google Finland clear-cut (Muhos/Kajaani) = test case, with NISAR (covered since Jun 2026) · strongest demo moment · #6
- 2026-11-14 · Timeline slider showing changes piling up over weeks/months/years · overview of long-term change for decision makers · #6
- 2026-11-14 · Keep data small (enough for motivation + demo); NASA data required, Copernicus/GEE allowed; ships out of scope · deadline · #6
- 2026-11-14 · Agents commit small and push their branch after every commit · visibility + no lost work · #6
- 2026-11-14 · Demo sites: Muhos (Finland) + Agroparc Penedès + coarse Catalonia overview · keep it small; one test case, one Catalan case · #10
- 2026-11-14 · Tracks: Tian's agent radar, Tomi web app, Andrea verdict; fixed data contract between them · parallel work without waiting · #10
- 2026-11-14 · Process radar data in the cloud (Codespace), store only small results in the repo · team is on mobile data · #10
- 2026-11-14 · No Google Earth Engine: OPERA RTC-S1 + DIST-ALERT via Earthdata Login cover history and overview · nobody has an account; one credential is enough · #10
- 2026-11-14 · Web app is a static site with no build step (MapLibre from a CDN) · nothing to break, hosts anywhere · #10
- 2026-11-14 · Every assignment names the model; the orchestrator model only orchestrates, implementation runs on Opus/Sonnet · cost and role clarity · #10
- 2026-11-14 · Radar files may be downloaded and processed on laptops, the Codespace stays optional; still only small results in the repo · the team moved to fast wifi at 16:00 · #9
- 2026-11-14 · Work ships as small pilots humans can look at; a checkpoint where all three humans run the app and steer · decide from what we see, not from text (Tomi's proposal) · #9
- 2026-11-14 · Every PR that changes the app or its data carries a picture in `docs/screenshots/` · Tian: pictures at every stage · #9
- 2026-11-14 · Each "done" note ends with at most two yes/no questions for the humans; after about midnight the orchestrator decides alone and logs it here · the humans sleep, the work continues · #9
- 2026-11-14 · Adopted from Tomi's lists: record layers, Catalonia from optical alerts, minimum-size slider, "why this label" checklist, shareable link, CSV download, "play Muhos". Rejected: click-anywhere record lookup · cheap, visible, useful to a regulator; the rejected one depends on government services allowing browser requests · #45 #50 #51 #52
- 2026-11-14 · OPERA DIST-ALERT optical alerts also date the Muhos clearing before NISAR's first calibrated pass (25 Jun) · most of the ~330 ha was cut earlier, and Sentinel-1 reads wait for an account approval · #44
- 2026-11-14 · Record layers live in `<site>/context/` (`index.json` + one GeoJSON per layer) · the data side and the app side can build in parallel · #45 #52
- 2026-11-14 · A second orchestrator-level agent plans and hands out work; the main one reviews, merges and runs the radar sub-agents · keeps teammates supplied with work · #9
- 2026-11-14 · Every agent reviews its own PRs with its own Opus reviewer sub-agent and merges them itself; Tomi's agents review the orchestrator's radar PRs · removes the review queue in front of the orchestrator · #64 #70
- 2026-11-14 · Licence: MIT for the code · Tian's answer · #48
- 2026-11-14 · The repo is public since 16:49 (Tomi); GitHub Pages becomes the shared preview · one link for humans and jury; from now on nothing personal in commits, issues or comments · #48
- 2026-11-14 · Thinking tasks (design, demo strategy, evidence check) go to Tomi's Fable session; implementation stays on Opus / Sonnet · Tomi has Fable quota · #60 #78
- 2026-11-14 · Several sensors, one change: mutual 30 % overlap plus overlapping time windows; date = first positive sighting, with that source's window; a silent source never lowers confidence; format additions optional · no duplicates, no overclaimed dates · #60 #65 #66 #77
- 2026-11-14 · Demo: the claim is "a short, explained list of land changes a regulator should look at first"; the 30 s video shows Muhos only; the Muhos cleared-area curve is the first build request · `demo-strategy.md` · #49 #73
- 2026-11-14 · Verdict rules: inside a recorded wildfire perimeter → expected; a protected-area overlap below 10 % of the change is a neutral "borders" reason; a pending solar application → needs review; small low-confidence changes are not flagged on their own · rule decisions on #9 · #46 #47
- 2026-11-14 · The Muhos `scope` polygon is the outline of the 358 ha optical-alert patch; the site centre moves 3.3 km east-southeast · the alerts match the reported ~330 ha · #44
- 2026-11-14 · `story.json` may carry a chart (`chart` → a file in the `series/` format) · the Muhos cleared-area curve in the story panel · #73
- 2026-11-14 · Muhos final data: inside the clearing outline the optical alerts carry the outlines and dates (one change per month, 7 parts, 358.8 ha), Sentinel-1 and NISAR are attached as `sources` with their share and own date; outside it `merge.merge_detections` runs as designed · a three-source merge of the small parts gave 58 overlapping changes, and the radars date the block's edges early · #27, #77
- 2026-11-14 · Muhos review fixes: inside the clearing outline the optical date and outline win, and the window opens at a radar's last unchanged pass where that radar saw the whole part changed earlier; undated radar shares get roles that match their notes; part outlines are smoothed (holes under 1 ha filled, 1-pixel gaps closed, area within 3 %) · multi-sensor-design §2 exception · #27, #95
- 2026-11-14 · App look: one token system in `style.css`, Funnel fonts self-hosted, neutral chrome with one green action colour; the Marked areas switch hides the overlay; new changes appear without a glow · the map picture is the hero, strong colour stays reserved for verdicts, radar pink and red bars · #41
- 2026-11-14 · Barcelona site (50 × 39 km): Sentinel-1 reads the three IW2 bursts of track 132 as one mosaic per date (one 30 m lattice, no resampling) instead of tiles; NISAR 130 / 22 covers it whole · one stack = one detection, no seams; same track as Agroparc · #44, PR #110
- 2026-11-14 · The product name is Parallax (was the working title SARwatch) · decided by Tian; the Python package, folders and commands keep `sarwatch` · #112

<sub>Written by Claude</sub>
