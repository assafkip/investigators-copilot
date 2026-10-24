Generate a structured investigation brief summarizing current state.

**Active case:** read the case folder name from the first line of `.active-case` (written by `/q-begin` and `/q-new-case`). Every path below is inside `investigations/<case>/`. If `.active-case` is missing or empty, ask the founder which case to use. Never read or write the legacy root folders `canonical/`, `investigations/<case>/`, `memory/`.

Execute the /q-brief steps from `.q-system/commands.md`. Summary:

0. **Gate check (blocking, all three):** `investigation/findings/CHALLENGE-*.md` exists (else run `/q-challenge`); `/q-client-questions` has been run and answered; `output/analyses/` holds a premortem (else run `/analyze premortem`). If any gate fails, name it and stop.
1. Read `investigations/<case>/canonical/scope.md`, all targets, all findings, timeline, and completed analyses in `output/analyses/`
2. Generate brief with:
   - Executive summary: 3-5 bullet points answering the primary question
   - Key findings: confirmed intelligence with confidence levels and citations
   - Target matrix: all targets, status, key connections
   - Timeline summary: major events in chronological order
   - Collection gaps: what we still need
   - Hypotheses status: supported / refuted / undetermined
   - Recommended next steps: prioritized by impact, tagged with Energy + Time Est
3. **Evidence pass:** every URL the brief relies on is an `[EV-NNNN]` item (capture missing ones with `capture-evidence.sh --batch <file> --case <case>`), then render with `python3 skills/osint/scripts/render-report.py <brief.md> <out.md>` (fails on a broken citation)
4. Save to `investigations/<case>/output/briefs/brief-YYYY-MM-DD.md`
5. Present to founder

Argument: $ARGUMENTS (optional: "executive" for short version)
