# Site: Barcelona and its region

Which radar data the Barcelona site reads, what it costs, and how a window larger than one Sentinel-1 burst becomes
one stack. Last updated 2026-11-15 (live ASF searches and timed reads; recent-first selection; issue #44). Terms: [glossary.md](glossary.md).

## Window
**lon 1.85 to 2.45, lat 41.25 to 41.60** (about 50 × 39 km, 1,950 km²): the city, the Llobregat delta (airport, port),
the Vallès (Sabadell, Terrassa, Cerdanyola) and the start of the Maresme (Montgat to about Vilassar de Mar). Not all of Catalonia.
Kept as proposed: one NISAR frame and one Sentinel-1 track cover all of it (below), so the data layout gives no reason
to move it. Its south-west corner overlaps the Agroparc window (1.79-1.91, 41.41-41.49) on the same two stacks.

## Sentinel-1 (OPERA RTC-S1): track 132 ascending, three bursts as one mosaic
| Track · direction | Bursts over the window (share of it) | Dates with every burst, 2016 → | Jun–Sep dates per year |
|---|---|---|---|
| **132 ascending (used)** | IW2 281621 (36 %), 281622 (49 %), 281623 (15 %): 99.99 % together | 465 | 8–22 |
| 37 descending | IW3 078153–078156 (3 / 46 / 47 / 4 %) | 520 | 9–21 |
| 110 descending | IW1 234951–234954 (9 / 49 / 42 / 1 %) | 518 | 10–21 |

- Why 132: it is Agroparc's track (burst 281622 is Agroparc's burst), so the two sites see the overlap with the same
  geometry; it is ascending like the NISAR stack; it needs three bursts, not four; and all three lie in one sub-swath
  (IW2, one incidence-angle band). Every date since 2016 has all three bursts (no partial passes in Jun–Sep).
- **Mosaic, not tiles.** Every OPERA burst of one UTM zone sits on one 30 m lattice (coordinates are multiples of
  30 m; the reader checks it), and the bursts of one date come from one pass. So one window grid (EPSG:32631,
  1,313 × 1,685 px) holds all three without resampling; where neighbouring bursts overlap the mosaic is
  the mean of their valid pixels in linear power. One stack means one detection run, no seams where a change crosses
  a tile border, and the same code path as a single-burst site. Tiles per burst would need a join step and still cut
  regions at tile edges. Code: `s1.pick_bursts` (one track, greedy burst choice, only dates with every burst) and
  `s1.read_mosaic`; site switch `S1Settings(mosaic=True, track=132)`.
