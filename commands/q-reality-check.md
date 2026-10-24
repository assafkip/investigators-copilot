Challenger mode. Argue AGAINST current hypotheses and findings to find weak spots.

Different from /q-challenge (which audits evidence quality). This command adopts the opposing perspective and stress-tests conclusions.

**Active case:** read the case folder name from the first line of `.active-case` (written by `/q-begin` and `/q-new-case`). Every path below is inside `investigations/<case>/`. If `.active-case` is missing or empty, ask the founder which case to use. Never read or write the legacy root folders `canonical/`, `investigations/<case>/`, `memory/`.

## Steps

1. Read the active case's scope, findings, and investigation state
2. For each major hypothesis or finding, temporarily argue the OPPOSITE:
   - "What if this person is NOT the harasser?"
   - "What if the accounts are NOT connected?"
   - "What if the evidence supports a completely different explanation?"
3. Rate each hypothesis:
   - **STRONG:** Would survive cross-examination. Multiple independent evidence sources.
   - **MODERATE:** Plausible but relies on a single evidence chain or inference.
   - **WEAK:** Could be coincidence, name matching, or confirmation bias.
4. For each MODERATE or WEAK finding:
   - What specific evidence would upgrade it to STRONG?
   - What's the simplest alternative explanation?
   - What collection could test it? (Energy tag + Time Est)
5. Optional, when a draft brief/report exists: `python3 skills/osint/scripts/validate-citations.py <brief.md> --case <case>`. Dead links and citing sentences whose hard tokens are missing from the captured EV item are WEAK candidates.

## Output

Write to the active case's `investigation/findings/REALITY-CHECK-YYYY-MM-DD.md`

## Tone

Not hostile. Socratic. The goal is to find weak spots before a client, attorney, or opposing party does. Frame as: "How would someone challenge this in court/deposition?"

Run before finalizing any brief or report.
