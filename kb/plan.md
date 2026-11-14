# Build plan

How we get from the brief (`product.md`) to a submitted app by Sun 15 Nov, 22:00. Approved by Tian on 14 Nov 2026,
13:30; updated 14 Nov 17:00 (repo public, several sensors → one change, demo strategy, optical-alert finding). Last
updated 2026-11-14. Live state: #1. Assignments: #9. The hand-off format: `data-contract.md`.

## Decisions behind the plan
- **Demo sites:** Muhos, Finland (Google's clearing, the test case) · **Agroparc Penedès** (258 ha earthworks) ·
  a coarse **all-Catalonia overview**. Other cases in `project-context.md` §7 are not detailed sites.
- **Tracks:** Tian's agent = radar · Tomi = web app · Andrea = verdict. Tian's agent also orchestrates.
- **Every assignment names the model** (Sonnet 5.5 or Opus 5.5). Thinking tasks (design, demo strategy, evidence
  check) go to Tomi's Fable session; implementation never runs on Fable.
- **Review:** every agent reviews its own PRs with its own Opus reviewer sub-agent and merges them itself
  (`AGENTS.md`); Tomi's agents review the orchestrator's radar PRs (#70).
- **One account type only:** NASA Earthdata Login. No Google Earth Engine.
- **Only small results enter the repo** (PNG, GeoJSON, JSON). Radar files may be downloaded and processed on
  laptops (fast wifi since Sat 16:00); the Codespace (`.devcontainer/`) stays as an option.
- **Web app:** static site with no build step (HTML + ES modules, MapLibre GL JS from a CDN). The repo is public
  since Sat 16:49; hosting is GitHub Pages as soon as Tomi switches it on.
- **Humans steer from what they can see:** work ships as small pilots; every PR that changes the app or its data
  carries a picture (`docs/screenshots/`); each "done" note ends with at most two yes/no questions for the humans.
  After about midnight the orchestrator decides alone and logs it in `decisions.md`.
- **Several sensors, one change:** `multi-sensor-design.md` (confirmed). **Demo:** `demo-strategy.md`: the claim,
  a 30 s video that shows Muhos only, the 3-minute pitch, and its build requests in priority order.

## How it fits together
```
 radar files (laptop or Codespace)              repo: app/data/ (small files)            browser
 NISAR GCOV crops ─┐   detections per source
 OPERA RTC-S1 crops├─► ─► merge into one list ─► <site>/changes.geojson ──┐
 OPERA DIST-ALERT ─┘   (Tian's agent)            <site>/layers, evidence  ├─► static web app (Tomi)
                                                 <site>/series/*.json     │   map · timeline · change card · list
 public records (protected areas, zoning,                                 │
 land registry, solar list, wildfires) ─► verdict step ─► verdict + reasons┤
                               (Andrea)  └► <site>/context/ record layers ─┘
```
- **Radar method:** same-track image stack → average neighbouring pixels in linear power (speckle) → per pixel,
  compare the early median with the late median in dB → keep changes above a threshold that persist → date each
  pixel by the first pass where it shows → group into regions → type by rule (cross-pol HV drops = clearing;
  co-pol HH jumps = structure; unstable both ways = earthworks). NISAR covers Jun–Nov 2026.
- **History before NISAR:** OPERA Sentinel-1 (30 m, from 2016; downloaded for both sites) and OPERA DIST-ALERT
  optical alerts (#44). The alerts show the Muhos clearing as one 358 ha patch, month by month from spring 2026.
- **One change per place:** detections from different sources that overlap mutually by ≥ 30 % and in time become
  one change, dated by the first positive sighting; a change already under way when a record begins is a "late
  start" and is never dated to that first pass (`multi-sensor-design.md`).
- **Catalonia overview:** optical vegetation-loss alerts (a date per pixel, 2023→) give candidates region-wide;
  radar confirms the largest. Wording in the app: "an optical alert finds it, radar confirms it through clouds".
  Wildfires are labelled as expected through the wildfire lookup.
- **Timeline slider:** every change has a `first_date`; the app shows changes with `first_date ≤ slider`, and a
  coverage strip shows which satellites were watching on that date.
- **Record layers:** what the public records say about the land, as switchable map layers, first at Agroparc.
- **Ground height change:** no site was picked for it, so it is a stretch item (EGMS overlay) and the first cut.

## Coverage we confirmed (ASF search API, 14 Nov)
| Site | NISAR GCOV | OPERA Sentinel-1 (RTC-S1) |
|---|---|---|
| Muhos (clearing centred near 26.111, 64.835) | 4 tracks × 9–12 calibrated dates, 21 Jun → 4 Nov; used: track 157 / frame 35 ascending, 11 dates read | 2,413 scenes, 2016→ |
| Agroparc (1.85, 41.45) | used: track 130 / frame 22 ascending, 11 dates read, 23 Jun → 2 Nov · track 66 / frame 68 descending: 16 dates from Nov 2025, mixed maturity | 1,552 scenes, 2016→ (earliest 17 Apr 2016) |

## Who owns which files (disjoint, so no merge conflicts)
| Owner | Paths |
|---|---|
| Tian's agent | `pyproject.toml`, `.devcontainer/`, `src/sarwatch/{contract,nisar,s1,change,export,pipeline,distalert,merge}.py`, `explore/`, `app/data/sites.json`, `app/data/<real site>/` except `story.json`, `records.json`, `context/`, `kb/plan.md`, `kb/data-contract.md` |
| Andrea | `src/sarwatch/context/`, `src/sarwatch/verdict.py`, `kb/verdict-rules.md`, `app/data/<site>/{story.json,records.json,context/}` |
| Tomi | `app/` except `app/data/` · `README.md`, `LICENSE`, `.github/` · `kb/{submission,demo-strategy,multi-sensor-design,evidence-check}.md` |

`docs/screenshots/` is shared: name files `<issue>-<what>.jpg`. Need a contract change? Ask on #9; don't edit
`contract.py` or `data-contract.md` yourself. The verdict step writes into `changes.geojson` through its one
documented command ("Run on a site" in `verdict-rules.md`), which the radar track re-runs after every regeneration.
Shared app files, in merge order: `panel.js`: #51 → #73 → #74 · `main.js`: #75, #50 · `inbox.js`, `map.js`: #50,
#52, then #76.

## Tasks
**Done (issue):** S0 plan, contract, fixture #10 · R1 NISAR reader #15 · R2 change core #11 · R3 Sentinel-1 reader
#22 · R7 exporter #21 · V1 record lookups #14 · V2 verdict rules #17 · V3 site stories + Muhos records #39 · V4
wildfire lookup #47 · A1 app skeleton #13 · A2 card evidence #18 · A3 photo basemap, explainer, tour #25 · A5 review
inbox #34 · E3 multi-sensor fields in the format + fixture #66 · W1 submission draft #49 · W2 licence, README, Pages
workflow, repo public #48 · thinking tasks: several sensors → one change #60, demo strategy (PR #67).

| ID | Who · model | Goal → output | Issue · state (14 Nov 17:00) |
|---|---|---|---|
| R4 | Tian's agent (Opus sub-agent) | **Muhos end to end**, NISAR + Sentinel-1 → `app/data/muhos/` | #27: PR #55, fix list from the review |
| R5 | Tian's agent (Opus sub-agent) | **Agroparc end to end**, NISAR + Sentinel-1 from 2016 → `app/data/agroparc/` | #36: PRs #57, #68 |
| R8 | Tian's agent (Opus sub-agent) | North-up card pictures; date wording, `time_range`, `bbox` in the export | #37: PR #62 in review |
| R6 | Tian's agent (Opus sub-agent) | Optical alerts: the reader is merged (PR #72); next the alerts in the Muhos data and the `scope` polygon, then `app/data/catalonia/` | #44 step 2 |
| E1 | Tian's agent (Opus sub-agent) | `merge.py`: detections from several sources → one change | #65 running |
| E2 | Tian's agent (Sonnet sub-agent) | The exporter calls the merge: `sources`, `not_before`, the sentences; site `sources` | #77: after #62 and #65 |
| V5 | Andrea · Opus 5.5 | Record layers for Agroparc, data side → `app/data/agroparc/context/` | #45 running |
| V6 | Andrea · Sonnet 5.5 | Verdicts on the real sites; fix lists from the #31 and #59 reviews | #46: PR #59; the real run waits for tuned data + `scope` |
| V7 | Andrea · Opus 5.5 | Labels on the Catalonia overview; showcase cards for the pitch | #79: part 1 after #45, part 2 after #44 step 2 |
| A6 | Tomi · Sonnet 5.5 | App findings from the check against real data | #41 |
| A8 | Tomi · Opus 5.5 | "Why this label?" checklist on the card | #51: PR #69 |
| A11 | Tomi · Opus session (Sonnet-level) | Muhos cleared-area curve in the story panel (`story.json` → `chart`) | #73 |
| A12 | Tomi · Opus session (Sonnet-level) | Card: "when" wording, "seen by" list, confidence note | #74 |
| A9 | Tomi · Opus session (Sonnet-level) | Record layer switches (app side) | #52 |
| A13 | Tomi · Sonnet 5.5 | Timeline: coverage strip, "watching on this date", start markers | #75 |
| A7 | Tomi · Sonnet 5.5 | Shareable link, CSV download, minimum-size slider | #50 |
| A14 | Tomi · Sonnet 5.5 | Small changes above large ones, "two sources" filter, chart marks | #76: last; first to cut |
| F3 | Tomi · Fable | Evidence check: do the results carry the demo claim; go / no-go per site; fallback story → `kb/evidence-check.md` | #78 |
| — | Tomi's agents · Opus, medium effort | Review duty for the radar PRs | #70 |
| A10 | Tomi · Opus 5.5 | "Play Muhos" replay + tour steps that follow the pitch, with real dates and ids | no issue yet: needs Muhos data and verdicts on `main` |
| A4 | Tomi · Sonnet 5.5 | Polish and phone-width check, from the checkpoint feedback | no issue yet |
| W1 | Humans, with Tomi's agents | Final submission texts, the 30 s video, the project page | Sun, from `submission.md` and `demo-strategy.md` |

## Human tasks
1. **Tomi:** switch GitHub Pages on (Settings → Pages → Source: GitHub Actions) and post the link on #9.
2. **Each human:** commit e-mail in the public history (scan report on #48): accept, and use the GitHub noreply
   address from now on?
3. **Everyone, at the checkpoint:** open the app (Pages link, or `git pull` and `python -m http.server 8000 -d app`),
   look, answer the questions on #9.
4. **Anyone:** yes/no on #9: a 30 s narrated video as the demo, the name Parallax · send the questions in #7 to the
   specialist · confirm the **local pitch time** (if pitches are Sunday afternoon, the freeze moves earlier).

## Milestones (local time)
| When | What must be true |
|---|---|
| Sat 14:30 | S0 merged, issues created, assignments on #9 (met) |
| Sat 17:30 | **M1:** a NISAR crop read works and is measured · record lookups answer for Agroparc · the app shows the fixture with a working slider (met) |
| Sat evening | **Checkpoint:** Muhos and Agroparc real data on `main`; the three humans open the app and steer |
| Sat 21:30 | **M2:** Muhos real changes → verdicts → visible in the app |
| Sun 11:00 | **M3:** Muhos + Agroparc + Catalonia overview in the app, cards complete |
| Sun 16:00 | **Freeze:** fixes, wording and visuals only |
| Sun 19:00 | Deployed, submission text and video drafted |
| Sun 22:00 | Submitted (the form closes 23:59; resubmits are allowed) |

## Risks and fallbacks
- **Mixed NISAR maturity** (beta / provisional / validated) can fake change → one track per site, provisional or later.
- **Muhos:** the clearing was mostly cut before NISAR's first calibrated pass (25 Jun). The optical alerts carry
  the months before (358 ha, close to the reported ~330 ha); NISAR shows the growth after June; Sentinel-1 fills
  the gap. Frozen ground in the 4 Nov pass and snow in March distort radar; the app says so. The patch lies 3.3 km
  east-southeast of the centre we first used, so the site centre and the tour framing move.
- **Agroparc:** seasonal farmland change drowns an untuned run, and the optical alerts there are dominated by the
  2023 drought, so radar carries the site. Our sources don't confirm that works have started. The evidence check
  (#78) gives the go / no-go and ranks the fallback cases from `project-context.md` §7.
- **Records are thin** (permits are PDFs) → the verdict falls back to rules; wording stays "needs review".
- **Cut order if behind:** ground-height layer → #76 → CSV and size slider (#50) → "play Muhos" replay → picture
  swipe → Catalonia overview → year-synced photo basemap. **Never cut:** Muhos, Agroparc, the verdict card, the
  timeline, the Muhos cleared-area curve.

## How we check it works
- `python -m pytest`: change core on synthetic stacks; contract validator on the fixture and the real sites.
- Sanity numbers: Muhos clearing vs the reported ~330 ha (same order of magnitude; state the gap) · Agroparc changes
  fall inside the project outline · unchanged forest nearby stays below the threshold.
- Verdict: each rule has a fixture case with the expected label; every reason's source link opens.
- App: `python -m http.server 8000 -d app`, click through each site: the slider reveals changes in date order, the
  card shows pictures + chart + reasons, phone width has no sideways scroll. Every PR shows it in a picture.
- Before the freeze: fresh clone → the app runs from committed data only, with no credentials.

<sub>Written by Claude</sub>
