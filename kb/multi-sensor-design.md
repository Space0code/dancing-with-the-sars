# One change, several sensors: design

How detections from optical alerts, Sentinel-1 and NISAR become **one change per place** with an honest date and confidence. Last updated 2026-11-14 (#60). **Status: proposal**, not implemented; `data-contract.md` and `contract.py` are unchanged. Thresholds are first guesses `(unverified)`, to be tuned on Muhos.

## Terms
- **Source:** one sensor's record over a site (`OPERA DIST-ALERT`, `Sentinel-1 C-band`, `NISAR L-band`). **Kind:** `optical` or `radar`. The two kinds fail for unrelated reasons (clouds vs. snow, frost, wet soil); the two radars share theirs.
- **Detection:** one region from one source (what the exporter writes as a change today), plus a **window** `[not_before, not_after]`: the change happened after the source's last look that showed the old state and by its first look that showed the new one. Radar: `not_after` = the region's `first_date`, `not_before` = that sensor's pass before it. Optical: `not_after` = the alert date, `not_before` = the last cloud-free look before it if the reader has it, else null.
- **Late start:** a radar detection whose `first_date` falls inside the run's baseline passes (the first `n_early` passes). The change was already under way when the record began, so the source proves *that* it changed and gives only "on or before" for *when*: `not_before` = null.

## 1. Merging: when are two detections the same change?
All three conditions, detections from **different** sources only (a source never merges with itself):
| Condition | Rule | Why |
|---|---|---|
| Space | the intersection is ≥ 30 % of **each** polygon (mutual overlap) | 20 m and 30 m grids and different physics give different outlines; a one-sided test would let one large optical area swallow many small radar regions |
| Time | the windows, from `not_before` to `last_date`, each widened by 24 days (two radar revisits), overlap. Unknown `not_before`: 24 days before `not_after`; for a late start: 120 days before the record began | sources pass on different days; a late start may sit months after the real start |
| Type | no condition | optical only knows "vegetation loss"; a building site is a clearing to one sensor and a structure to another |

Changes = connected groups under this relation. The same place changing twice (cleared 2023, built on 2025) fails the time test and stays two changes.
- **Outline:** union of the group's polygons; `area_ha` from the union. Each source keeps its own area in `sources`.
- **Type:** from the detection with the highest own confidence; ties: `structure` > `earthworks` > `clearing` > `other`.
- **Nested detections** (a small radar region inside a much larger optical area, so only one side reaches 30 %): they stay **separate** changes. Each lists the other's source with the **share** of its own area that source covers; a share ≥ 30 % counts as agreement (section 3). So the small one says "lies inside a larger optical alert area", the large one "radar saw 12 % of it" and gains nothing. The app draws small polygons above large ones. Known limit: two cards for one place; the optical exporter should cut its regions by month so sizes are comparable.

## 2. Dating
| Field | Rule |
|---|---|
| `first_date` | earliest `not_after` among the sources that detected it **without** a late start: the first day any source positively saw the change |
| `not_before` (new) | the `not_before` of that same source. Not tightened with another sensor's "still unchanged" pass: sensors differ in sensitivity, so one sensor's silence is not proof of no change |
| `last_date` | latest `last_date` of any detecting source |
| only late-start sources | `first_date` = earliest `not_after`, `not_before` = null |

Wording of "When": `not_before` set → **"between 2 and 20 May 2026"**. Null → **"on or before 20 May 2026"**. Only late starts → **"already under way on 25 Jun 2026, when NISAR began watching; the start date is not known"**. Never a single day unless `not_before` is the day before. A late start is never written as "happened on".

## 3. Confidence
Each detection keeps its own grade (radar: as in `change.py`; optical: provisional alert = low, confirmed alert = medium). Merged grade = best own grade, then:
| Situation | Adjustment | Card adds |
|---|---|---|
| optical + radar agree | +1 step; no risky-season penalty | "two independent kinds of satellite saw it" |
| two radars agree, normal season | +1 step | "both radar satellites saw it" |
| one kind only (one source, or both radars), date in that kind's risky months for the site | −1 step | "seen only by radar while the ground was probably frozen or snow-covered, which can look like a change" |
| one source, normal season | none | "only <source> saw it" + why the others did not (below) |
| a source was watching and did not flag it | **none** | "did not flag it" |

Clamped to low … high. A late-start source counts as agreeing (it shows the change is real). Silence never lowers: clouds, a type the source cannot see, or weak C-band response to cut forest all explain it innocently. Risky months per site and kind `(unverified, ask #7)`: Muhos radar Nov–Apr (snow, frost), Muhos optical Nov–Feb (low sun, snow); Catalonia none by month (crop cycles are handled by the detector tuning, #36).

## 4. Wording on the card
`explain` is built by the exporter from `sources`, in date order; the verdict step appends its reason as today.
| Role of a source | Sentence |
|---|---|
| saw it first, optical | "An optical alert found vegetation loss here between 2 and 20 May 2026." |
| saw it later, radar | "Sentinel-1 radar saw the same change, through clouds, on 26 May." |
| late start | "NISAR began watching on 25 Jun 2026 and shows the change already under way." |
| watching, no detection | "The optical alerts did not flag it." (+ "they only see vegetation loss" for a structure) |
| not watching | "NISAR was not flying yet." / "Optical alerts start in 2023." |

"Confirmed" only with two sources. Never: "verified", "proved", "exact date", or a count of sources as if it were certainty.
```
┌ NEEDS REVIEW ───────────────────────────────┐
│ Forest clearing                              │
│ When        between 2 and 20 May 2026        │
│ Size        14 ha (sources: 11 to 14 ha)     │
│ Confidence  High · two independent kinds of  │
│             satellite saw it                 │
│ Seen by                                      │
│  ● Optical alert   2 – 20 May      first     │
│  ● Sentinel-1      26 May          confirms  │
│  ◐ NISAR           by 25 Jun       already   │
│                                    under way │
│ "An optical alert found vegetation loss …"   │
└──────────────────────────────────────────────┘
```

## 5. Timeline: who was watching?
- A **coverage strip** under the slider: one thin bar per source from its `start` to its `end`, labelled, on the same time axis. Before the first bar the track is greyed: "no satellite record here before 2016".
- A line that follows the slider: **"Watching on 12 Mar 2021: Sentinel-1 radar. Optical alerts start in 2023, NISAR in June 2026."**
- A small marker where each bar starts ("NISAR begins"), so the batch of "already under way" changes appearing on 25 Jun 2026 reads as the sensor switching on, not as a burst of activity. The site's `time_range` starts at its earliest source.

## 6. Contract proposal (additive, all optional; old data and the old app keep working)
- **Change** `sources`: `[{sensor, kind, role, first_date, last_date, not_before, confidence, area_ha, share, note}]`. `role`: `detected` · `late_start` · `not_seen` · `not_watching`. Dates and `confidence` are null for the last two; `share` = fraction of the change's area this source covers; `note` = the plain sentence from section 4.
- **Change** `not_before`: `YYYY-MM-DD` or null (≤ `first_date`). Missing = today's behaviour.
- **Change** `sensor` stays: the source that set `first_date`. `signal` and the evidence pictures come from the best radar detection (NISAR before Sentinel-1); optical-only changes have `signal: null`.
- **Site** (in `sites.json`) `sources`: `[{sensor, kind, start, end, revisit_days, sees, risky_months}]`; `sees` = change types the source can detect, `risky_months` = `[11, 12, 1, …]`.
- No `sources` on a change = a single-source change, shown as today.

## 7. Worked examples (dates are illustrations of the rules, not measurements)
**Muhos clear-cut, spring 2026.** Optical: last clear look 2 May, alert 20 May, confirmed (medium), 14 ha. Sentinel-1: unchanged 14 May, VH −3 dB on 26 May (medium), 11 ha. NISAR: record starts 25 Jun, HV already falling within its first three passes (late start, medium), 13 ha. All pairs overlap mutually and in time → one change, outline = union. `first_date` 20 May (optical saw it first), `not_before` 2 May: "between 2 and 20 May 2026" (the Sentinel-1 pass of 14 May is not used to tighten it). Confidence medium + 1 = **high**: optical and radar agree. Without the optical alert and Sentinel-1 the same place would read "already under way on 25 Jun 2026, when NISAR began watching", never "cleared on 25 Jun".

**Warehouse in Catalonia, 2021.** Sentinel-1: VV +4 dB between the passes of 3 and 15 Mar 2021, still growing until 20 Jun, 6 ha, own grade medium. Optical alerts: `not_watching` (start 2023; also blind to structures). NISAR: `not_watching` (starts June 2026). One source, normal season → `structure`, "between 3 and 15 Mar 2021", confidence **medium**, "Only Sentinel-1 radar was watching in 2021". A single source may still reach high on its own grade: a large step that holds for years is its own evidence.

## 8. Work split (each ≤ 1 h; exporter tasks in order, app tasks in parallel against the fixture)
| # | Task | Model |
|---|---|---|
| E1 | `src/sarwatch/merge.py`: pure function, detections in → merged changes out (sections 1–3, shapely, no files); tests = the two examples above plus the nested and the twice-changed case | Opus |
| E2 | `export.write_site` calls it: runs and optical alerts (#44) become detections with windows and late-start flags; writes `sources`, `not_before`, the `explain` sentences; evidence from the best radar run | Sonnet |
| E3 | `sites.json` `sources` per site; validator accepts the optional fields; fixture gets one three-source and one single-source change | Sonnet |
| A1 | Card: "When" wording, "Seen by" list, confidence note; falls back to `sensor` when `sources` is missing | Sonnet |
| A2 | Timeline: coverage strip, "watching on this date" line, start markers, greyed track | Sonnet |
| A3 | Small polygons drawn above large ones; inbox filter "seen by two or more sources"; chart marks each source's first sighting | Sonnet |
Cut order if time runs out: A3, then E3's risky months, then A2's markers. E1 + E2 + A1 are the minimum that removes duplicate changes.

## Open: decisions to confirm (orchestrator)
1. **Date = first positive sighting, window from that one source** (conservative), not the tightest window across sources.
2. **Mutual 30 % overlap**: nested detections stay separate changes that cite each other, rather than one large merged outline.
3. **The contract additions** in section 6, including `contract.py` accepting them (E3), and that silence from a watching source never lowers confidence.

<sub>Written by Claude</sub>
