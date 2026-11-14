# Product brief: what we build

The agreed idea (team brainstorm, 14 Nov 2026). Last updated 2026-11-14. The planner turns this into issues; decisions
log: `decisions.md` · data: `data-sources.md` · physics: `sar-primer.md`. Items marked *proposal* are not decided yet.

## One line
A web app that watches a region with radar satellites, finds where the land changed (trees cut, buildings up, earth
moved, ground sinking) and tells a regulator in plain language **which changes look expected and which need a look**,
with the evidence.

## Why
- **The Finland case (verified).** From Mar to Aug 2026 Google's Finnish subsidiary cleared ~330 ha of forest at Muhos
  and just under 200 ha at Kajaani-Otanmäki for planned AI datacenters, **before the mandatory environmental impact
  assessment was finished**. It kept cutting after being told in May that an assessment was required. 6 Oct: the
  permit regulator ordered a stop. 29 Oct: police opened a preliminary investigation into suspected environmental damage,
  including drainage failures. That's months of large physical change, visible from orbit, before anyone stepped in.
  Details and coordinates: `project-context.md` §7.
- **Regulators can't inspect everything.** Changes that match no plan or permit go unnoticed until the damage is done.
- **Radar sees through clouds and works at night**, so monitoring doesn't stall in bad weather or in winter.
  Over Catalonia NISAR gives each point a new look **roughly every 5–6 days**, and adding Sentinel-1 makes it more
  frequent. Say "every few days, whatever the weather", **not "daily"**.

## Who it's for
Regulators and decision makers: regional environment and planning departments, municipal planners, rural or forest
agents. They are **not radar experts**. Every screen explains the technical data in plain language, with visuals.

## What the user sees
```
┌──────────────────────────────────────────────┬──────────────────────────────┐
│  Map of Catalonia (basemap + change markers   │  Change #127 · Forest clearing│
│  colored by verdict)                          │  Where: <municipality> · 12 ha│
│      ● high concern  ● needs review  ● expected│  When: between 3 and 15 Sep   │
│                                               │  Verdict: NEEDS REVIEW        │
│                                               │  Why: non-buildable land; no  │
│                                               │  building or permit on record │
│                                               │  Evidence: [before][after]    │
│                                               │  radar + photo, signal chart  │
│                                               │  "Radar saw the tree signal   │
│                                               │   drop 6 dB, like cut forest" │
├──────────────────────────────────────────────┴──────────────────────────────┤
│  Timeline  2016 ──────────────●───────── Nov 2026   [▶ play]  (changes pile up) │
└──────────────────────────────────────────────────────────────────────────────┘
```
1. **Overview map** of Catalonia with detected changes, colored by verdict.
2. **Timeline slider** (requested): drag or play to watch changes **pile up over weeks, months and years**, e.g. a
   town spreading outward. *Proposal:* compute one "date first changed" map per pixel; the slider shows every pixel
   whose date ≤ the slider. This is cheap to precompute and instant to scrub.
3. **Change card** on click: what changed, where, when, how big, the **verdict + reason**, before/after evidence
   (radar and photo), and a one-sentence plain-language explanation of the signal.
4. **2–3 Catalonia hotspots** analyzed in detail, plus the **Finland test case**: would the app have flagged Google's
   clearing as it happened?

## Change types (all four agreed)
| Type | Radar signal (`sar-primer.md` §8) | Data that confirms or explains it |
|---|---|---|
| Forest clearing | cross-pol (HV / VH) power drops: no more canopy volume; strongest at L-band | OPERA DIST-ALERT-HLS, Hansen, HRL tree cover, GEDI height |
| New buildings / structures | co-pol (HH) brightens from wall–ground double-bounce, then stays stable | Cadastre buildings (+ construction date), ICGC orthophoto |
| Earthworks / flattening (grading, quarries, landfills) | coherence between passes collapses; backscatter changes | ICGC land cover, LiDAR / DEM before |
| Ground height change (sinking / rising) | InSAR displacement | **EGMS** (ready-made, ends 2024); NISAR GUNW optional |

## Verdict: how a change gets its label (agreed approach, rules are a *proposal*)
Radar detects the change. Then we **query public government data**, and where none exists we **fall back to simple
rules**. Labels: **Expected · Needs review · High concern**. The app **never says "illegal"**; it shows a reason.
- **High concern** (*proposal*): inside a protected area (PEIN / Natura 2000); or large clearing / earthworks on
  non-buildable land with no matching record.
- **Needs review** (*proposal*): change on non-buildable land; or a large change with no matching record (no cadastre
  building, no solar-plant entry, no planned development sector).
- **Expected** (*proposal*): inside urban land or a planned development sector with a matching record. Fire scars
  (FIRMS / burned area) and seasonal farming are labeled "natural / routine", not construction.
- Public layers that can be queried: cadastre WFS, PEIN / Natura 2000 REST, zoning (MUC), solar-plant open data.
  Permits and environmental-assessment files are mostly PDFs or not public. See `data-sources.md` §3.

## Data: keep it small
Just enough for the motivation and the demo. NASA data is required (NISAR at minimum); Copernicus, Google Earth Engine,
Catalan open data are allowed. *Proposal:* NISAR GCOV subsets for the hotspots and Finland; Sentinel-1 (OPERA RTC-S1
via Earth Engine) for the multi-year timeline and the overview; public layers queried per change. No full-granule
downloads unless subsetting fails. Precompute everything the demo shows.

## Non-goals
- Ships and maritime: an afterthought at most, not in the product.
- Deciding legality or enforcing anything; training a "legality" model.
- Processing all of Catalonia at full resolution; a live, real-time ingest pipeline.

## Anti-goals (a failure even if it technically works)
- Pointing at a named company or person as wrongdoing on weak evidence (false positives in a public app).
- Radar jargon on screen that a regulator can't read.
- Overclaiming: "daily", "illegal", or change we can't tell apart from noise, rain or harvest.
- A demo that depends on live multi-GB downloads.

## Constraints
- Submission by end of 15 Nov 2026; 3 people.
- The repo goes public, so no personal data. Files >10 MB stay out of git.
- NISAR calibrated data starts **Jun 2026** (beta back to Oct 2025). The multi-year history must come from
  Sentinel-1 / optical.

## Left to the planner
Tech stack (web map + where processing runs) · which 2–3 hotspots (research pick in `project-context.md` §7: Agroparc Penedès, Alcarràs solar, Gavarres fire) · rule
thresholds · pitch format (video / slides) · questions for the geoscience specialist (see AGENTS.md).

<sub>Written by Claude</sub>
