#!/bin/bash
# next-ev-id.sh -- return the next EV-NNNN ID for the active (or given) case
# Usage:
#   next-ev-id.sh                       # uses active case
#   next-ev-id.sh <case-folder-name>    # explicit case
#
# Concurrency-safe: uses mkdir-as-atomic-lock (flock is not available on macOS).
# A counter file (.ev-id.counter) is source of truth; a filesystem scan of
# EV-NNNN-* directories is used as a backstop in case the counter is missing
# or lower than observed IDs (e.g., after manual edits).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=lib/active_case.sh
source "$SCRIPT_DIR/lib/active_case.sh"
resolve_case_dir "${1:-}" || exit 1

ITEMS_DIR="$CASE_DIR/investigation/evidence/items"
mkdir -p "$ITEMS_DIR"

LOCK_DIR="$ITEMS_DIR/.ev-id.lock.d"
COUNTER_FILE="$ITEMS_DIR/.ev-id.counter"

acquire_lock() {
  local attempt
  for attempt in $(seq 1 100); do
    if mkdir "$LOCK_DIR" 2>/dev/null; then
      return 0
    fi
    # Stale-lock reclaim: if the lock is older than 30s, remove it and retry.
    if [ -d "$LOCK_DIR" ]; then
      local age
      age=$(($(date +%s) - $(stat -f %m "$LOCK_DIR" 2>/dev/null || echo 0)))
      if [ "$age" -gt 30 ]; then
        rmdir "$LOCK_DIR" 2>/dev/null || true
      fi
    fi
    sleep 0.1
  done
  echo "ERROR: could not acquire EV-ID lock at $LOCK_DIR after 10s" >&2
  exit 1
}

release_lock() {
  rmdir "$LOCK_DIR" 2>/dev/null || true
}

acquire_lock
trap release_lock EXIT

COUNTER_VAL=0
if [ -f "$COUNTER_FILE" ]; then
  COUNTER_VAL=$(tr -d '[:space:]' < "$COUNTER_FILE" || echo 0)
  [ -z "$COUNTER_VAL" ] && COUNTER_VAL=0
fi

SCAN_HIGHEST=$(ls -1 "$ITEMS_DIR" 2>/dev/null \
  | grep -oE '^EV-[0-9]{4}' \
  | sed 's/EV-//' \
  | sort -n \
  | tail -1 || true)
SCAN_VAL=0
if [ -n "${SCAN_HIGHEST:-}" ]; then
  SCAN_VAL=$((10#$SCAN_HIGHEST))
fi

if [ "$SCAN_VAL" -gt "$COUNTER_VAL" ]; then
  CURRENT=$SCAN_VAL
else
  CURRENT=$COUNTER_VAL
fi

NEXT=$((CURRENT + 1))
printf "%d" "$NEXT" > "$COUNTER_FILE"
printf "EV-%04d\n" "$NEXT"
