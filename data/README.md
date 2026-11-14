# data/

Local cache, **gitignored** (NISAR granules are 2–7 GB each). Only this file and `pilot/` are versioned.

| Path | What |
|---|---|
| `pilot/asf-search-nisar-gcov-2026-11-14.csv` | **Legacy** (pre-pivot, likely Abilene TX; unverified). ASF export of 35 NISAR GCOV granules, 2 tracks, Oct 2025 – Oct 2026. Not used for the Catalonia pilot; delete once a Catalonia manifest exists. |

**Access:** downloads need a free NASA Earthdata Login in `~/.netrc` (see onboarding issue #2). Searching ASF needs no login.
Prefer reading spatial subsets remotely over full downloads. Put downloaded/derived files under `data/<topic>/`.

<sub>Written by Claude</sub>
