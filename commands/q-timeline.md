Build or update the chronological timeline of investigation events.

**Active case:** read the case folder name from the first line of `.active-case` (written by `/q-begin` and `/q-new-case`). Every path below is inside `investigations/<case>/`. If `.active-case` is missing or empty, ask the founder which case to use. Never read or write the legacy root folders `canonical/`, `investigations/<case>/`, `memory/`.

Execute the /q-timeline steps from `.q-system/commands.md`.

1. Read all target profiles in `investigations/<case>/investigation/targets/` and findings in `investigations/<case>/investigation/findings/`
2. Extract dated events
3. Build/update `investigations/<case>/investigation/timelines/master-timeline.md`
4. Identify: activity clusters, gaps, temporal correlations between targets, sequence patterns
5. Present timeline to founder
6. Flag periods that need more collection

Argument: $ARGUMENTS (optional: date range or target to focus on)
