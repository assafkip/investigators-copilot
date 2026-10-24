#!/bin/bash
# ingest-client-document.sh -- register a client-provided file as an EV-NNNN item
#
# Use this for files the client hands us (dossiers, reports, screenshot
# compilations, PDFs, docx narratives) where there is no live URL to archive.
# For URL-sourced evidence, use capture-evidence.sh instead.
#
# Usage:
#   ingest-client-document.sh <file-path> <slug> <type> [flags]
#
# Types:
#   document           -- narrative/report/dossier the client gave us
#   screenshot_only    -- screenshot compilation where original URL is lost
#
# Flags:
#   --case <folder>           defaults to active case
#   --provided-by <who>       e.g. "client (contact name)", "referring investigator (firm)"
#   --received-date <date>    ISO date we received it (defaults to today)
#   --note "text"             free-form notes
#
# Creates:
#   investigations/<case>/investigation/evidence/items/EV-NNNN-<slug>/
#     original.<ext>       # copy of the client file, byte-for-byte
#     source.json          # metadata + integrity hash
#     chain-of-custody.md  # received-from / received-date / hash
#     content.md           # stub + links to existing extracted/ content if present
#
# Requires: jq, shasum

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../../.." && pwd)"

FILE="${1:-}"
SLUG="${2:-}"
TYPE="${3:-}"
if [ -z "$FILE" ] || [ -z "$SLUG" ] || [ -z "$TYPE" ]; then
  echo "Usage: ingest-client-document.sh <file-path> <slug> <type> [--case <folder>] [--provided-by <who>] [--received-date <date>] [--note \"text\"]" >&2
  echo "Types: document | screenshot_only" >&2
  exit 1
fi
shift 3

if [ "$TYPE" != "document" ] && [ "$TYPE" != "screenshot_only" ]; then
  echo "ERROR: type must be 'document' or 'screenshot_only' (got: $TYPE)" >&2
  exit 1
fi

if [ ! -f "$FILE" ]; then
  echo "ERROR: file not found: $FILE" >&2
  exit 1
fi

CASE=""
PROVIDED_BY=""
RECEIVED_DATE="$(date -u +%Y-%m-%d)"
NOTE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --case) CASE="$2"; shift 2 ;;
    --provided-by) PROVIDED_BY="$2"; shift 2 ;;
    --received-date) RECEIVED_DATE="$2"; shift 2 ;;
    --note) NOTE="$2"; shift 2 ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 1 ;;
  esac
done

# Shared resolver: a case name under investigations/, or a path to a case
# folder elsewhere (ASK-2617). Sets CASE and CASE_DIR.
. "$SCRIPT_DIR/lib/active_case.sh"
resolve_case_dir "$CASE" || exit 1

# Assign EV-NNNN ID. Pass CASE_DIR, not CASE: for a case outside
# investigations/ CASE is only the folder name and would resolve elsewhere.
EV_ID=$("$SCRIPT_DIR/next-ev-id.sh" "$CASE_DIR")
ITEM_DIR="$CASE_DIR/investigation/evidence/items/${EV_ID}-${SLUG}"
mkdir -p "$ITEM_DIR"

# Copy original file preserving extension
ORIG_NAME=$(basename "$FILE")
EXT="${ORIG_NAME##*.}"
if [ "$EXT" = "$ORIG_NAME" ]; then
  EXT="bin"
fi
ORIG_COPY="$ITEM_DIR/original.$EXT"
cp "$FILE" "$ORIG_COPY"

# SHA-256 of original
SHA256=$(shasum -a 256 "$ORIG_COPY" | awk '{print $1}')
SIZE=$(wc -c < "$ORIG_COPY" | tr -d ' ')

INGEST_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Look for pre-existing extraction under evidence/extracted/<stem>/
STEM="${ORIG_NAME%.*}"
EXTRACTED_DIR="$CASE_DIR/investigation/evidence/extracted/$STEM"
EXTRACTED_REL=""
HAS_TEXT="false"
HAS_OCR="false"
HAS_IMAGES="false"
if [ -d "$EXTRACTED_DIR" ]; then
  EXTRACTED_REL=$(python3 -c "import os; print(os.path.relpath('$EXTRACTED_DIR', '$ITEM_DIR'))")
  [ -f "$EXTRACTED_DIR/text.md" ] && HAS_TEXT="true"
  [ -f "$EXTRACTED_DIR/ocr.md" ] && HAS_OCR="true"
  [ -d "$EXTRACTED_DIR/images" ] && HAS_IMAGES="true"
fi

echo "=== $EV_ID ==="
echo "File: $FILE"
echo "Case: $CASE"
echo "Dir:  $ITEM_DIR"
echo "Type: $TYPE"
echo "Size: $SIZE bytes"
echo "SHA256: $SHA256"
echo "Extracted: ${EXTRACTED_DIR:-(none)}"
echo ""

