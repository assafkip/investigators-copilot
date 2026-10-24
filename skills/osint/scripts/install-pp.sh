#!/bin/bash
# install-pp.sh -- install and run the printing-press public-records CLIs used by /q-corp
#
# CLIs come from https://github.com/mvanhorn/printing-press-library (each is a
# standalone Go binary installed with `go install`; nothing is vendored here).
# Covered sources:
#
#   name           binary                 source                              key / env
#   edgar          edgar-pp-cli           SEC EDGAR filings, insiders, XBRL   COMPANY_PP_CONTACT_EMAIL (required UA)
#   sec-edgar      sec-edgar-pp-cli       SEC EDGAR, local SQLite mirror      (none; contact email recommended)
#   company-goat   company-goat-pp-cli    SEC Form D funding + UK Companies   COMPANIES_HOUSE_API_KEY (UK only),
#                                         House + Wikidata + DNS              COMPANY_PP_CONTACT_EMAIL
#   fec            fec-pp-cli             OpenFEC campaign finance            FEC_API_KEY_QUERY_AUTH (DEMO_KEY works, rate-limited)
#   lda-gov        lda-gov-pp-cli         US lobbying disclosures (LDA.gov)   LDA_API_KEY (optional, higher rate)
#   faa-registry   faa-registry-pp-cli    FAA aircraft registry               (none)
#   eu-tenders     eu-tenders-pp-cli      EU public procurement (TED)         (none)
#
# Usage:
#   install-pp.sh list                       # what is installed / missing
#   install-pp.sh install [name ...]         # default: all of the above
#   install-pp.sh run <name> [--case C] -- <cli args...>
#       Runs the CLI and saves stdout + the exact command to
#       investigations/<case>/investigation/evidence/raw-collections/<ts>-pp-<name>/
#       (stdout is also printed). Registry output is T1 for "this record says X";
#       capture any record page you will cite with capture-evidence.sh.
#
# Requires: Go (the library asks for Go 1.26.5+; with GOTOOLCHAIN=auto, the
# default, an older go fetches the needed toolchain on first install).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../../.." && pwd)"
REPO="github.com/mvanhorn/printing-press-library"

# name|module path under the repo|binary
CATALOG="edgar|library/other/edgar/cmd/edgar-pp-cli|edgar-pp-cli
sec-edgar|library/developer-tools/sec-edgar/cmd/sec-edgar-pp-cli|sec-edgar-pp-cli
company-goat|library/developer-tools/company-goat/cmd/company-goat-pp-cli|company-goat-pp-cli
fec|library/other/fec/cmd/fec-pp-cli|fec-pp-cli
lda-gov|library/other/lda-gov/cmd/lda-gov-pp-cli|lda-gov-pp-cli
faa-registry|library/travel/faa-registry/cmd/faa-registry-pp-cli|faa-registry-pp-cli
eu-tenders|library/sales-and-crm/eu-tenders/cmd/eu-tenders-pp-cli|eu-tenders-pp-cli"

usage() {
  sed -n '19,25p' "$0" | sed 's/^# \{0,1\}//' >&2
  exit 1
}

lookup() {
  local name="$1"
  printf '%s\n' "$CATALOG" | awk -F'|' -v n="$name" '$1 == n {print; found=1} END {exit !found}'
}

gobin_dir() {
  local d
  d="$(go env GOBIN 2>/dev/null || true)"
  [ -n "$d" ] || d="$(go env GOPATH 2>/dev/null)/bin"
  printf '%s' "$d"
}

find_bin() {
  local bin="$1"
  if command -v "$bin" >/dev/null 2>&1; then
    command -v "$bin"
  elif command -v go >/dev/null 2>&1 && [ -x "$(gobin_dir)/$bin" ]; then
    printf '%s' "$(gobin_dir)/$bin"
  else
    return 1
  fi
}

