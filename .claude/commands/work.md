---
description: Worker loop: pick up your next GitHub issue, do it, report back
---
You are a **worker agent** in this repo. Follow AGENTS.md. Optional focus from the user: $ARGUMENTS

1. `git switch main && git pull --rebase`. Who am I: `gh api user -q .login` (map to a name via AGENTS.md).
2. Read #1 (`gh issue view 1`). List my work: `gh issue list --assignee @me --state open`.
   Also check mentions: `gh search issues --repo Space0code/dancing-with-the-sars --mentions @me --state open`.
3. Pick: an `in-progress` issue of mine first, else the oldest `status:ready`. Answer pending `type:question`s to me
   first (quick). Nothing assigned → tell the user and suggest unassigned `status:ready` issues; don't self-assign
   without the user's OK.
4. Claim it (labels + plan comment starting `**[<name>'s agent]**`). Branch `<N>-<slug>`.
5. Do the work. Post intermediate findings as comments if they're useful to others now. Use sub-agents for noisy work.
6. Finish: tidy (delete scratch), update kb if something is reusable, PR with `Closes #N`, merge per AGENTS.md policy,
   final summary comment on the issue. If blocked or a human must decide → label + one precise question.
7. Report to the user in ≤8 lines: done, where, what's next in the queue.

<!-- Written by Claude -->
