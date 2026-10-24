# Evidence Items

Every piece of evidence lives in its own `EV-NNNN-<slug>/` folder under this directory. This is enforced by the evidence capture protocol (`.claude/rules/evidence-capture-protocol.md`).

## Creating an evidence item

```
bash skills/osint/scripts/capture-evidence.sh <url> <slug>
```

This runs the full capture pipeline (Wayback + archive.today + Chrome PDF + PNG + SHA-256 + metadata) and produces an atomic `EV-NNNN-<slug>/` folder. If any step fails, the item is marked `INCOMPLETE` and must not be cited in a report.

## Folder contents (URL-sourced items)

```
EV-NNNN-<slug>/
  source.json              # capture metadata + integrity hashes
  chain-of-custody.md      # capturer, timestamp, integrity
  content.md               # transcription + OCR notes
  capture.pdf              # full-page PDF
  capture.png              # PNG rendering for inline embedding
```

## Folder contents (screenshot-only items, no URL)

```
EV-NNNN-<slug>/
  original.pdf             # client-provided artifact
  source.json              # type: "screenshot_only"
  chain-of-custody.md      # received-from + received-date
  content.md               # transcription + OCR
```

## Citing in reports

```markdown
At 2:46 AM on Mar 14, @ohmstone posted "There are 9243 reasons why Brad sucks." [EV-0014]
```

Run `python3 skills/osint/scripts/render-report.py <in.md> <out.md>` before delivery. The renderer embeds the PNG inline and appends a footnote block with capture metadata.

## Rules

- Never reuse an EV-NNNN ID.
- Never delete an item even if it turns out irrelevant -- mark superseded in `content.md`.
- Never modify `source.json` after capture.
- Never bypass `capture-evidence.sh` for URL-sourced items.

See `.claude/rules/evidence-capture-protocol.md` for the full protocol.