cmd_list() {
  printf '%s\n' "$CATALOG" | while IFS='|' read -r name _ bin; do
    if path=$(find_bin "$bin"); then
      printf '%-14s installed  %s\n' "$name" "$path"
    else
      printf '%-14s missing    (install-pp.sh install %s)\n' "$name" "$name"
    fi
  done
}

cmd_install() {
  if ! command -v go >/dev/null 2>&1; then
    echo "NotConfigured: Go is not installed. https://go.dev/dl/ (or brew install go)" >&2
    exit 3
  fi
  local names=("$@") failed=0 line name module bin
  if [ "${#names[@]}" -eq 0 ]; then
    while IFS='|' read -r name _ _; do names+=("$name"); done <<<"$CATALOG"
  fi
  for name in "${names[@]}"; do
    if ! line=$(lookup "$name"); then
      echo "ERROR: unknown CLI: $name (see install-pp.sh list)" >&2
      failed=$((failed + 1))
      continue
    fi
    module="$(printf '%s' "$line" | cut -d'|' -f2)"
    bin="$(printf '%s' "$line" | cut -d'|' -f3)"
    echo "[install] $name -> go install $REPO/$module@latest"
    if go install "$REPO/$module@latest"; then
      echo "          OK: $(gobin_dir)/$bin"
    else
      echo "          FAIL: $name (see go output above)" >&2
      failed=$((failed + 1))
    fi
  done
  case ":$PATH:" in
    *":$(gobin_dir):"*) ;;
    *) echo "[install] note: add $(gobin_dir) to PATH (export PATH=\"\$PATH:$(gobin_dir)\")" ;;
  esac
  [ "$failed" -eq 0 ] || { echo "[install] $failed failure(s)" >&2; exit 1; }
}

cmd_run() {
  local name="${1:-}"; [ -n "$name" ] || usage
  shift
  local case_arg="" want_case=0
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do
    case "$1" in
      --case) case_arg="${2:-}"; want_case=1; shift 2 ;;
      *) echo "ERROR: put CLI arguments after --" >&2; usage ;;
    esac
  done
  [ "${1:-}" = "--" ] && shift
  local line bin path
  line=$(lookup "$name") || { echo "ERROR: unknown CLI: $name" >&2; exit 1; }
  bin="$(printf '%s' "$line" | cut -d'|' -f3)"
  path=$(find_bin "$bin") || { echo "NotConfigured: $bin not installed. install-pp.sh install $name" >&2; exit 3; }

  # shellcheck source=lib/active_case.sh
  source "$SCRIPT_DIR/lib/active_case.sh"
  if [ "$want_case" = "1" ] || [ -f "$WORKSPACE/.active-case" ]; then
    resolve_case_dir "$case_arg" || exit 1
    DEST="$CASE_DIR/investigation/evidence/raw-collections/$(date -u +%Y%m%dT%H%M%SZ)-pp-$name"
  else
    DEST="${TMPDIR:-/tmp}/pp-$name-$(date -u +%Y%m%dT%H%M%SZ)"
  fi
  mkdir -p "$DEST"
  {
    printf 'run_utc: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'binary: %s\n' "$path"
    printf 'command:'; printf ' %q' "$bin" "$@"; printf '\n'
  } > "$DEST/command.txt"
  local rc=0
  "$path" "$@" > "$DEST/output.txt" 2> "$DEST/stderr.txt" || rc=$?
  printf 'exit: %s\n' "$rc" >> "$DEST/command.txt"
  cat "$DEST/output.txt"
  echo "[pp] saved: $DEST (exit $rc)" >&2
  return "$rc"
}

SUB="${1:-}"
[ -n "$SUB" ] || usage
shift
case "$SUB" in
  list) cmd_list ;;
  install) cmd_install "$@" ;;
  run) cmd_run "$@" ;;
  -h | --help) usage ;;
  *) echo "ERROR: unknown subcommand: $SUB" >&2; usage ;;
esac
