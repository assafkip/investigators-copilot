Force a structured challenge of all investigation assumptions and hypotheses.

This is a mid-investigation health check. Do NOT skip steps.

**Active case:** read the case folder name from the first line of `.active-case` (written by `/q-begin` and `/q-new-case`). Every path below is inside `investigations/<case>/`. If `.active-case` is missing or empty, ask the founder which case to use. Never read or write the legacy root folders `canonical/`, `investigations/<case>/`, `memory/`.

## Steps

1. Read `investigations/<case>/canonical/scope.md` for hypotheses
2. Read ALL files in `investigations/<case>/investigation/findings/`
3. Read `investigations/<case>/investigation/evidence/` index (list files, read key ones)
4. Read `investigations/<case>/memory/investigation-state.md` for current assessment

## For each hypothesis, answer:

| Question | Answer |
|----------|--------|
| What evidence SUPPORTS this? | (cite specific files) |
| What evidence CONTRADICTS this? | (cite specific files) |
| What would DISPROVE this? | (describe the test) |
| Have we actually looked for disproving evidence? | Yes/No |
| Is this based on fact, inference, or assumption? | (classify) |
| Could the same evidence support a different explanation? | (describe) |

## Then check for:

- **Circular reasoning:** Are we using conclusion A to support conclusion B, and B to support A?
- **Name-matching traps:** Are we assuming two accounts/profiles are the same person just because the name matches?
- **Confirmation bias:** Have we only collected evidence that supports our theory?
- **Source independence:** Do multiple "sources" actually trace back to the same original data point?
- **Community inference vs. identification:** Did witnesses IDENTIFY someone, or INFER from context?

## Output

Write to `investigations/<case>/investigation/findings/CHALLENGE-YYYY-MM-DD.md` with:
- Each hypothesis: current confidence, revised confidence (if changed), and why
- Top 3 weakest assumptions that need testing
- Recommended collection to test (not confirm) the weakest assumptions
- Tag each recommended action with Energy + Time Est

Present the challenge to the founder as choices, not commands.
