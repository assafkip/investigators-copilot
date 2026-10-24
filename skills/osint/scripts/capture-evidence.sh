#!/bin/bash
# capture-evidence.sh -- atomic evidence capture pipeline
#
# Captures a URL to an EV-NNNN evidence folder with full chain of custody.
# Submits to Wayback + archive.today, renders PDF + PNG via Chrome headless,
# computes SHA-256, writes source.json + chain-of-custody.md.
#
# Any single failure marks the item INCOMPLETE and blocks report inclusion.
#
# Usage:
#   capture-evidence.sh <url> <slug> [--case <case-folder>] [--account <@handle>]
#                                    [--platform <name>] [--note "text"]
#                                    [--social] [--archivebox]
#   capture-evidence.sh --batch <file> [--case <case-folder>]
#
# Batch file format (one item per line, tab-separated):
#   <url>\t<slug>\t[platform]\t[account]\t[note]
#   Lines starting with # and blank lines are ignored.
#   In batch mode the script iterates items and fail-stops on the first
#   INCOMPLETE capture (consistent with evidence-capture-protocol.md).
#
# Examples:
#   capture-evidence.sh "https://x.com/DataRepublican/status/123" "datarepublican-origin-thread"
#   capture-evidence.sh --batch /tmp/osint-.../urls.tsv
#
# Optional media backends (additive; default behaviour unchanged without the flags):
#   --social      after the normal capture, download the post's media into the
#                 same EV item (media/) with yt-dlp, gallery-dl and/or bellingcat
#                 auto-archiver (whichever are installed), hash every file into
#                 media-manifest.json and note it in content.md.
#                 auto-archiver runs only when $AUTO_ARCHIVER_CONFIG points at its
#                 orchestration.yaml (it is configured, not flag-driven).
#   --archivebox  also submit the URL to a self-hosted ArchiveBox
#                 ($ARCHIVEBOX_URL, optional $ARCHIVEBOX_API_KEY); the response is
#                 kept as media/archivebox.json.
#   Neither step can flip a COMPLETE item to INCOMPLETE, and neither edits
#   source.json (chain of custody stays immutable).
#
# Requires: curl, jq, shasum, Google Chrome (macOS)

set -euo pipefail

# ---------- Resolve workspace and active case ----------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# ---------- Batch dispatcher ----------
#
# If invoked as `--batch <file>`, iterate the file and re-invoke this script
# per line. Fail-stop on first INCOMPLETE (exit 2 from single-URL path).

if [ "${1:-}" = "--batch" ]; then
  BATCH_FILE="${2:-}"
  if [ -z "$BATCH_FILE" ] || [ ! -f "$BATCH_FILE" ]; then
    echo "ERROR: --batch requires a readable file path" >&2
    exit 1
  fi
  shift 2
  BATCH_EXTRA=("$@")

  COUNT=0
  COMPLETE=0
  while IFS=$'\t' read -r b_url b_slug b_platform b_account b_note || [ -n "${b_url:-}" ]; do
    case "$b_url" in
      '' | \#*) continue ;;
    esac
    if [ -z "${b_slug:-}" ]; then
      echo "ERROR: batch line missing slug for url=$b_url" >&2
      exit 1
    fi
    COUNT=$((COUNT + 1))
    extra=()
    [ -n "${b_platform:-}" ] && extra+=(--platform "$b_platform")
    [ -n "${b_account:-}" ] && extra+=(--account "$b_account")
    [ -n "${b_note:-}" ] && extra+=(--note "$b_note")

    echo "--- batch item $COUNT: $b_url ---"
    if "$0" "$b_url" "$b_slug" "${BATCH_EXTRA[@]}" "${extra[@]}"; then
      COMPLETE=$((COMPLETE + 1))
    else
      rc=$?
      echo "FAIL-STOP: batch item $COUNT returned exit $rc; remaining items skipped." >&2
      echo "batch summary: $COMPLETE/$COUNT complete before failure" >&2
      exit "$rc"
    fi
  done < "$BATCH_FILE"

  echo "batch summary: $COMPLETE/$COUNT complete"
  exit 0
