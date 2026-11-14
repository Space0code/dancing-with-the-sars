# AGENTS.md: rules for every agent in this repo

**Project:** NASA Space Apps 2026, "Dancing with the SARs". Interactive app that uses radar (NISAR + Sentinel-1) to
**detect land-surface changes** (forest clearing, new buildings, earthworks, ground motion) and **flag which look
expected vs. need a regulator's review**, in plain language with clear visuals. Pilot: **Catalonia** (+ Google's Finland
clear-cut as test case). Deadline: submission by end of **15 Nov 2026**. What we build: `kb/product.md` · background:
`kb/project-context.md`.

## Team
| Human | GitHub | Role of their Claude |
|---|---|---|
| Tian | `TianK003` | **orchestrator**: plans, splits work into issues, assigns, reviews shared code, keeps #1 current |
| Tomi | `Space0code` | worker |
| Andrea | `molte38` | worker |

Find out whose agent you are: `gh api user -q .login`. Humans are AI engineers (CS / math / EE), **not geologists**:
explain earth-science terms in engineering language (signals, noise, dB, phase, covariance) and link `kb/glossary.md`.

## Coordination = GitHub Issues (the shared memory between machines)
- **Issue = one unit of work, question, finding or decision.** Assignee = who does it. Labels:
  `status:ready|in-progress|blocked|review` · `type:task|question|finding|decision` · `needs-human` · `kb` · `meta`.
- **#1 📍 Team status** (pinned): the orchestrator edits its body in place. Read it at session start.
- **#9 📣 Message board** (pinned): **the one place agents talk to each other.** Task specs live in task issues; every
  assignment, hand-off, "done" and question is a comment on #9 that `@`-mentions the recipient's handle:
  - **Orchestrator assigns** (only Tian's agent hands out work; it runs the whole team):
    `@molte38 #12 on branch 12-x · @Space0code #13 on branch 13-y · I take #14 on 14-z. Tag me when done.`
  - **Worker done:** `@TianK003 #12 done → PR #15 (branch 12-x). Found: … Open: …`, then take your next assignment.
  - **Worker question:** ask **your own human first**; only if they can't answer, post `@TianK003 question on #12: …
    (my recommendation: …)`. The orchestrator answers, or takes it to Tian or the specialist (#7).
  - Read #9 (`gh issue view 9 --comments`) at session start, after each finished task, and whenever blocked or idle.
- **Every agent comment starts with `**[<name>'s agent]**`** (accounts are shared by human + agent; this tells them apart).
- Start of session: `git pull --rebase` · read #1 and #9 · `gh issue list --assignee @me --state open`.
- Claim: `gh issue edit N --add-label status:in-progress --remove-label status:ready` + a comment with your plan (≤5 lines).
- Never wait idly: if blocked, set `status:blocked`, say on what (in the issue + on #9), and take other work.
- Need a human decision / credential / access: add `needs-human`, ask one precise question with options + your
  recommendation, stop that thread.
- **Geoscience specialist:** an expert we met at the event answers questions through the humans (WhatsApp). Agents:
  add questions to issue #7 "Questions for the specialist" (one line each, answerable quickly); never
  put their contact details in the repo.
- Finish: final comment = what was done, where (paths, PR), key findings, open questions. Keep it skimmable.

## Git
- Never commit to `main` directly; never force-push. Branch per issue: `<N>-<short-slug>`. Small PRs, body starts `Closes #N`.
- **Merge policy:** PRs that only touch `kb/`, `explore/`, docs → the author squash-merges
  (`gh pr merge --squash --delete-branch`) after self-review. PRs touching shared code (`src/`, `app/`, deps, `.claude/`,
  this file) → label `status:review`, request review from `TianK003`; the orchestrator merges.
- Pull/rebase before pushing; resolve conflicts yourself, never by discarding others' work.

## Repo layout (create folders only when needed)
| Path | What |
|---|---|
| `kb/` | knowledge base: start at `kb/README.md` |
| `data/` | gitignored except `data/README.md` + small manifests in `data/pilot/` |
| `explore/<topic>/` | exploration scripts/notebooks, one folder per topic/issue |
| `src/` · `app/` | shared library code · the final interactive app (later) |
| `.claude/commands/` | `/work` (worker loop) · `/orchestrate` (Tian) · `/kb` (tidy the knowledge base) |

## Data & secrets
- Never commit raw data or anything >10 MB. NISAR granules are 2–7 GB: **read spatial subsets remotely** when possible.
- Small derived outputs (PNG, small GeoTIFF/JSON) are fine; bigger → GitHub Release asset, linked from kb.
- Credentials only in `~/.netrc` / env vars. The repo will go **public**: no personal data (local paths, emails, machine
  names/specs, tokens, cookies). Check `git diff --staged` before every commit.

## Knowledge base (grow on demand, don't pre-organize)
- `kb/README.md` is the index: one line per page. Add a page only for knowledge someone will reuse; prefer extending a page.
- Each page: H1, one-line purpose + "last updated", then dense content. Verified facts only; mark guesses `(unverified)`.
- Flow: result → issue comment (`type:finding`) → if reusable, fold into kb in the same PR. Decisions → one line in
  `kb/decisions.md`.
- Split a page when it passes ~200 lines; merge or delete stale pages. Every agent keeps kb tidy when it touches it.

## Hygiene
- Delete temp scripts / scratch files before the PR. No dead code, no duplicate notebooks.
- Pin Python deps when adding them. Keep scripts rerunnable (paths relative to repo root, cache in `data/`).

<sub>Written by Claude</sub>
