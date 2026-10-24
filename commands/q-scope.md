Define or update the investigation scope, hypotheses, and collection requirements.

**Active case:** read the case folder name from the first line of `.active-case` (written by `/q-begin` and `/q-new-case`). Every path below is inside `investigations/<case>/`. If `.active-case` is missing or empty, ask the founder which case to use. Never read or write the legacy root folders `canonical/`, `investigations/<case>/`, `memory/`.

Read `.q-system/preflight.md` first, then execute the /q-scope steps from `.q-system/commands.md`.

1. Ask the founder to describe the investigation (target, question, context)
2. Define: primary question, targets, hypotheses, collection requirements, boundaries
3. Write to `investigations/<case>/canonical/scope.md`
4. Create initial target files in `investigations/<case>/investigation/targets/` using the template from `investigations/<case>/investigation/targets/_TEMPLATE.md`
5. Create initial collection plan in `investigations/<case>/canonical/collection-plan.md`
6. Update `investigations/<case>/memory/investigation-state.md`
7. Confirm with founder

Argument: $ARGUMENTS (optional: description of investigation to skip the initial question)
