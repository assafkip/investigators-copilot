Export investigation data in a structured format.

**Active case:** read the case folder name from the first line of `.active-case` (written by `/q-begin` and `/q-new-case`). Every path below is inside `investigations/<case>/`. If `.active-case` is missing or empty, ask the founder which case to use. Never read or write the legacy root folders `canonical/`, `investigations/<case>/`, `memory/`.

Execute the /q-export steps from `.q-system/commands.md`.

Formats: markdown, json, timeline-html, stix, misp, csv, map. Flag: `--redact`.

S=`skills/osint/scripts`

1. Gather all investigation files from `investigations/<case>/investigation/` and `output/analyses/`
2. Export in requested format:
   - markdown: Full investigation report (render `[EV-NNNN]` citations with `python3 $S/render-report.py <in.md> <out.md>`; it fails on a broken citation)
   - json: Structured data (targets, findings, links, timeline)
   - timeline-html: `python3 $S/render-timeline.py --case <case>` (add `--timesketch` for a Timesketch import CSV)
   - stix | misp | csv: `python3 $S/export-intel.py stix|misp|csv|all --case <case> [--tlp clear|green|amber|red]`
   - map: `python3 $S/render-map.py --case <case>` (EXIF/analyst points, not verified locations)
3. Every URL the export relies on must be an EV-NNNN item. Capture missing ones with `bash $S/capture-evidence.sh --batch <file> --case <case>` (see `/q-screenshots`). No `screenshots/` dump folder.
4. `--redact`: run `python3 $S/redact-pii.py <export.md>`; it writes `<stem>.redacted.md` beside the export (presidio if installed, else regex). Share the redacted copy; keep the original in the case.
5. Save to `investigations/<case>/output/exports/`
6. Present to founder

Argument: $ARGUMENTS (optional: format -- markdown, json, timeline-html, stix, misp, csv, or map; optional `--redact`. Defaults to markdown.)
