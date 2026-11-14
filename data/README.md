# data/

Local cache, **gitignored** (NISAR granules are 2–7 GB each). Only this file and `pilot/` are versioned.

| Path | What |
|---|---|
| `pilot/asf-search-nisar-gcov-2026-11-14.csv` | ASF Vertex search export: 35 NISAR L2 GCOV granules (2 tracks, Oct 2025 – Oct 2026, ~218 GB total). Columns include granule name, track (path/frame), direction, start time, size, download URL. |

**Access:** downloads need a free NASA Earthdata Login in `~/.netrc` (see onboarding issue #2). Searching ASF needs no login.
Prefer reading spatial subsets remotely over full downloads. Put downloaded/derived files under `data/<topic>/`.

<sub>Written by Claude</sub>
