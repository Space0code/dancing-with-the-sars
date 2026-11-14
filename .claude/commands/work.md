---
description: Worker loop: pick up your next GitHub issue, do it, report back
---
You are a **worker agent** in this repo. Follow AGENTS.md. Optional focus from the user: $ARGUMENTS

1. `git switch main && git pull --rebase`. Who am I: `gh api user -q .login` (map to a name via AGENTS.md).
2. Read #1 (`gh issue view 1`) and the **message board #9** (`gh issue view 9 --comments`): find the latest comments
   that `@`-mention me (assignments, answers). List my work: `gh issue list --assignee @me --state open`.
3. Pick: what the orchestrator assigned me on #9 (an `in-progress` issue of mine first, else the oldest `status:ready`).
   Nothing assigned → tell the user and post on #9 `@TianK003 free for work`; don't self-assign without the user's OK.
4. Claim it (labels + plan comment starting `**[<name>'s agent]**`). Use the branch named on #9 (`<N>-<slug>`).
5. Do the work; commit + push often (CLAUDE.md). Use sub-agents for noisy work. Questions: ask the user (my human)
   first; if they can't answer, post `@TianK003 question on #N: … (my recommendation: …)` on #9 and keep working on
   whatever isn't blocked.
6. Finish: tidy (delete scratch), update kb if something is reusable, PR with `Closes #N` and a picture of what it
   built. Shared code: spawn a fresh Opus reviewer sub-agent, let it post its review on the PR, fix the findings, then
   squash-merge yourself (AGENTS.md merge policy). Final summary comment on the issue, then on #9:
   `@TianK003 #N merged (PR #M). Found: … Open: …`.
7. Report to the user in ≤8 lines: done, where, what's next. Waiting for work? Suggest `/loop 10m /work`.

<!-- Written by Claude -->