fi

# ---------- Parse args (single-URL path) ----------

URL="${1:-}"
SLUG="${2:-}"
if [ -z "$URL" ] || [ -z "$SLUG" ]; then
  echo "Usage: capture-evidence.sh <url> <slug> [--case <case-folder>] [--account <@handle>] [--platform <name>] [--note \"text\"]" >&2
  echo "       capture-evidence.sh --batch <file> [--case <case-folder>]" >&2
  exit 1
fi
shift 2

CASE=""
ACCOUNT=""
PLATFORM=""
NOTE=""
SOCIAL=0
ARCHIVEBOX=0
while [ $# -gt 0 ]; do
  case "$1" in
    --case) CASE="$2"; shift 2 ;;
    --account) ACCOUNT="$2"; shift 2 ;;
    --platform) PLATFORM="$2"; shift 2 ;;
    --note) NOTE="$2"; shift 2 ;;
    --social) SOCIAL=1; shift ;;
    --archivebox) ARCHIVEBOX=1; shift ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 1 ;;
  esac
done

# shellcheck source=lib/active_case.sh
source "$SCRIPT_DIR/lib/active_case.sh"
resolve_case_dir "$CASE" || exit 1

# ---------- Assign EV-NNNN ID ----------

# CASE_DIR, not CASE: for a case outside investigations/ CASE is only the
# folder name and next-ev-id.sh would resolve it under investigations/ (ASK-2617).
EV_ID=$("$SCRIPT_DIR/next-ev-id.sh" "$CASE_DIR")
ITEM_DIR="$CASE_DIR/investigation/evidence/items/${EV_ID}-${SLUG}"
mkdir -p "$ITEM_DIR"

echo "=== $EV_ID ==="
echo "URL:  $URL"
echo "Case: $CASE"
echo "Dir:  $ITEM_DIR"
echo ""

# ---------- Track status ----------

STATUS_WAYBACK="PENDING"
STATUS_ARCHIVE_TODAY="PENDING"
STATUS_PDF="PENDING"
STATUS_PNG="PENDING"
WAYBACK_URL=""
ARCHIVE_TODAY_URL=""
PDF_SHA=""
CAPTURE_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# ---------- Step 1: Wayback Machine submission (disabled) ----------
# External archive submissions disabled per founder direction 2026-05-05.
# Local hashed PDF + PNG provide sufficient chain of custody.

STATUS_WAYBACK="SKIPPED"
echo "[1/4] Wayback Machine: SKIPPED (local-only mode)"

# ---------- Step 2: archive.today submission (disabled) ----------

STATUS_ARCHIVE_TODAY="SKIPPED"
echo "[2/4] archive.today: SKIPPED (local-only mode)"

# ---------- Step 3: Chrome headless PDF ----------

CHROME="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
CHROME_TIMEOUT_SEC="${CHROME_TIMEOUT_SEC:-45}"

# run_with_timeout <seconds> <cmd...> -- uses perl alarm since macOS lacks GNU timeout
# Runs cmd in background, kills it (and descendants) if it doesn't exit in time.
run_with_timeout() {
  local t=$1; shift
  ( "$@" ) &
  local pid=$!
  ( sleep "$t"; kill -TERM "$pid" 2>/dev/null; sleep 2; kill -KILL "$pid" 2>/dev/null ) &
  local watcher=$!
  wait "$pid" 2>/dev/null
  local rc=$?
  kill "$watcher" 2>/dev/null
  wait "$watcher" 2>/dev/null || true
  return $rc
}

if [ ! -x "$CHROME" ]; then
  echo "[3/4] ERROR: Chrome not found at $CHROME"
  STATUS_PDF="FAIL (chrome missing)"
  STATUS_PNG="FAIL (chrome missing)"
