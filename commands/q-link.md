Map and document the relationship between two investigation targets.

**Active case:** read the case folder name from the first line of `.active-case` (written by `/q-begin` and `/q-new-case`). Every path below is inside `investigations/<case>/`. If `.active-case` is missing or empty, ask the founder which case to use. Never read or write the legacy root folders `canonical/`, `investigations/<case>/`, `memory/`.

Execute the /q-link steps from `.q-system/commands.md`.

1. Read both target profiles from `investigations/<case>/investigation/targets/`
2. Search evidence for shared: organizations, events, digital infrastructure, communication patterns, third-party connections
3. Classify relationship: direct / indirect / inferred / unknown
4. Assess strength: strong / moderate / weak / speculative
5. Document in both target files + create finding in `investigations/<case>/investigation/findings/`
6. Update `investigations/<case>/investigation/timelines/master-timeline.md` if relationship has temporal dimension

Argument: $ARGUMENTS (required: two target names, e.g. "John Smith" "Jane Doe")
