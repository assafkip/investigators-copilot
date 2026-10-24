Save current investigation state. Run at the end of every session.

**Active case:** read the case folder name from the first line of `.active-case` (written by `/q-begin` and `/q-new-case`). Every path below is inside `investigations/<case>/`. If `.active-case` is missing or empty, ask the founder which case to use. Never read or write the legacy root folders `canonical/`, `investigations/<case>/`, `memory/`.

Execute the /q-checkpoint steps from `.q-system/commands.md`.

1. Update `investigations/<case>/memory/investigation-state.md` with:
   - Session summary
   - What was collected/analyzed
   - Outstanding tasks
   - Next priority
2. Verify target files are consistent with findings and timeline
3. Flag any inconsistencies
4. Confirm save

Argument: $ARGUMENTS
