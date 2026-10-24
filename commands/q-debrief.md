Extract structured findings from a conversation, interview, document, or source.

**Active case:** read the case folder name from the first line of `.active-case` (written by `/q-begin` and `/q-new-case`). Every path below is inside `investigations/<case>/`. If `.active-case` is missing or empty, ask the founder which case to use. Never read or write the legacy root folders `canonical/`, `investigations/<case>/`, `memory/`.

Execute the /q-debrief steps from `.q-system/commands.md`.

1. Ask founder to describe or paste the source material
2. Extract:
   - New targets or entities mentioned
   - Facts (with reliability assessment using A-F scale from `.q-system/preflight.md`)
   - Timeline events (with dates)
   - Relationships between entities
   - Contradictions with existing findings
   - New collection leads
3. Route to appropriate investigation files in `investigations/<case>/investigation/`
4. Cross-reference against existing data
5. Update `investigations/<case>/memory/investigation-state.md`

Argument: $ARGUMENTS (optional: paste source material directly)
