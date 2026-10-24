# Evidence Capture Protocol (ENFORCED, all investigations)

This rule governs how evidence enters any investigation under `investigations/`. It is non-negotiable. The founder approved this protocol on 2026-04-09 after identifying that post-hoc screenshot dumps break chain of custody.

## Core principle

**Every piece of evidence gets captured at the time of collection, not after.** Reports must reference evidence by stable ID, with the screenshot rendered inline. No report writer should ever be responsible for "going back to capture screenshots" because that step is already done.

## Folder format

Every evidence item lives in its own folder under the active case:

```
investigations/<case>/investigation/evidence/items/EV-NNNN-<slug>/
  source.json              # capture metadata + integrity hashes (REQUIRED)
  chain-of-custody.md      # who/when/how (REQUIRED)
  content.md               # transcription + OCR notes (REQUIRED stub)
  capture.pdf              # full-page PDF (REQUIRED for URL-sourced items)
  capture.png              # PNG rendering for inline embedding (REQUIRED for URL-sourced items)
```

The EV-NNNN ID is zero-padded four digits, assigned by `skills/osint/scripts/next-ev-id.sh`, monotonic per case. Never reuse an ID. Never renumber.

## The one command that creates evidence

```
bash skills/osint/scripts/capture-evidence.sh <url> <slug> \
  [--case <case-folder>] [--account <@handle>] [--platform <name>] [--note "text"] \
  [--social] [--archivebox]
bash skills/osint/scripts/capture-evidence.sh --batch <urls.tsv> [--case <case-folder>]
```

This script:
1. Assigns the next EV-NNNN
2. Wayback Machine submission -- SKIPPED (local-only mode; the script records `"status": "SKIPPED"`)
3. archive.today submission -- SKIPPED (local-only mode)
4. Runs Chrome headless to produce `capture.pdf` + `capture.png`
5. Computes SHA-256 of the PDF
6. Writes `source.json`, `chain-of-custody.md`, `content.md` stub
7. Carves artifacts from the capture (QR codes via `zbarimg`, EXIF GPS via `exiftool`, wallet/email/URL strings) into `content.md`. Every tool is optional and this step can never mark the item INCOMPLETE.

Optional, additive flags (both run AFTER steps 1-7; files go to the item's `media/`):
- `--social` downloads the post's media with yt-dlp, gallery-dl and/or bellingcat auto-archiver (whichever are installed; auto-archiver only with `$AUTO_ARCHIVER_CONFIG`), hashes every file into the item's `media-manifest.json`, and notes it in `content.md`.
- `--archivebox` submits the URL to a self-hosted ArchiveBox (`$ARCHIVEBOX_URL`, optional `$ARCHIVEBOX_API_KEY`) and keeps the response as `media/archivebox.json`.

Neither flag can flip an item's status (a COMPLETE item stays COMPLETE if a media download fails; an INCOMPLETE item is not rescued by a successful one), and neither edits `source.json`. Install the tools with `setup-tools.sh --only yt-dlp,gallery-dl,auto-archiver` or `--docker archivebox`.

If step 4 or 5 fails, the item is marked `INCOMPLETE` in `source.json` and the script exits non-zero. An INCOMPLETE item **may not be cited in any report** until it's resolved or explicitly re-classified. (Steps 2-3 are intentionally skipped, not failures.)

**Do not write your own capture logic. Do not manually zip screenshots.** Use the script. If the script is broken, fix the script, do not bypass it.

## SCREENSHOT_ONLY evidence class

For client-provided evidence where the original URL is lost (e.g., the Sowell PDF the client gave us on 2026-04-09), use this structure:

```
items/EV-NNNN-<slug>/
  original.pdf (or .png/.jpg)     # the artifact the client gave us
  source.json                     # {"type": "screenshot_only", "provided_by": "<who>", ...}
  chain-of-custody.md             # received-from, received-date, hash of original
  content.md                      # transcription + OCR
```

Set `"type": "screenshot_only"` in `source.json`. Reports can cite these items but the rendered footnote must say `Screenshot-only (no original URL)` so an attorney immediately sees the evidentiary difference.

## Citation in reports

All findings, briefs, and reports reference evidence by ID:

```markdown
At 2:46 AM Mar 14, @ohmstone posted "There are 9243 reasons why Brad sucks." [EV-0014]
```

Before delivery, run:

```
python3 skills/osint/scripts/render-report.py <input.md> <output.md>
```

This resolves `[EV-NNNN]` citations to inline PNG embeds + footnote metadata. It exits non-zero if any citation is broken.

## Forbidden patterns

- Do not create a `screenshots/` dump folder alongside a report. That pattern is deprecated.
- Do not reference evidence by filename (e.g., "see image4.png"). Always use the EV-NNNN ID.
- Do not cite an INCOMPLETE item in a report.
- Do not modify `source.json` after capture. Chain of custody depends on its immutability.
- Do not delete an EV-NNNN folder even if the evidence turns out to be irrelevant. Mark it superseded in `content.md` instead.
- Do not bypass `capture-evidence.sh` to "save time." The script enforces the protocol.

## When the script fails

Fail-stop rule applies. If `capture-evidence.sh` fails:
1. Stop collection immediately.
2. Tell the founder what broke (which step failed, what URL).
3. Wait for instructions before continuing.

Common failure modes:
- Chrome headless blocked by a paywall or login wall -- the PDF will be the login page; mark INCOMPLETE and flag
- URL redirects to a 404 or deleted page -- archive still useful; mark INCOMPLETE if Chrome can't render

## Client-provided documents (CSV, PDF, DOCX, images) -- ingest before you touch them

Every client-provided file goes through TWO existing tools, in order, before any
custom classification or extraction script is written or run against it:

```
bash skills/osint/scripts/ingest-client-document.sh <file> <slug> document \
  --case <case-folder> --provided-by "<who>"

python3 skills/osint/scripts/extract-intake.py --case <case-folder>
```

The first registers the file as an EV-NNNN item (SHA-256 hash + chain-of-custody).
The second deterministically extracts verbatim content (text/OCR/CSV rows, no LLM,
no network) to `investigation/evidence/extracted/<stem>/`. Any downstream
identity-classification or leak-record analysis is a separate script that reads
FROM that extracted output, not from a loose copy in `investigation/intake/`.

**Scar (2026-07-21, case-001-example):** a client CSV was copied straight
into `investigation/intake/` and a bespoke classifier was written and run against
it directly, skipping both tools entirely even though they already existed and
were built for exactly this. This was prompt-only enforcement (a rule with no
hook) -- see `q-system/CLAUDE.md`'s ban on that pattern. Fixed below.

## Enforcement

Any new investigation case gets the `investigation/evidence/items/` directory scaffolded automatically via `templates/new-investigation/`. The template includes a `README.md` pointing at this protocol.

Any time a Q command (`/q-collect`, `/q-osint`, `/q-intake`, `/q-brief`, `/q-export`) touches evidence, it must route through `capture-evidence.sh` for URL-sourced items.

**Deterministic gate (added 2026-07-21):** `skills/osint/scripts/evidence-pipeline-guard.py`, wired as a PostToolUse hook (Edit/Write/MultiEdit/Bash) in `.claude/settings.json`. It BLOCKS (exit 2) any new or executed script under `investigation/evidence/scripts/` in a case whose `investigation/intake/` contains a file that lacks either a registered EV-NNNN item or a deterministic extraction. No-ops when a case has no document intake at all (pure OSINT collection). Self-test: `python3 skills/osint/scripts/evidence-pipeline-guard.py --self-test`.
