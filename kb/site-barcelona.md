# Site: Barcelona and its region

Which radar data the Barcelona site reads, what it costs, and how a window larger than one Sentinel-1 burst becomes
one stack. Last updated 2026-11-14 (live ASF searches and timed reads; issue #44). Terms: [glossary.md](glossary.md).

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
- **100 changes** (`max_changes`, after `exclude_points`): the largest merged changes, a low-confidence one counted at half its area.
  Site pictures above 2 MB get a 256-colour palette (`layer_bytes`): the folder is 6.6 MB.

## First result (14 Nov 2026)
700 Sentinel-1 + 66 NISAR regions → 762 merged changes → the 100 largest: structure 75 = 515 ha, earthworks 14 =
90 ha, clearing 9 = 47 ha, other 2 = 14 ha (666 ha). 97 from Sentinel-1, 3 from NISAR (2026). 10 Sentinel-1 and 2 NISAR
changes are late starts (already under way when the sensor began watching): their date is that sensor's first pass and
the card says the record cannot date them. One change, a moored ship at a port berth that NISAR read as earthworks, is
left out by `exclude_points`. Zoning (MUC) counts from the first run (68 urban, 23 developable, 9 non-buildable) are
not redone. Pictures and the list of
what is still wrong: PR #110.

<sub>Written by Claude</sub>
