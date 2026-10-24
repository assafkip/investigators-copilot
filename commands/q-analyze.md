Review all collected data and surface patterns, connections, and gaps.

**Active case:** read the case folder name from the first line of `.active-case` (written by `/q-begin` and `/q-new-case`). Every path below is inside `investigations/<case>/`. If `.active-case` is missing or empty, ask the founder which case to use. Never read or write the legacy root folders `canonical/`, `investigations/<case>/`, `memory/`.

Execute the /q-analyze steps from `.q-system/commands.md`.

1. Read all target profiles in `investigations/<case>/investigation/targets/`
2. Read all findings in `investigations/<case>/investigation/findings/`
3. Read timeline in `investigations/<case>/investigation/timelines/`
4. Identify: connections, patterns, gaps, contradictions, new leads
5. For each finding, assess: confidence level, supporting evidence, alternative explanations
6. Update `investigations/<case>/investigation/findings/` with new assessments using the template from `investigations/<case>/investigation/findings/_TEMPLATE.md`
7. Update `investigations/<case>/canonical/collection-plan.md` with new requirements
8. Present analysis to founder

Argument: $ARGUMENTS (optional: specific aspect to focus analysis on)
