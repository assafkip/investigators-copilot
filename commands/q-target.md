Create or update a target profile for an investigation target.

**Active case:** read the case folder name from the first line of `.active-case` (written by `/q-begin` and `/q-new-case`). Every path below is inside `investigations/<case>/`. If `.active-case` is missing or empty, ask the founder which case to use. Never read or write the legacy root folders `canonical/`, `investigations/<case>/`, `memory/`.

Execute the /q-target steps from `.q-system/commands.md`.

1. Create/update `investigations/<case>/investigation/targets/[name].md` using the template from `investigations/<case>/investigation/targets/_TEMPLATE.md`
2. Populate: identity, digital footprint, connections, timeline, collection status, assessment
3. Cross-reference against other target files for connections
4. Update `investigations/<case>/investigation/timelines/master-timeline.md` if new events found
5. Flag collection gaps
6. Update `investigations/<case>/memory/investigation-state.md`

Argument: $ARGUMENTS (required: target name)
