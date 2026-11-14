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

<sub>Written by Claude</sub>
