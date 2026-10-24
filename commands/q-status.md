Quick snapshot of investigation state.

**Active case:** read the case folder name from the first line of `.active-case` (written by `/q-begin` and `/q-new-case`). Every path below is inside `investigations/<case>/`. If `.active-case` is missing or empty, ask the founder which case to use. Never read or write the legacy root folders `canonical/`, `investigations/<case>/`, `memory/`.

Execute the /q-status steps from `.q-system/commands.md`.

1. Read `investigations/<case>/memory/investigation-state.md`
2. Read `investigations/<case>/canonical/scope.md` for hypotheses
3. Output compact summary:
   - Targets: X total, Y fully profiled, Z with gaps
   - Findings: X confirmed, Y assessed, Z speculative
   - Collection: X sources tapped, Y outstanding
   - Hypotheses: status of each
   - Top 3 priorities

Keep it short. No narrative. Bullet points only.

Argument: $ARGUMENTS
