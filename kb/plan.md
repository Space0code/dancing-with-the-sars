# Build plan

How we get from the brief (`product.md`) to a submitted app by Sun 15 Nov, 22:00. Approved by Tian on 14 Nov 2026,
13:30; updated 14 Nov 16:30 (fast wifi, checkpoint, Tomi's proposals adopted). Last updated 2026-11-14. Live state:
#1. Assignments: #9. The hand-off format: `data-contract.md`.

## Decisions behind the plan
- **Demo sites:** Muhos, Finland (Google's clearing, the test case) · **Agroparc Penedès** (258 ha earthworks) ·
  a coarse **all-Catalonia overview**. Other cases in `project-context.md` §7 are not detailed sites.
- **Tracks:** Tian's agent = radar · Tomi = web app · Andrea = verdict. Tian's agent also orchestrates.
- **Every assignment names the model** to use (Sonnet 5.5 or Opus 5.5).
- **One account type only:** NASA Earthdata Login. No Google Earth Engine.
- **Only small results enter the repo** (PNG, GeoJSON, JSON). Since Sat 16:00 the team is on fast wifi, so radar files
  may be downloaded and processed on laptops; the Codespace (`.devcontainer/`) stays as an option.
- **Web app:** static site with no build step (HTML + ES modules, MapLibre GL JS from a CDN). Hosting: GitHub Pages
  once the repo is public (#48 prepares it).
- **Humans steer from what they can see** (Tomi's proposal, adopted): work ships as small pilots; every PR that
  changes the app or its data carries a picture (`docs/screenshots/`); each "done" note ends with at most two yes/no
  questions for the humans. After about midnight the orchestrator decides alone and logs it in `decisions.md`.

## How it fits together
```
 radar files (laptop or Codespace)              repo: app/data/ (small files)            browser
 NISAR GCOV crops ─┐
 OPERA RTC-S1 crops├─► radar change detection ─► <site>/changes.geojson ──┐
 OPERA DIST-ALERT ─┘   (Tian's agent)            <site>/layers, evidence  ├─► static web app (Tomi)
                                                 <site>/series/*.json     │   map · timeline · change card · list
 public records (protected areas, zoning,                                 │
 land registry, solar list, wildfires) ─► verdict step ─► verdict + reasons┤
                               (Andrea)  └► <site>/context/ record layers ─┘
```
- **Radar method:** same-track image stack → average neighbouring pixels in linear power (speckle) → per pixel,
  compare the early median with the late median in dB → keep changes above a threshold that persist → date each
  pixel by the first pass where it shows → group into regions ≥0.5 ha → type by rule (cross-pol HV drops = clearing;
  co-pol HH jumps = structure; unstable both ways = earthworks). NISAR covers Jun–Nov 2026.
- **History before NISAR:** OPERA Sentinel-1 (30 m, from 2016; reads wait for an approval on the Earthdata account)
  and OPERA DIST-ALERT optical alerts (#44), which date the Muhos cutting from before 25 Jun.
- **Catalonia overview:** OPERA DIST-ALERT-HLS vegetation-loss alerts (a date per pixel, 2023→) give candidates
  region-wide; NISAR crops confirm the largest. Wording in the app: "an optical alert finds it, radar confirms it
  through clouds". Wildfires are labelled as expected through the wildfire lookup (#47).
- **Timeline slider:** every change has a `first_date`; the app shows changes with `first_date ≤ slider`.
- **Record layers:** what the public records say about the land, as switchable map layers, first at Agroparc.
- **Ground height change:** no site was picked for it, so it is a stretch item (EGMS overlay) and the first cut.

## Coverage we confirmed (ASF search API, 14 Nov)
| Site | NISAR GCOV | OPERA Sentinel-1 (RTC-S1) |
|---|---|---|
| Muhos (26.044, 64.843) | 4 tracks × 9–12 calibrated dates, 21 Jun → 4 Nov; used: track 157 / frame 35 ascending, 11 dates read | 2,413 scenes, 2016→ |
| Agroparc (1.85, 41.45) | used: track 130 / frame 22 ascending, 11 dates read, 23 Jun → 2 Nov · track 66 / frame 68 descending: 16 dates from Nov 2025, mixed maturity | 1,552 scenes, 2016→ (earliest 17 Apr 2016) |

## Who owns which files (disjoint, so no merge conflicts)
| Owner | Paths |
|---|---|
| Tian's agent | `pyproject.toml`, `.devcontainer/`, `src/sarwatch/{contract,nisar,s1,change,export,pipeline,distalert}.py`, `explore/`, `app/data/sites.json`, `app/data/<real site>/` except `story.json`, `records.json`, `context/`, `kb/plan.md`, `kb/data-contract.md` |
| Andrea | `src/sarwatch/context/`, `src/sarwatch/verdict.py`, `kb/verdict-rules.md`, `app/data/<site>/{story.json,records.json,context/}` |
| Tomi | `app/` except `app/data/` · `README.md`, `LICENSE`, `.github/` (#48) · `kb/submission.md` (#49) |

`docs/screenshots/` is shared: name files `<issue>-<what>.jpg`. Need a contract change? Ask on #9; don't edit
`contract.py` or `data-contract.md` yourself. The verdict step writes into `changes.geojson` through its one
documented command (#46), which the radar track re-runs after every regeneration.

## Tasks
| ID | Who · model | Goal → output | Issue · state (14 Nov 16:30) |
|---|---|---|---|
| S0 | Tian's agent | Plan, contract, fake fixture site, project setup | #10 done |
| R1 | Tian's agent | NISAR crop reader, measured; `nisar.py` | #15 done |
| R2 | Tian's agent | `change.py`: stack → dB change, first-change date, regions, series | #11 done |
| R3 | Tian's agent | `s1.py`: OPERA Sentinel-1 crops as the same kind of stack | #22: reader merged; live reads wait for the account approval |
| R7 | Tian's agent | `export.py`: changes → the app data format | #21 done |
| R4 | Tian's agent (Opus sub-agent) | Site runner; **Muhos end to end** → `app/data/muhos/` | #27: runner merged; tuning on 11 dates |
| R5 | Tian's agent (Opus sub-agent) | **Agroparc end to end** → `app/data/agroparc/` | #36: tuning on 11 dates |
| R8 | Tian's agent (Opus sub-agent) | North-up card pictures; real dates, `time_range`, `bbox` in the export | #37 in progress |
| R6 | Tian's agent (Opus sub-agent) | Optical alerts: Muhos history, then the Catalonia overview → `distalert.py`, `app/data/catalonia/` | #44 in progress |
| V1 | Andrea · Opus 5.5 | Record lookups in `src/sarwatch/context/` | #14 done |
| V2 | Andrea · Sonnet 5.5 | `verdict.py`: rules → verdict + reasons + plain sentence; `official` record key | #17: PR #31, fixes pushed |
| V3 | Andrea · Sonnet 5.5 | Site stories + hand-entered Muhos records | #39: PR #42 in review |
| V5 | Andrea · Opus 5.5 | Record layers for Agroparc, data side → `app/data/agroparc/context/` | #45 |
| V6 | Andrea · Sonnet 5.5 | Verdicts on the real sites: dry run on trial data, then the real run | #46 |
| V4 | Andrea · Sonnet 5.5 | Wildfire lookup, so burn scars come out "expected" | #47 |
| V7 | Andrea · Opus 5.5 | Lookups and labels on the Catalonia overview | no issue yet: after #44 and #45 |
| A1 | Tomi · Sonnet 5.5 | App skeleton on the fixture | #13 done |
| A2 | Tomi · Sonnet 5.5 | Card evidence: swipe, signal chart, reasons, picture overlays | #18 done |
| A3 | Tomi · Opus 5.5 | Photo basemap by year, explainer, guided tour | #25: PR #38 merged |
| A5 | Tomi · Sonnet 5.5 | Review inbox: sortable, filterable list of changes | #34: PR #40, merge chain |
| A6 | Tomi · Sonnet 5.5 | Check the app against real radar output | #41: PR #43 (partial), rest after the merge chain |
| A7 | Tomi · Sonnet 5.5 | Shareable link, CSV download, minimum-size slider | #50: after the merge chain |
| A8 | Tomi · Opus 5.5 | "Why this label?" checklist on the card | #51: after the merge chain |
| A9 | Tomi · Sonnet 5.5 | Record layer switches (app side) | #52: after the merge chain |
| A10 | Tomi · Opus 5.5 | "Play Muhos" replay + tour steps with real dates and ids | no issue yet: needs real dates on `main` |
| A4 | Tomi · Sonnet 5.5 | Polish and phone-width check, from the checkpoint feedback | no issue yet |
| W1 | Tomi · Opus 5.5 drafts, humans finish | Submission pack → `kb/submission.md` | #49 |
| W2 | Tomi · Sonnet 5.5 prepares, Tomi (human) flips | Personal-data scan, LICENSE, README, Pages; make the repo public | #48 |

## Human tasks
1. **Tian:** approve the ASF data-use agreement for the Earthdata account (link in #1): it unblocks Sentinel-1 history.
2. **Tomi + Tian:** yes/no on #9: make the repo public tonight once the scan in #48 is clean · MIT licence.
3. **Everyone, at the checkpoint:** `git pull`, `python -m http.server 8000 -d app`, look, answer the questions on #9.
4. **Anyone:** send the questions in #7 to the specialist · confirm the **local pitch time and submission checklist**
   (if pitches are Sunday afternoon, the freeze moves earlier) · pick an app name.

## Milestones (local time)
| When | What must be true |
|---|---|
| Sat 14:30 | S0 merged, issues created, assignments on #9 (met) |
| Sat 17:30 | **M1:** a NISAR crop read works and is measured · record lookups answer for Agroparc · the app shows the fixture with a working slider (met) |
| Sat evening | **Checkpoint:** all open PRs merged, Muhos and Agroparc real data on `main`; the three humans open the app and steer |
| Sat 21:30 | **M2:** Muhos real changes → verdicts → visible in the app |
| Sun 11:00 | **M3:** Muhos + Agroparc + Catalonia overview in the app, cards complete |
| Sun 16:00 | **Freeze:** fixes, wording and visuals only |
| Sun 19:00 | Deployed, repo public, submission text and slides / video drafted |
| Sun 22:00 | Submitted (2 h buffer) |

## Risks and fallbacks
- **Mixed NISAR maturity** (beta / provisional / validated) can fake change → one track per site, provisional or later.
- **Muhos timing:** most of the reported ~330 ha was cut before NISAR's first calibrated pass (25 Jun); the first
  11-date run shows 17 ha of clearing. The earlier cutting comes from optical alerts (#44) and from Sentinel-1 once
  the account approval is done. Frozen ground in the 4 Nov pass and snow in March distort the signal; the app says so.
- **Agroparc:** seasonal farmland change drowns the first run (about 1,100 ha of false "structure"); tuning in #36.
  Our sources don't confirm that works have started. If nothing real shows inside the project outline, Tian picks
  another Catalan case from `project-context.md` §7.
- **Records are thin** (permits are PDFs) → the verdict falls back to rules; wording stays "needs review".
- **Cut order if behind:** ground-height layer → "play Muhos" replay → picture swipe → Catalonia overview →
  year-synced photo basemap. **Never cut:** Muhos, Agroparc, the verdict card, the timeline.

## How we check it works
- `python -m pytest`: change core on synthetic stacks; contract validator on the fixture and the real sites.
- Sanity numbers: Muhos clearing vs the reported ~330 ha (same order of magnitude; state the gap) · Agroparc changes
  fall inside the project outline · unchanged forest nearby stays below the threshold.
- Verdict: each rule has a fixture case with the expected label; every reason's source link opens.
- App: `python -m http.server 8000 -d app`, click through each site: the slider reveals changes in date order, the
  card shows pictures + chart + reasons, phone width has no sideways scroll. Every PR shows it in a picture.
- Before the freeze: fresh clone → the app runs from committed data only, with no credentials.

<sub>Written by Claude</sub>
