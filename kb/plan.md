# Build plan

How we get from the brief (`product.md`) to a submitted app by Sun 15 Nov, 22:00. Approved by Tian on 14 Nov 2026,
13:30. Last updated 2026-11-14. Issue numbers for the task IDs below: see #1. The hand-off format: `data-contract.md`.

## Decisions behind the plan
- **Demo sites:** Muhos, Finland (Google's clearing, the test case) · **Agroparc Penedès** (258 ha earthworks) ·
  a coarse **all-Catalonia overview**. Other cases in `project-context.md` §7 are not detailed sites.
- **Tracks:** Tian's agent = radar · Tomi = web app · Andrea = verdict. Tian's agent also orchestrates.
- **Every assignment names the model** to use (Sonnet 5.5 or Opus 5.5).
- **One account type only:** NASA Earthdata Login. No Google Earth Engine.
- **Process in the cloud, store only results.** The team is on mobile data, so radar files never come to laptops:
  radar processing runs in a GitHub Codespace (`.devcontainer/`), and only small results (PNG, GeoJSON, JSON) enter
  the repo. **Decision point Sat ~17:30:** if that route fails, the team moves to a fast-internet space and downloads.
- **Web app:** static site with no build step (HTML + ES modules, MapLibre GL JS and a small chart library from a
  CDN). Hosting: GitHub Pages once the repo is public.

## How it fits together
```
 cloud (Codespace)                              repo: app/data/ (small files)            browser
 NISAR GCOV crops ─┐
 OPERA RTC-S1 crops├─► radar change detection ─► <site>/changes.geojson ──┐
 OPERA DIST-ALERT ─┘   (Tian's agent)            <site>/layers, evidence  ├─► static web app (Tomi)
                                                 <site>/series/*.json     │   map · timeline slider · change card
 public records (protected areas, zoning,                                 │
 land registry, solar list) ─► verdict step ─► adds verdict + reasons ────┘
                               (Andrea)        to each change
```
- **Radar method:** same-track image stack → average neighbouring pixels in linear power (speckle) → per pixel,
  compare the early median with the late median in dB → keep changes above a threshold that persist → date each
  pixel by the first pass where it shows → group into regions ≥0.5 ha → type by rule (cross-pol HV drops = clearing;
  co-pol HH jumps = structure; unstable both ways = earthworks). NISAR covers Jun–Nov 2026; OPERA Sentinel-1
  (30 m, from 2016 at both sites) covers the years before.
- **Catalonia overview:** NASA's OPERA DIST-ALERT-HLS vegetation-loss alerts (a date per pixel, 2023→) give candidates
  region-wide with almost no processing; NISAR crops confirm the ~20 largest. Wording in the app: "an optical alert
  finds it, radar confirms it through clouds".
- **Timeline slider:** every change has a `first_date`; the app shows changes with `first_date ≤ slider`.
- **Ground height change:** no site was picked for it, so it is a stretch item (EGMS overlay) and the first cut.

## Coverage we confirmed (ASF search API, 14 Nov)
| Site | NISAR GCOV | OPERA Sentinel-1 (RTC-S1) |
|---|---|---|
| Muhos (26.044, 64.843) | 4 tracks × 9–12 calibrated dates, 21 Jun → 4 Nov; best: track 157 / frame 35 ascending, 12 dates, ~2 GB each | 2,413 scenes, 2016→ |
| Agroparc (1.85, 41.45) | track 130 / frame 22 ascending: 11 dates, 23 Jun → 2 Nov · track 66 / frame 68 descending: 16 dates from Nov 2025, mixed maturity | 1,552 scenes, 2016→ (earliest 17 Apr 2016) |

## Who owns which files (disjoint, so no merge conflicts)
| Owner | Paths |
|---|---|
| Tian's agent | `pyproject.toml`, `.devcontainer/`, `src/sarwatch/{contract,nisar,s1,change,export}.py`, `explore/`, `app/data/sites.json`, `app/data/<real site>/` except `story.json`, `kb/plan.md`, `kb/data-contract.md` |
| Andrea | `src/sarwatch/context/` (one client per public record source), `src/sarwatch/verdict.py`, `kb/verdict-rules.md`, `app/data/<site>/story.json` |
| Tomi | `app/` except `app/data/` |

Need a contract change? Ask on #9; don't edit `contract.py` or `data-contract.md` yourself.

## Tasks
| ID | Who · model | Goal → output | Size |
|---|---|---|---|
| S0 | Tian's agent | This plan, the contract, the fake fixture site, project setup | done first |
| R1 | Tian's agent | Read one NISAR crop over Muhos from the Codespace; **measure MB and seconds**; `nisar.py`; `kb/data-nisar-gcov.md` | 1.5 h, needs the Earthdata token |
| R2 | Tian's agent (sub-agent) | `change.py`: stack → dB change, first-change date, regions, series; tests on synthetic data | 1.5 h |
| R3 | Tian's agent | `s1.py`: OPERA Sentinel-1 crops as the same kind of stack | 1.5 h |
| R4 | Tian's agent | **Muhos end to end** → `app/data/muhos/` | 2 h |
| R5 | Tian's agent | **Agroparc end to end** → `app/data/agroparc/` | 1.5 h |
| R6 | Tian's agent, or Andrea when free | Catalonia overview → `app/data/catalonia/` | 2–3 h |
| V1 | Andrea · **Opus 5.5** (quirky government services) | Record lookups in `src/sarwatch/context/`: protected areas, land-registry buildings, zoning, solar-plant list | 2–3 h |
| V2 | Andrea · Sonnet 5.5 | `verdict.py`: rules → verdict + reasons + plain sentence; CLI that enriches a `changes.geojson`; `kb/verdict-rules.md` | 2 h |
| V3 | Andrea · Sonnet 5.5 | Finland records + `story.json` for Muhos and Agroparc (sourced, dated events) | 1.5 h |
| V4 | Andrea · Sonnet 5.5 | Fire rule for the overview (NASA FIRMS) so wildfires come out "expected" | 1 h, optional |
| A1 | Tomi · Sonnet 5.5 | App skeleton on the fixture: map, site switcher, verdict colors, timeline slider + play, change card | 2–3 h |
| A2 | Tomi · Sonnet 5.5 | Card evidence: before/after pictures with swipe, signal chart, reasons with links; picture overlays | 2 h |
| A3 | Tomi · **Opus 5.5** (design and wording judgment) | Photo basemap that follows the slider year, "how to read this" explainer, guided tour | 2–3 h |
| A4 | Tomi · Sonnet 5.5 | Polish, phone-width check, deploy | 1.5 h |
| W1 | Tian's agent drafts, humans finish | Submission pack: summary, data and AI-use disclosure, references, slide / video script | Sun |
| W2 | Tian's agent + Tomi (repo owner) | Public-repo check: personal-data scan, LICENSE, README, make public, Pages on | Sun |

## Human tasks
1. **Tian (blocks R1):** create a NASA Earthdata Login and a user token · `gh auth refresh -h github.com -s codespace` ·
   `gh secret set EARTHDATA_TOKEN --user --repos Space0code/dancing-with-the-sars` (typed by Tian, never shown to an agent).
2. **Tomi, Andrea:** `git pull`, reply `ready` on #9, use the model named in your assignment.
3. **Anyone:** send the questions in #7 to the specialist · confirm the **local pitch time and submission checklist**
   (if pitches are Sunday afternoon, the freeze moves earlier) · pick an app name.

## Milestones (local time)
| When | What must be true |
|---|---|
| Sat 14:30 | S0 merged, issues created, assignments on #9 |
| Sat 17:30 | **M1:** a NISAR crop read works and is measured · record lookups answer for Agroparc · the app shows the fixture with a working slider. **Stay or move?** |
| Sat 21:30 | **M2:** Muhos real changes → verdicts → visible in the app |
| Sun 11:00 | **M3:** Muhos + Agroparc + Catalonia overview in the app, cards complete |
| Sun 16:00 | **Freeze:** fixes, wording and visuals only |
| Sun 19:00 | Deployed, repo public, submission text and slides / video drafted |
| Sun 22:00 | Submitted (2 h buffer) |

## Risks and fallbacks
- **Codespace or remote crop fails** → move to the fast-internet space and download ~25 granules (≈45 GB).
- **Mixed NISAR maturity** (beta / provisional / validated) can fake change → one track per site, provisional or later.
- **Muhos timing:** cutting ran Mar–Aug, calibrated NISAR starts 21 Jun → NISAR shows the part cut *after* the May
  warning; Sentinel-1 covers Mar–Jun (snow in March distorts the signal, and the app says so).
- **Records are thin** (permits are PDFs) → the verdict falls back to rules; wording stays "needs review".
- **Cut order if behind:** ground-height layer → picture swipe → Catalonia overview → year-synced photo basemap.
  **Never cut:** Muhos, Agroparc, the verdict card, the timeline.

## How we check it works
- `python -m pytest`: change core on synthetic stacks; contract validator on the fixture and the real sites.
- Sanity numbers: Muhos clearing vs the reported ~330 ha (same order of magnitude; state the gap) · Agroparc changes
  fall inside the project outline · unchanged forest nearby stays below the threshold.
- Verdict: each rule has a fixture case with the expected label; every reason's source link opens.
- App: `python -m http.server` in `app/`, click through each site: the slider reveals changes in date order, the card
  shows pictures + chart + reasons, phone width has no sideways scroll.
- Before the freeze: fresh clone → the app runs from committed data only, with no credentials.

<sub>Written by Claude</sub>
