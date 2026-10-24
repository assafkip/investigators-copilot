#!/bin/bash
# reverse-image.sh -- Google Cloud Vision web detection for one image (T3 output)
#
# Sends a local image (or a public image URL) to the Cloud Vision
# images:annotate endpoint with WEB_DETECTION + LANDMARK_DETECTION and prints a
# normalized JSON document: web entities, full / partial matching images,
# pages with matching images, visually similar images, best-guess labels and
# landmarks (with lat/lon when Vision returns them).
#
# Pattern adapted from GONZOsint/gvision (Unlicense): web entities + landmarks
# from the Vision API. Re-implemented here as a keyed REST call, no SDK.
#
# Every hit is T3 (automated tool output): a lead for the hypothesis queue,
# never a finding on its own. Capture any page you intend to cite with
# capture-evidence.sh.
#
# Usage:
#   reverse-image.sh <image-path-or-url> [--case <case-folder|"">] [--max N] [--raw]
#   (--case "" saves under the active case from .active-case)
#
# Env:
#   GOOGLE_VISION_API_KEY   Cloud Vision API key (required)
#
# Output: JSON on stdout. With --case, also written to
#   investigations/<case>/investigation/evidence/raw-collections/<ts>-reverse-image-<stem>/
#
# Requires: curl, jq, base64, shasum or sha256sum

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../../.." && pwd)"

usage() {
  echo "Usage: reverse-image.sh <image-path-or-url> [--case <case-folder>] [--max N] [--raw]" >&2
  exit 1
}

TARGET="${1:-}"
[ -z "$TARGET" ] && usage
shift

CASE=""
MAX=50
RAW=0
WANT_CASE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --case) CASE="${2:-}"; WANT_CASE=1; shift 2 ;;
    --max) MAX="${2:-50}"; shift 2 ;;
    --raw) RAW=1; shift ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage ;;
  esac
done

if [ -z "${GOOGLE_VISION_API_KEY:-}" ]; then
  echo "NotConfigured: GOOGLE_VISION_API_KEY is not set." >&2
  echo "  Enable the Cloud Vision API and create an API key:" >&2
  echo "  https://console.cloud.google.com/apis/library/vision.googleapis.com" >&2
  exit 3
fi

command -v jq >/dev/null 2>&1 || { echo "ERROR: jq not installed" >&2; exit 1; }

sha256_of() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    sha256sum "$1" | awk '{print $1}'
  fi
}

TMP="$(mktemp -d -t revimg-XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

IMAGE_SHA=""
case "$TARGET" in
  http://* | https://*)
    jq -n --arg uri "$TARGET" --argjson max "$MAX" '{
      requests: [{
        image: { source: { imageUri: $uri } },
        features: [
          { type: "WEB_DETECTION", maxResults: $max },
          { type: "LANDMARK_DETECTION", maxResults: 10 }
        ],
        imageContext: { webDetectionParams: { includeGeoResults: true } }
      }]
    }' > "$TMP/req.json"
    ;;
  *)
    if [ ! -f "$TARGET" ]; then
      echo "ERROR: image not found: $TARGET" >&2
      exit 1
    fi
    IMAGE_SHA="$(sha256_of "$TARGET")"
    base64 < "$TARGET" | tr -d '\n' > "$TMP/img.b64"
    jq -n --rawfile content "$TMP/img.b64" --argjson max "$MAX" '{
      requests: [{
        image: { content: $content },
        features: [
          { type: "WEB_DETECTION", maxResults: $max },
          { type: "LANDMARK_DETECTION", maxResults: 10 }
        ],
        imageContext: { webDetectionParams: { includeGeoResults: true } }
      }]
    }' > "$TMP/req.json"
    ;;
esac

HTTP_CODE=$(curl -sS --max-time 60 -o "$TMP/resp.json" -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -X POST "https://vision.googleapis.com/v1/images:annotate?key=${GOOGLE_VISION_API_KEY}" \
  --data-binary @"$TMP/req.json") || HTTP_CODE="000"

if [ "$HTTP_CODE" != "200" ]; then
  echo "ERROR: Cloud Vision returned HTTP $HTTP_CODE" >&2
  jq -r '.error.message // empty' "$TMP/resp.json" 2>/dev/null >&2 || true
  exit 2
fi

API_ERR=$(jq -r '.responses[0].error.message // empty' "$TMP/resp.json")
if [ -n "$API_ERR" ]; then
  echo "ERROR: Cloud Vision: $API_ERR" >&2
  exit 2
fi

NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
jq --arg image "$TARGET" --arg sha "$IMAGE_SHA" --arg ts "$NOW" '
  .responses[0] as $r
  | ($r.webDetection // {}) as $w
  | {
      source: "google-vision",
      tier: "T3",
      note: "Automated reverse-image output. Lead only; cite nothing until captured and crosslinked.",
      queried_at: $ts,
      image: $image,
      image_sha256: $sha,
      best_guess_labels: [($w.bestGuessLabels // [])[] | .label],
      web_entities: [($w.webEntities // [])[] | {description: (.description // ""), score: (.score // 0), entity_id: (.entityId // "")}],
      full_matching_images: [($w.fullMatchingImages // [])[] | .url],
      partial_matching_images: [($w.partialMatchingImages // [])[] | .url],
      pages_with_matching_images: [($w.pagesWithMatchingImages // [])[] | {url, title: (.pageTitle // "")}],
      visually_similar_images: [($w.visuallySimilarImages // [])[] | .url],
      landmarks: [($r.landmarkAnnotations // [])[] | {
        description: (.description // ""),
        score: (.score // 0),
        lat: (.locations[0].latLng.latitude // null),
        lon: (.locations[0].latLng.longitude // null)
      }]
    }' "$TMP/resp.json" > "$TMP/out.json"

if [ "$RAW" = "1" ]; then
  cp "$TMP/resp.json" "$TMP/out.raw.json"
fi

if [ "$WANT_CASE" = "1" ]; then
  # shellcheck source=lib/active_case.sh
  source "$SCRIPT_DIR/lib/active_case.sh"
  resolve_case_dir "$CASE" || exit 1
  STEM="$(basename "$TARGET" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-40)"
  DEST="$CASE_DIR/investigation/evidence/raw-collections/$(date -u +%Y%m%dT%H%M%SZ)-reverse-image-$STEM"
  mkdir -p "$DEST"
  cp "$TMP/out.json" "$DEST/vision.json"
  [ -f "$TMP/out.raw.json" ] && cp "$TMP/out.raw.json" "$DEST/vision.raw.json"
  echo "[reverse-image] saved: $DEST" >&2
fi

if [ "$RAW" = "1" ]; then
  jq -s '{normalized: .[0], raw: .[1]}' "$TMP/out.json" "$TMP/resp.json"
else
  cat "$TMP/out.json"
fi
