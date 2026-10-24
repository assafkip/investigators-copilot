#!/bin/bash
# active_case.sh -- single resolver for the active investigation case.
# Source it, then call: resolve_case_dir "<case-or-empty>"
# Sets CASE and CASE_DIR, or prints an error and returns 1.
# Resolution order: explicit argument, else first line of
# $WORKSPACE/.active-case. WORKSPACE must be set ().
# The value is a case folder name under investigations/, or a path (containing
# "/") to an existing case folder anywhere.
# Extracted 2026-10-10 from three copy-pasted blocks (next-ev-id.sh,
# capture-evidence.sh, extract-intake.py) so they cannot drift apart.

resolve_case_dir() {
  CASE="${1:-}"
  if [ -z "$CASE" ]; then
    if [ -f "$WORKSPACE/.active-case" ]; then
      CASE=$(head -1 "$WORKSPACE/.active-case" | tr -d '[:space:]')
    fi
  fi
  if [ -z "$CASE" ]; then
    echo "ERROR: no active case set and no case argument given" >&2
    return 1
  fi
  # A case may live outside investigations/ (e.g. infohawk/NNN-slug): a value
  # containing "/" that is an existing directory is used as the case folder
  # itself, and CASE becomes its folder name. Ported once here from the local
  # copies in next-ev-id.sh / capture-evidence.sh / ingest-client-document.sh
  # (ASK-2617) so the three cannot drift apart again.
  case "$CASE" in
    */*)
      if [ -d "$CASE" ]; then
        CASE_DIR="$(cd "$CASE" && pwd)"
        CASE="$(basename "$CASE_DIR")"
        return 0
      fi ;;
  esac
  CASE_DIR="$WORKSPACE/investigations/$CASE"
  if [ ! -d "$CASE_DIR" ]; then
    echo "ERROR: case directory not found: $CASE_DIR" >&2
    return 1
  fi
}
