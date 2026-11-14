---
description: Tidy the knowledge base (kb/): fold findings in, dedupe, keep it readable
---
Tidy `kb/` per the AGENTS.md knowledge-base rules. Focus: $ARGUMENTS

1. Read `kb/README.md` and the page list. Scan issues labeled `type:finding` or `kb` updated since the last kb change
   (`git log -1 --format=%cs -- kb/`) and fold reusable facts into the right page.
2. Fix: duplicates (merge), pages >200 lines (split), stale or contradicted content (update or delete), missing index
   lines, unexplained jargon (link `kb/glossary.md` or add a term).
3. Don't restructure for its own sake; small diffs. Open a PR (`kb/` only → self-merge), summarize changes in ≤5 lines.

<!-- Written by Claude -->