else
  echo "[3/4] Chrome PDF..."
  PDF_PATH="$ITEM_DIR/capture.pdf"
  # Unique user-data-dir per capture to avoid singleton lock conflicts
  CHROME_DATA="$(mktemp -d -t qchrome-XXXXXX)"

  run_with_timeout "$CHROME_TIMEOUT_SEC" \
    "$CHROME" \
      --headless=new \
      --disable-gpu \
      --no-sandbox \
      --no-first-run \
      --no-default-browser-check \
      --disable-extensions \
      --disable-dev-shm-usage \
      --no-pdf-header-footer \
      --user-data-dir="$CHROME_DATA" \
      --virtual-time-budget=10000 \
      --timeout=20000 \
      --print-to-pdf="$PDF_PATH" \
      "$URL" >/dev/null 2>&1 || true
  # Clean up any straggler Chrome children from this user-data-dir
  pkill -f "user-data-dir=$CHROME_DATA" 2>/dev/null || true

  if [ -s "$PDF_PATH" ]; then
    STATUS_PDF="OK"
    PDF_SHA=$(shasum -a 256 "$PDF_PATH" | awk '{print $1}')
    echo "      OK: capture.pdf ($(wc -c < "$PDF_PATH" | tr -d ' ') bytes, sha256=${PDF_SHA:0:16}...)"
  else
    STATUS_PDF="FAIL"
    echo "      FAIL"
  fi

  # ---------- Step 4: Chrome headless PNG ----------
  echo "[4/4] Chrome PNG..."
  PNG_PATH="$ITEM_DIR/capture.png"
  CHROME_DATA2="$(mktemp -d -t qchrome-XXXXXX)"

  run_with_timeout "$CHROME_TIMEOUT_SEC" \
    "$CHROME" \
      --headless=new \
      --disable-gpu \
      --no-sandbox \
      --no-first-run \
      --no-default-browser-check \
      --disable-extensions \
      --disable-dev-shm-usage \
      --hide-scrollbars \
      --user-data-dir="$CHROME_DATA2" \
      --virtual-time-budget=10000 \
      --timeout=20000 \
      --window-size=1280,2400 \
      --screenshot="$PNG_PATH" \
      "$URL" >/dev/null 2>&1 || true
  pkill -f "user-data-dir=$CHROME_DATA2" 2>/dev/null || true

  if [ -s "$PNG_PATH" ]; then
    STATUS_PNG="OK"
    echo "      OK: capture.png ($(wc -c < "$PNG_PATH" | tr -d ' ') bytes)"
  else
    STATUS_PNG="FAIL"
    echo "      FAIL"
  fi

  rm -rf "$CHROME_DATA" "$CHROME_DATA2"
fi

# ---------- Write source.json ----------

jq -n \
  --arg ev_id "$EV_ID" \
  --arg url "$URL" \
  --arg slug "$SLUG" \
  --arg case "$CASE" \
  --arg account "$ACCOUNT" \
  --arg platform "$PLATFORM" \
  --arg note "$NOTE" \
  --arg capture_ts "$CAPTURE_TS" \
  --arg wayback_url "$WAYBACK_URL" \
  --arg archive_today_url "$ARCHIVE_TODAY_URL" \
  --arg status_wayback "$STATUS_WAYBACK" \
  --arg status_archive_today "$STATUS_ARCHIVE_TODAY" \
  --arg status_pdf "$STATUS_PDF" \
  --arg status_png "$STATUS_PNG" \
  --arg pdf_sha256 "$PDF_SHA" \
  '{
    ev_id: $ev_id,
    slug: $slug,
    case: $case,
    source_url: $url,
    account: $account,
    platform: $platform,
    note: $note,
    capture_timestamp_utc: $capture_ts,
    type: "url",
    captures: {
      wayback: { status: $status_wayback, url: $wayback_url },
      archive_today: { status: $status_archive_today, url: $archive_today_url },
      pdf: { status: $status_pdf, path: "capture.pdf", sha256: $pdf_sha256 },
      png: { status: $status_png, path: "capture.png" }
    }
  }' > "$ITEM_DIR/source.json"

# ---------- Overall status ----------
#
# REQUIRED for COMPLETE: PDF OK, PNG OK.
# External archives (Wayback, archive.today) are disabled in local-only mode.
# Reason: founder directive -- local hashed PDF + PNG are sufficient chain of custody.