# Write source.json
jq -n \
  --arg ev_id "$EV_ID" \
  --arg slug "$SLUG" \
  --arg case "$CASE" \
  --arg type "$TYPE" \
  --arg original_filename "$ORIG_NAME" \
  --arg original_path_stored "original.$EXT" \
  --arg sha256 "$SHA256" \
  --argjson size_bytes "$SIZE" \
  --arg ingest_ts "$INGEST_TS" \
  --arg received_date "$RECEIVED_DATE" \
  --arg provided_by "$PROVIDED_BY" \
  --arg note "$NOTE" \
  --arg extracted_rel "$EXTRACTED_REL" \
  --arg has_text "$HAS_TEXT" \
  --arg has_ocr "$HAS_OCR" \
  --arg has_images "$HAS_IMAGES" \
  '{
    ev_id: $ev_id,
    slug: $slug,
    case: $case,
    type: $type,
    original_filename: $original_filename,
    original_path: $original_path_stored,
    sha256: $sha256,
    size_bytes: $size_bytes,
    provenance: {
      provided_by: $provided_by,
      received_date: $received_date,
      ingest_timestamp_utc: $ingest_ts
    },
    note: $note,
    extraction: {
      linked_dir: $extracted_rel,
      has_text: ($has_text == "true"),
      has_ocr: ($has_ocr == "true"),
      has_images: ($has_images == "true")
    },
    overall_status: "COMPLETE"
  }' > "$ITEM_DIR/source.json"

# Write chain-of-custody.md
CAPTURER="${USER:-unknown}@$(hostname)"
cat > "$ITEM_DIR/chain-of-custody.md" <<EOF
# Chain of Custody -- $EV_ID

- **Ingested by:** $CAPTURER
- **Ingested at:** $INGEST_TS
- **Type:** $TYPE
- **Original filename:** $ORIG_NAME
- **Stored as:** original.$EXT
- **Size:** $SIZE bytes
- **SHA-256:** $SHA256
- **Provided by:** ${PROVIDED_BY:-(unknown)}
- **Received date:** $RECEIVED_DATE
- **Case:** $CASE

## Integrity verification

To verify the stored copy matches the original hash above:

\`\`\`
shasum -a 256 original.$EXT
\`\`\`

Expected: \`$SHA256\`

## Notes

${NOTE:-(none)}
EOF

# Write content.md with links to extracted content if present
cat > "$ITEM_DIR/content.md" <<EOF
# Content -- $EV_ID

**Type:** $TYPE
**Original:** $ORIG_NAME
**Ingested:** $INGEST_TS

EOF

if [ -n "$EXTRACTED_REL" ]; then
  EXTRACTED_AT=""
  EXTRACTOR=""
  if [ -f "$EXTRACTED_DIR/manifest.json" ]; then
    EXTRACTED_AT=$(jq -r '.extracted_at // empty' "$EXTRACTED_DIR/manifest.json" 2>/dev/null)
    EXTRACTOR=$(jq -r '.extractor // empty' "$EXTRACTED_DIR/manifest.json" 2>/dev/null)
  fi
  if [ -n "$EXTRACTED_AT" ] && [ -n "$EXTRACTOR" ]; then
    EXTRACTION_LINE="Text, OCR, and embedded images from this file were extracted on $EXTRACTED_AT by \`$EXTRACTOR\`."
  else
    EXTRACTION_LINE="Text, OCR, and embedded images from this file were previously extracted (extraction predates timestamp tracking -- no recorded date/tool)."
  fi
cat >> "$ITEM_DIR/content.md" <<EOF
## Pre-existing extraction

$EXTRACTION_LINE The extracted content lives at:

\`$EXTRACTED_REL/\`

Linked artifacts:
EOF
  [ "$HAS_TEXT" = "true" ]   && echo "- Text: [\`text.md\`]($EXTRACTED_REL/text.md)" >> "$ITEM_DIR/content.md"
  [ "$HAS_OCR" = "true" ]    && echo "- OCR: [\`ocr.md\`]($EXTRACTED_REL/ocr.md)" >> "$ITEM_DIR/content.md"
  [ "$HAS_IMAGES" = "true" ] && echo "- Images: [\`images/\`]($EXTRACTED_REL/images/)" >> "$ITEM_DIR/content.md"
  cat >> "$ITEM_DIR/content.md" <<EOF

The extracted directory is the working data for analysis. This EV folder holds the canonical original and its hash for chain of custody.
EOF
else
cat >> "$ITEM_DIR/content.md" <<EOF
## Transcription / extraction

No pre-existing extraction found under \`evidence/extracted/\`. To extract, run:

\`\`\`
python3 investigation/evidence/scripts/extract_all.py original.$EXT
\`\`\`

Or fill in transcription manually below.

## Manual transcription

(fill in as needed)
EOF
fi

cat >> "$ITEM_DIR/content.md" <<EOF

## Key references in this document

(fill in: list the named accounts, people, URLs, dates, and events this document contains so other EV items can cross-reference)
EOF

echo "=== $EV_ID: COMPLETE ==="
echo "Dir: $ITEM_DIR"
