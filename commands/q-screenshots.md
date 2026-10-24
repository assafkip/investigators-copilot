Capture every URL referenced in a report or brief as a chain-of-custody evidence item (EV-NNNN).

Arguments: $ARGUMENTS (path to the target file, or omit to use the most recent file in the active case's output/)

**Active case:** read the case folder name from the first line of `.active-case`. If it is missing or empty, ask the founder which case to use.

## Steps

1. Read the target file
2. Extract all URLs from the document (links, references, appendix citations)
3. Deduplicate and filter:
   - Skip internal file paths
   - Skip mailto: links
   - Skip URLs that are clearly API endpoints (not human-readable pages)
   - Skip URLs already captured (an EV item whose `source.json` has that `source_url`)
4. Write a batch file, one line per URL: `<url>\t<slug>\t[platform]\t[account]\t[note]`
5. Run: `bash skills/osint/scripts/capture-evidence.sh --batch <file> --case <case>`
   - Per-URL extras (single-URL form): `--social` downloads post media into the same EV item; `--archivebox` adds an ArchiveBox copy. Both are additive and never change the item's status.
6. Replace raw URLs in the report with `[EV-NNNN]` citations, then render: `python3 skills/osint/scripts/render-report.py <in.md> <out.md>`

## Output

- EV-NNNN folders under `investigations/<case>/investigation/evidence/items/` (capture.pdf, capture.png, source.json, chain-of-custody.md, content.md)
- The report cites evidence by ID. No `screenshots/` dump folder and no GO FULL PAGE extension (deprecated by `.claude/rules/evidence-capture-protocol.md`).

## Failure

The batch fail-stops on the first INCOMPLETE item (login wall, paywall, 404, render failure). Stop and tell the founder which URL and why; an INCOMPLETE item is never cited.