if [ "$STATUS_PDF" = "OK" ] && [ "$STATUS_PNG" = "OK" ]; then
  OVERALL="COMPLETE"
else
  OVERALL="INCOMPLETE"
fi
jq ". + {overall_status: \"$OVERALL\"}" "$ITEM_DIR/source.json" > "$ITEM_DIR/source.json.tmp" \
  && mv "$ITEM_DIR/source.json.tmp" "$ITEM_DIR/source.json"

# ---------- Write chain-of-custody.md ----------

CAPTURER="${USER:-unknown}@$(hostname)"
cat > "$ITEM_DIR/chain-of-custody.md" <<EOF
# Chain of Custody -- $EV_ID

- **Captured by:** $CAPTURER
- **Captured at:** $CAPTURE_TS
- **Source URL:** $URL
- **Case:** $CASE
- **Account:** ${ACCOUNT:-(none)}
- **Platform:** ${PLATFORM:-(none)}
- **Overall status:** $OVERALL

## Captures

| Capture | Status | Reference |
|---------|--------|-----------|
| Wayback Machine | $STATUS_WAYBACK | ${WAYBACK_URL:-(none)} |
| archive.today | $STATUS_ARCHIVE_TODAY | ${ARCHIVE_TODAY_URL:-(none)} |
| Full-page PDF | $STATUS_PDF | capture.pdf (sha256: ${PDF_SHA:-n/a}) |
| PNG (viewport) | $STATUS_PNG | capture.png |

## Notes

${NOTE:-(none)}

## Integrity

