Process new information into the investigation structure.

**Active case:** read the case folder name from the first line of `.active-case` (written by `/q-begin` and `/q-new-case`). Every path below is inside `investigations/<case>/`. If `.active-case` is missing or empty, ask the founder which case to use. Never read or write the legacy root folders `canonical/`, `investigations/<case>/`, `memory/`.

Execute the /q-intake steps from `.q-system/commands.md`.

Types: target, finding, evidence, tip

1. Ask for the information (or accept paste/file)
2. Classify: What type of information is this?
3. Assess reliability using the A-F scale from `.q-system/preflight.md`
4. Route to appropriate file:
   - New person/entity -> `investigations/<case>/investigation/targets/[name].md`
   - Confirmed intelligence -> `investigations/<case>/investigation/findings/`
   - Raw data/screenshots -> `investigations/<case>/investigation/evidence/`
   - Timeline events -> `investigations/<case>/investigation/timelines/`
5. Cross-reference against existing targets and findings
6. Flag any new leads or connections surfaced
7. Update `investigations/<case>/memory/investigation-state.md`

Client files: `ingest-client-document.sh` then `extract-intake.py --case <case>` first (see commands.md). `extract-intake.py` also writes `iocs.json`, `entities.json`, `exif.json` per document under `evidence/extracted/<stem>/`: T3 leads, never findings. `--ner langextract` sends text to Gemini (founder approval for client documents).

Argument: $ARGUMENTS (optional: type -- target, finding, evidence, or tip)
