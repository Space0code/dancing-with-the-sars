# Dancing with the SARs

NASA Space Apps Challenge 2026 (Barcelona, 14–15 Nov). Challenge: build an interactive app that uses **NISAR** radar
data to track surface change on Earth. Our angle: the footprint of the recent **datacenter buildout**
(land conversion, construction, surrounding infrastructure).

**Team:** Tian (`TianK003`), Tomi (`Space0code`), Andrea (`molte38`).

## How we work
Each of us drives a Claude Code agent. Tian's agent orchestrates; Tomi's and Andrea's agents do the tasks.
They coordinate through **GitHub Issues** (tasks, questions, findings, decisions) and keep the knowledge base in `kb/`.
Rules for agents: [AGENTS.md](AGENTS.md). Current state: the pinned **📍 Team status** issue (#1).

**Start a session:** `cd dancing-with-the-sars && claude`, then `/work` (worker) or `/orchestrate` (Tian).
First time: follow the onboarding issue (#2).

## Where things are
- `kb/`: what we know (start with [kb/README.md](kb/README.md); new to radar? read [kb/sar-primer.md](kb/sar-primer.md))
- `data/`: local data cache (gitignored); see [data/README.md](data/README.md)
- `explore/`: exploration scripts and notebooks (created by the first tasks)

<sub>Written by Claude</sub>
