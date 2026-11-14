@AGENTS.md

## Claude-only notes
- Worker session: run `/work`. Tian's orchestrator session: run `/orchestrate`. Tidy knowledge base: `/kb`.
- Use sub-agents for noisy work (big file inspection, log/grep sweeps); keep only conclusions in the main context.
- Orchestrator: write issues self-contained (goal, context links, acceptance criteria, output paths, size estimate) so a
  cheaper model can do them without the chat history. Say which model/effort fits if it matters.

<!-- Written by Claude -->
