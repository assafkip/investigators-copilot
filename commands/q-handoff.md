Generate a session handoff note for continuity across Claude Code sessions.

Save to the active case's `memory/last-handoff.md`, i.e. `investigations/<case>/memory/last-handoff.md`, where `<case>` is the first line of `.active-case` (ask the founder if it is missing or empty).

## Handoff Contents

1. **Session summary:** 2-3 sentences on what happened
2. **In-progress work:** Anything started but not finished (with file paths)
3. **Decisions made:** Key analytical judgments or approach changes
4. **Files modified:** List of all investigation files changed this session
5. **Blocked items:** What we're waiting on (client response, API keys, etc.)
6. **Suggested next action:** The single most impactful thing to do next session, with Energy tag + Time Est

## Triggers

Run this when:
- The founder says "done", "stopping", "wrapping up"
- Context is running low
- After `/q-end` or `/q-checkpoint`
- Before context compaction
