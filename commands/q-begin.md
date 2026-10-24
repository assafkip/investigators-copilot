Start a new investigation session. Read all state files to load context before doing anything.

## Steps

1. Identify the active case folder in `investigations/`
   - If the founder named a case, use it
   - Else read the first line of `.active-case` and confirm it with the founder
   - If `.active-case` is missing or empty: if only one case exists, use it; otherwise ask the founder
   - Write the chosen folder name (e.g. `case-001-example`) as the only line of `.active-case`, so every other `/q-*` command and script (`next-ev-id.sh`, `capture-evidence.sh`, `extract-intake.py`) resolves the same case
2. Read these files in parallel from the active case:
   - `canonical/scope.md`
   - `canonical/collection-plan.md`
   - `memory/investigation-state.md`
   - `memory/last-handoff.md` (if exists)
3. Read `.q-system/preflight.md`
4. Output a brief status:
   - Case name and primary question
   - Where we left off (from investigation-state.md)
   - Handoff notes (from last-handoff.md)
   - Top 3 priorities
   - Any blockers or outstanding client responses

Do NOT start any collection or analysis until the founder confirms direction.
