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
  5 June 2016 → September 2026, 4–6 per summer. Baseline = the 2016 + 2017 summers (10 passes), end state = the 2026
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
Both stacks: ≈ 2.6 GB and ≈ 25 minutes of reads (limit: 10 GB, 60 min). Cache:
`data/stacks/barcelona/{s1,nisar}/<date>.npz` (gitignored; ≈ 15 MB per date): reruns with other settings run
offline with `python -m sarwatch.pipeline barcelona --offline`.

<sub>Written by Claude</sub>