- PDF SHA-256: ${PDF_SHA:-n/a}
- To verify: \`shasum -a 256 capture.pdf\` must match above.
- source.json written atomically at capture time and should not be modified.
EOF

# ---------- content.md stub ----------

cat > "$ITEM_DIR/content.md" <<EOF
# Content -- $EV_ID

> Transcription and OCR notes for this evidence item.
> Source: $URL
> Captured: $CAPTURE_TS

## Transcribed text

(fill in after capture: direct transcription of post text)

## OCR / extracted text

(fill in: OCR output from capture.png/pdf if needed)

## Observed metadata

- Post timestamp:
- View count:
- Engagement (likes/reposts/replies):
- Author display name:
EOF

# ---------- Step 7: carve artifacts (strings / QR / EXIF) -- additive, never fail-stop ----------
# Carving is ENRICHMENT, not chain-of-custody: each tool is optional and wrapped in `|| true`
# so a missing binary OR a no-QR image (zbarimg exits non-zero when it finds nothing) cannot
# abort the capture under `set -euo pipefail`. Findings APPEND into content.md; source.json
# stays immutable; a COMPLETE capture is never flipped to INCOMPLETE by carving.
# Optional binaries: brew install exiftool zbar  (Linux: apt install libimage-exiftool-perl zbar-tools)
# Ported 2026-10-10 from kipi-investigations capture-evidence.sh.
{
  echo ""
  echo "## Carved artifacts (strings / QR / EXIF)"
  echo ""
  CARVE_TARGETS=()
  [ -s "${PNG_PATH:-}" ] && CARVE_TARGETS+=("$PNG_PATH")
  [ -s "${PDF_PATH:-}" ] && CARVE_TARGETS+=("$PDF_PATH")
  if [ "${#CARVE_TARGETS[@]}" -gt 0 ]; then
    for f in "${CARVE_TARGETS[@]}"; do
      base=$(basename "$f")
      if command -v zbarimg >/dev/null 2>&1; then
        qr=$(zbarimg --quiet --raw "$f" 2>/dev/null || true)
        [ -n "$qr" ] && echo "- QR/barcode in $base: \`$qr\`" || true
      else
        echo "- (zbarimg not installed -- QR decode skipped for $base; brew install zbar)"
      fi
      if command -v exiftool >/dev/null 2>&1; then
        gps=$(exiftool -s3 -GPSPosition "$f" 2>/dev/null || true)
        [ -n "$gps" ] && echo "- EXIF GPS in $base: $gps" || true
      else
        echo "- (exiftool not installed -- EXIF skipped for $base; brew install exiftool)"
      fi
      if command -v strings >/dev/null 2>&1; then
        hits=$(strings -n 8 "$f" 2>/dev/null | grep -aoiE '(0x[a-f0-9]{40}|bc1[a-z0-9]{20,}|https?://[^ ]+|[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,})' 2>/dev/null | sort -u | head -20 || true)
        [ -n "$hits" ] && { echo "- Strings hits in $base:"; echo "$hits" | sed 's/^/  - /'; } || true
      fi
    done
  else
    echo "- (no capture.png / capture.pdf to carve)"
  fi
} >> "$ITEM_DIR/content.md" 2>/dev/null || true

# ---------- Step 8: social media / ArchiveBox backends -- additive, never fail-stop ----------
# Added 2026-10-10 (Phase 6). Runs only with --social / --archivebox. Like carving,
# this is ENRICHMENT: every command is wrapped so a missing tool, a private post or
# a network error cannot abort the script, and OVERALL is never recomputed here,
# so a COMPLETE item stays COMPLETE. Media hashes live in media-manifest.json, not
# source.json, because source.json is immutable after capture.
SOCIAL_TIMEOUT_SEC="${SOCIAL_TIMEOUT_SEC:-300}"

sha256_file() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    sha256sum "$1" | awk '{print $1}'
  fi
}

write_media_manifest() {
  local media_dir="$1" backends="$2" manifest="$ITEM_DIR/media-manifest.json"
  local entries="[]" rel sha size
  while IFS= read -r -d '' f; do
    rel="${f#"$ITEM_DIR"/}"
    sha=$(sha256_file "$f")
    size=$(wc -c < "$f" | tr -d ' ')
    entries=$(jq --arg p "$rel" --arg s "$sha" --argjson b "$size" \
      '. + [{path: $p, sha256: $s, bytes: $b}]' <<<"$entries")
  done < <(find "$media_dir" -type f -print0 2>/dev/null | sort -z)
  jq -n --arg ev "$EV_ID" --arg url "$URL" --arg ts "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
    --arg backends "$backends" --argjson files "$entries" \
    '{ev_id: $ev, source_url: $url, generated_utc: $ts,
      backends: ($backends | split(",") | map(select(length > 0))),
      files: $files}' > "$manifest"
  jq '.files | length' "$manifest"
}

if [ "$SOCIAL" = "1" ] || [ "$ARCHIVEBOX" = "1" ]; then
  MEDIA_DIR="$ITEM_DIR/media"
  mkdir -p "$MEDIA_DIR"
  BACKENDS_RUN=""
  SOCIAL_NOTES=()
  echo "[8] Media backends..."

  if [ "$SOCIAL" = "1" ]; then
    if command -v yt-dlp >/dev/null 2>&1; then
      run_with_timeout "$SOCIAL_TIMEOUT_SEC" yt-dlp --no-playlist --no-progress \
        --write-info-json --restrict-filenames \
        -o "$MEDIA_DIR/yt-dlp/%(extractor)s-%(id)s.%(ext)s" "$URL" >/dev/null 2>&1 \
        && SOCIAL_NOTES+=("yt-dlp: downloaded") \
        || SOCIAL_NOTES+=("yt-dlp: no media or failed (not an error for the capture)")
      BACKENDS_RUN="$BACKENDS_RUN,yt-dlp"
    else
      SOCIAL_NOTES+=("yt-dlp: not installed (pipx install yt-dlp)")
    fi
    if command -v gallery-dl >/dev/null 2>&1; then
      run_with_timeout "$SOCIAL_TIMEOUT_SEC" gallery-dl --write-metadata \
        -D "$MEDIA_DIR/gallery-dl" "$URL" >/dev/null 2>&1 \
        && SOCIAL_NOTES+=("gallery-dl: downloaded") \
        || SOCIAL_NOTES+=("gallery-dl: no media or failed (not an error for the capture)")
      BACKENDS_RUN="$BACKENDS_RUN,gallery-dl"
    else
      SOCIAL_NOTES+=("gallery-dl: not installed (pipx install gallery-dl)")
    fi
    if command -v auto-archiver >/dev/null 2>&1 && [ -n "${AUTO_ARCHIVER_CONFIG:-}" ] \
       && [ -f "${AUTO_ARCHIVER_CONFIG}" ]; then
      mkdir -p "$MEDIA_DIR/auto-archiver"
      # Absolute before the cd: a relative config path passed the -f check above and
      # then broke inside media/auto-archiver (post-merge review, ASK-2613).
      AA_CONFIG="$(cd "$(dirname "$AUTO_ARCHIVER_CONFIG")" && pwd)/$(basename "$AUTO_ARCHIVER_CONFIG")"
      ( cd "$MEDIA_DIR/auto-archiver" && run_with_timeout "$SOCIAL_TIMEOUT_SEC" \
          auto-archiver --config "$AA_CONFIG" "$URL" > auto-archiver.log 2>&1 ) \
        && SOCIAL_NOTES+=("auto-archiver: ran (see media/auto-archiver/auto-archiver.log; WACZ/media per your orchestration.yaml)") \
        || SOCIAL_NOTES+=("auto-archiver: failed (see media/auto-archiver/auto-archiver.log)")
      BACKENDS_RUN="$BACKENDS_RUN,auto-archiver"
    else
      SOCIAL_NOTES+=("auto-archiver: skipped (needs the auto-archiver CLI and AUTO_ARCHIVER_CONFIG=orchestration.yaml)")
    fi
  fi

  if [ "$ARCHIVEBOX" = "1" ]; then
    if [ -n "${ARCHIVEBOX_URL:-}" ]; then
      AB_AUTH=()
      [ -n "${ARCHIVEBOX_API_KEY:-}" ] && AB_AUTH=(-H "X-ArchiveBox-API-Key: ${ARCHIVEBOX_API_KEY}")
      AB_CODE=$(curl -sS --max-time 120 -o "$MEDIA_DIR/archivebox.json" -w '%{http_code}' \
        -H 'Content-Type: application/json' ${AB_AUTH[@]+"${AB_AUTH[@]}"} \
        -X POST "${ARCHIVEBOX_URL%/}/api/v1/cli/add" \
        --data "$(jq -n --arg u "$URL" --arg t "$EV_ID" '{urls: [$u], tag: $t, depth: 0, update: false}')" \
        2>/dev/null || true)
      AB_CODE="${AB_CODE:-000}"  # -w already prints 000 on failure; echoing another gave 000000
      if [ "$AB_CODE" = "200" ]; then
        SOCIAL_NOTES+=("archivebox: submitted to ${ARCHIVEBOX_URL} (tag $EV_ID)")
      else
        SOCIAL_NOTES+=("archivebox: HTTP $AB_CODE from ${ARCHIVEBOX_URL} (not an error for the capture)")
      fi
      BACKENDS_RUN="$BACKENDS_RUN,archivebox"
    else
      SOCIAL_NOTES+=("archivebox: skipped (ARCHIVEBOX_URL not set)")
    fi
  fi

  MEDIA_COUNT=$(write_media_manifest "$MEDIA_DIR" "${BACKENDS_RUN#,}" 2>/dev/null || echo "?")
  {
    echo ""
    echo "## Media archive (--social / --archivebox)"
    echo ""
    echo "- Files: $MEDIA_COUNT, hashed in \`media-manifest.json\` (paths relative to this item)"
    for n in "${SOCIAL_NOTES[@]}"; do echo "- $n"; done
    echo "- Media is enrichment; it does not change this item's overall status ($OVERALL)."
  } >> "$ITEM_DIR/content.md" 2>/dev/null || true
  echo "      media files: $MEDIA_COUNT (media-manifest.json)"
fi

echo ""
echo "=== $EV_ID: $OVERALL ==="
echo "Dir: $ITEM_DIR"
if [ "$OVERALL" = "INCOMPLETE" ]; then
  echo "WARNING: this item is INCOMPLETE and must not be cited in reports until resolved." >&2
  exit 2
fi