- Dates: Jun–Sep of every year, at least 20 days apart (`months=(6, 7, 8, 9)`, `min_gap_days=20`): **57 dates**,
  5 June 2016 → September 2026, 4–6 per summer. Baseline = the 2016 summer only (5 passes), end state = the 2026
  summer (6 passes), the Agroparc comparison (summer against summer, so the farmland's yearly cycle cancels out).
- **Measured cost:** 28.6 MB and 10–16 s per date (VV + VH + mask of three bursts; NaN 0.1 %: layover / shadow and
  one corner). 57 dates ≈ 1.6 GB, ≈ 12 min.

## NISAR GCOV: track 130 / frame 22 ascending
- The same stack as Agroparc. Its partial frames cover **100 %** of the window on all **11 dates**, 23 Jun → 2 Nov 2026
  (10 PROVISIONAL + 2 Nov VALIDATED). Other footprints: 66 / 67 and 66 / 68 descending cover 46–89 %, 29 / 22
  ascending 19–32 % (29 / 23 covers it but has only 2 dates).
- Grid EPSG:32631, 20 m, 1,969 × 2,527 px (under the reader's 25 M pixel cap).
- **Measured cost:** 82–90 MB and about 60 s per date. 11 dates ≈ 0.95 GB, ≈ 11 min.

## Budget
Used: Sentinel-1 57 dates = 1.63 GB in 706 s of reads; NISAR 11 dates = 0.90 GB in 681 s (the two ran in parallel,
about 15 min wall clock). Total **2.53 GB, 23 min of reads** (limit: 10 GB, 60 min). Cache:
`data/stacks/barcelona/{s1,nisar}/<date>.npz` (gitignored; ≈ 15 MB per date): reruns with other settings run
offline with `python -m sarwatch.pipeline barcelona --offline`.

## Detection settings (`pipeline.SITES["barcelona"]`) and why
Starting point: Agroparc's (summer against summer, `normalize`, `hold`, `persist=99`, 3 dB, 1 ha). Changes, each
found by looking at quick-looks (`explore/barcelona/look.py`):
- **Sea:** wind lifts the sea's VV to −11 dB, a land level, so the co-pol water mask fails; its VH stays at −30 dB.
  Water = baseline cross-pol median below −24 dB (Sentinel-1) / −23 dB (NISAR HV), plus 2–3 pixels of shore
  (`water_pol`). Before the mask, NISAR called the windy sea "structure" (HH −20 → −16 dB). After it: no change on water.
- **Baseline = the 2016 summer only** (5 passes, `n_early=5`), so changes of 2017 are dated (with 2016 + 2017 as
  baseline, 87 regions, 303 ha, were dated inside it and could not be dated). End state = the 6 passes of summer
  2026, all of which must show the change.
- **Busy surfaces** (`noise_k=2`, new): a pixel counts only if its change is at least twice its own pass-to-pass
  spread in the two windows. Sentinel-1 VV spread over the 2016 passes: median 0.5 dB, 99th percentile 2.1 dB; quay
  edges where ships berth are the brightest spots of the spread map. Removes 42 of 742 Sentinel-1 regions: after `hold` it adds little, but it is cheap insurance.
- **NISAR keeps clearing, structure, earthworks only** (`keep_types`): its 4.5-month record compares June with
  October, and on the Llobregat delta and Maresme fields the "other" class was whole fields whose HV rose 5–7 dB (crops
  growing). 137 of 203 regions. `structure_db=6` turns weaker HH rises into "other" first. A year-to-year "churn" mask
  from the Sentinel-1 decade was tried and rejected: construction sites churn as much as fields (both ~1–1.5 dB).
- **150 changes, recent first** (`max_changes=150`, `recent_from=2024-01-01`, `max_recent=120`, `recent_low_conf_ha=2.0`;
  generic `Site` settings, `pipeline.top_changes`). After `exclude_points`: (1) a change first seen from 2024 on that a
  sensor watched start (not a late start) is "recent"; a **low-confidence recent change under 2 ha is dropped** (its
  signal is 3.8-5 dB, which on small areas is mostly crops); (2) the largest recent ones are kept, up to 120 (a
  low-confidence one counted at half its area); (3) the places left up to 150 go to the largest older changes.
  A NISAR change "already under way" on 23 Jun 2026 is dated to that pass, says the record cannot date it, and is **not**
  recent (it competes with the older ones by size). Without `recent_from` (Muhos, Agroparc, fixture) nothing changes.
  Site pictures above 2 MB get a 256-colour palette (`layer_bytes`).

## Measured before the cut (15 Nov 2026, offline, no `max_changes`)
761 merged changes (696 Sentinel-1 + 65 NISAR regions). First year: 2016 19, 2017 150, 2018 105, 2019 74, 2020 77,
2021 62, 2022 54, 2023 49, 2024 61, 2025 34, 2026 76. **171 from 2024 on** (8 of them NISAR late starts, not recent),
163 recent: 1-2 ha 144 (Sentinel-1 97, NISAR 47), 2-5 ha 27 (Sentinel-1 9, NISAR 18), over 5 ha none. The old
"100 largest" kept only 7 of them (2024: 3, 2025: 1, 2026: 3).
**Real or not?** Judged by eye from the card pictures (24 random recent ones, no ground truth, no optical check): about
half show a compact new bright spot or dark patch that fits a building, a clearing or earthworks; the rest sit in
speckled field mosaics (Vallès, Maresme, Llobregat delta) and look like crops or machinery. The smallest (1.0-1.1 ha,
72 of 163) are the least convincing. Treat the recent list as "places to look at", not as confirmed works.

## Result with recent first (15 Nov 2026)
150 changes: first year 2016 7, 2017 11, 2018 5, 2019 2, 2020 2, 2021 1, 2023 2, 2024 49, 2025 24, 2026 47 (120 recent,
30 older; 536 ha, 198 ha of it recent). From 2024 on: structure 74, clearing 28, earthworks 9, other 9; 81 Sentinel-1,
39 NISAR; 1-2 ha 97, 2-5 ha 23. Labels, all 150: expected 92, needs review 43, high concern 15; from 2024 on:
expected 69, review 38, high concern 13 (the verdict rules of #46 and #132; Catalan lookups, none failed). Picture:
`explore/barcelona/overview-recent.jpg`. Zoning (MUC) counts of the first run are not redone.

## Still wrong
- About half of the recent small changes are probably fields; no filter on the radar alone separated them (pass-to-pass
  churn does not either, see above). A land-cover or optical check is the next step.
- 1-2 ha is about 12-22 Sentinel-1 pixels: outlines are blocky and the area is +-30 %.
- Ships and port yards: one berth is excluded by hand (`exclude_points`); others may remain in the port and the airport.
- The place name (municipality) is not in the data; cards show coordinates only.
- The 120 cap cuts the smallest recent ones (about 1.0-1.1 ha, 22 of the 142 that pass the filter).

<sub>Written by Claude</sub>
