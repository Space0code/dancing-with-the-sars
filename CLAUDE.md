@AGENTS.md

## Claude-only notes
- Worker session: run `/work`. Tian's orchestrator session: run `/orchestrate`. Tidy knowledge base: `/kb`.
- **Commit small and often, push after every commit** to your issue branch (`git push -u origin <N>-<slug>` once, then
  `git push`). Each working step = one commit, so teammates see progress and nothing is lost on a crash. Never `main`.
- Use sub-agents for noisy work (big file inspection, log/grep sweeps); keep only conclusions in the main context.
- Orchestrator: write issues self-contained (goal, context links, acceptance criteria, output paths, size estimate) so a
  cheaper model can do them without the chat history. Say which model/effort fits if it matters.

<!-- Written by Claude -->
