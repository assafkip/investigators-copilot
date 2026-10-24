#!/bin/bash
# setup-tools.sh -- install the OPTIONAL tools behind osint-tool.py adapters and the
# Phase 2-7 scripts. Every tool is optional: adapters report "missing bin:X" until it
# is installed, and nothing here is required for the keyless core.
#
# Usage:
#   setup-tools.sh --list                    # catalog + installed/missing state
#   setup-tools.sh --only maigret,holehe     # install the named tools
#   setup-tools.sh --all                     # install every non-docker tool
#   setup-tools.sh --docker [svc,...]        # start docker services (default: list them)
#   add --dry-run to print the commands without running them
#
# Rules:
#   - Idempotent: a tool whose binary/import is already present is skipped.
#   - CLIs go through pipx (isolated venvs); falls back to `python3 -m pip install --user`.
#   - Python libraries (imported by our scripts) go into python3's user site.
#   - System packages are NEVER installed here: the apt/brew command is printed.
#   - A failed tool is reported and the rest continue; exit 1 if any failed.
#   - License: GPL/AGPL tools (holehe, ghunt, gitrecon, theHarvester, bbot) are only
#     ever run as subprocesses by the adapters, never imported.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
QI_DIR="$(cd "$SKILLS_DIR/.." && pwd)"
COMPOSE_FILE="$QI_DIR/tools/docker-compose.yml"
GITRECON_HOME="${GITRECON_HOME:-$HOME/.local/share/gitrecon}"
SHIM_DIR="${SHIM_DIR:-$HOME/.local/bin}"
PY="${PYTHON:-python3}"

# name|kind|install spec|presence check|note
#   kind: pipx (CLI), pip (library), go, cargo, sys (hint only), custom
#   check: bin:<name> | py:<module> | fn:<function>
CATALOG='maigret|pipx|maigret|bin:maigret|username sweep (adapter maigret)
sherlock|pipx|sherlock-project|bin:sherlock|username sweep (adapter sherlock)
user-scanner|pipx|user-scanner|bin:user-scanner|handle/email registration check (adapter user_scanner)
holehe|pipx|holehe|bin:holehe|email account enumeration, GPL-3.0 subprocess (adapter holehe)
ghunt|pipx|ghunt|bin:ghunt|Google account lookup, AGPL-3.0 subprocess; then run: ghunt login
telegram-phone-number-checker|pipx|telegram-phone-number-checker|bin:telegram-phone-number-checker|needs API_ID API_HASH PHONE_NUMBER (adapter telegram_phone)
dnstwist|pipx|dnstwist|bin:dnstwist|typosquat candidates (adapter typosquat)
theharvester|pipx|git+https://github.com/laramies/theHarvester|bin:theHarvester|emails/hosts, GPL-2.0 subprocess (adapter theharvester)
bbot|pipx|bbot|bin:bbot|recursive recon, AGPL-3.0 subprocess (adapter bbot)
yt-dlp|pipx|yt-dlp|bin:yt-dlp|capture-evidence.sh --social video
gallery-dl|pipx|gallery-dl|bin:gallery-dl|capture-evidence.sh --social images
auto-archiver|pipx|auto-archiver|bin:auto-archiver|capture-evidence.sh --social (needs AUTO_ARCHIVER_CONFIG)
phonenumbers|pip|phonenumbers|py:phonenumbers|adapter phone (offline libphonenumber)
dnspython|pip|dnspython|py:dns|DNS resolution in adapters
openpyxl|pip|openpyxl|py:openpyxl|XLSX intake + exports
splink|pip|splink|py:splink|resolve-entities.py probabilistic matching
presidio|pip|presidio-analyzer presidio-anonymizer|py:presidio_anonymizer|redact-pii.py
gliner|pip|gliner|py:gliner|extract-intake.py --ner gliner (weights download once)
langextract|pip|langextract|py:langextract|extract-intake.py --ner langextract (SENDS TEXT TO GEMINI)
spacy|pip|spacy|py:spacy|extract-intake.py --ner spacy
spacy-model|custom|en_core_web_lg|fn:have_spacy_model|spaCy English model for --ner spacy
followthemoney|pip|followthemoney|py:followthemoney|resolve-entities.py --ftm; needs ICU first (apt: pkg-config libicu-dev / brew: icu4c pkg-config)
stix2|pip|stix2|py:stix2|optional STIX bundle validation (tests/test_export_intel.py)
shadowfinder|pip|shadowfinder|py:shadowfinder|shadowfinder.sh (geo-sleuth)
scrapling|pip|scrapling[fetchers]|py:scrapling|crawl.sh fallback fetcher; then runs: scrapling install
katana|go|github.com/projectdiscovery/katana/cmd/katana@latest|bin:katana|crawl.sh --spider
pd-httpx|go|github.com/projectdiscovery/httpx/cmd/httpx@latest|fn:have_pd_httpx|adapter wappalyzer; set PD_HTTPX_BIN if python httpx shadows it
c2patool|cargo|c2patool|bin:c2patool|verification skill (C2PA provenance)
gitrecon|custom|https://github.com/GONZOsint/gitrecon|bin:gitrecon|GPL-3.0 subprocess; clone + shim (adapter gitrecon)
printing-press|custom|install-pp.sh install|fn:have_pp|public-records CLIs for /q-corp
telegram-harvest|custom|skills/telegram-harvest/setup.sh|fn:have_tgh|telegram-harvest venv + models
exiftool|sys|apt:libimage-exiftool-perl brew:exiftool|bin:exiftool|EXIF in extract-intake.py + capture-evidence.sh
zbar|sys|apt:zbar-tools brew:zbar|bin:zbarimg|QR decode in capture-evidence.sh
whois|sys|apt:whois brew:whois|bin:whois|whois fallback
dig|sys|apt:dnsutils brew:bind|bin:dig|DNS fallback
git|sys|apt:git brew:git|bin:git|adapter git_osint, gitrecon clone
docker|sys|apt:docker.io brew:--cask docker|bin:docker|optional services (--docker)'

DOCKER_SERVICES='crawl4ai|crawl.sh primary engine, http://localhost:11235 (CRAWL4AI_URL)
changedetection|watch.py, http://localhost:5000 (CHANGEDETECTION_URL + CHANGEDETECTION_API_KEY)
archivebox|capture-evidence.sh --archivebox, http://localhost:8010 (ARCHIVEBOX_URL + ARCHIVEBOX_API_KEY)
spiderfoot|adapter spiderfoot, http://localhost:5001 (SPIDERFOOT_URL)
yente|adapter opensanctions local, http://localhost:8000 (YENTE_URL); needs ~4GB RAM'

DRY=0
FAILED=()

say()  { printf '%s\n' "$*"; }
run()  { say "  + $*"; [ "$DRY" = 1 ] && return 0; "$@"; }

have_bin() { command -v "$1" >/dev/null 2>&1; }
have_py()  { "$PY" -c "import $1" >/dev/null 2>&1; }
have_spacy_model() { "$PY" -c "import spacy; spacy.load('en_core_web_lg')" >/dev/null 2>&1; }
have_pd_httpx() {
  local p="${PD_HTTPX_BIN:-}"
  [ -n "$p" ] && [ -x "$p" ] && return 0
  have_bin go && [ -x "$(go env GOPATH 2>/dev/null)/bin/httpx" ]
}
have_pp()  { have_bin edgar-pp-cli || have_bin company-goat-pp-cli; }
have_tgh() { [ -x "$SKILLS_DIR/telegram-harvest/.venv/bin/python" ]; }

present() {
  local check="$1"
  case "$check" in
    bin:*) have_bin "${check#bin:}" ;;
    py:*)  have_py "${check#py:}" ;;
    fn:*)  "${check#fn:}" ;;
    *)     return 1 ;;
  esac
}

field() { printf '%s' "$1" | cut -d'|' -f"$2"; }

sys_hint() {
  local spec="$1" apt brew
  apt="$(printf '%s' "$spec" | tr ' ' '\n' | sed -n 's/^apt://p')"
  brew="$(printf '%s\n' "$spec" | sed -n 's/.*brew://p')"
  say "  system package -- not installed by this script. Run one of:"
  [ -n "$apt" ] && say "    sudo apt-get install -y $apt"
  [ -n "$brew" ] && say "    brew install $brew"
  return 0
}

install_pipx() {
  local spec="$1"
  if have_bin pipx; then
    run pipx install "$spec"
  elif have_bin uv; then
    # uv tool gives the same isolated venv as pipx. pip --user into a distro
    # Python breaks setup.py builds (Debian's patched distutils: install_layout),
    # which failed sherlock (via stem) and holehe on first real run (ASK-2613).
    say "  (pipx not found: using uv tool install)"
    run uv tool install "$spec"
  else
    say "  (pipx/uv not found: falling back to pip --user; install pipx for isolated CLIs)"
    run "$PY" -m pip install --user "$spec"
  fi
}

install_custom() {
  local name="$1"
  case "$name" in
    gitrecon)
      have_bin git || { say "  git is required (see: setup-tools.sh --only git)"; return 1; }
      if [ -d "$GITRECON_HOME/.git" ]; then
        run git -C "$GITRECON_HOME" pull --ff-only
      else
        run git clone --depth 1 https://github.com/GONZOsint/gitrecon "$GITRECON_HOME"
      fi
      run "$PY" -m venv "$GITRECON_HOME/.venv"
      run "$GITRECON_HOME/.venv/bin/pip" install -r "$GITRECON_HOME/requirements.txt"
      run mkdir -p "$SHIM_DIR"
      say "  + write shim $SHIM_DIR/gitrecon"
      if [ "$DRY" != 1 ]; then
        printf '#!/bin/bash\n# shim written by setup-tools.sh\ncd "%s" && exec "%s/.venv/bin/python" gitrecon.py "$@"\n' \
          "$GITRECON_HOME" "$GITRECON_HOME" > "$SHIM_DIR/gitrecon"
        chmod +x "$SHIM_DIR/gitrecon"
      fi
      case ":$PATH:" in *":$SHIM_DIR:"*) ;; *) say "  note: add $SHIM_DIR to PATH" ;; esac
      ;;
    printing-press)
      run bash "$SCRIPT_DIR/install-pp.sh" install ;;
    telegram-harvest)
      run bash "$SKILLS_DIR/telegram-harvest/setup.sh" ;;
    spacy-model)
      have_py spacy || { say "  spacy is required first (setup-tools.sh --only spacy)"; return 1; }
      run "$PY" -m spacy download en_core_web_lg ;;
    *) say "  unknown custom tool: $name"; return 1 ;;
  esac
}

install_one() {
  local line name kind spec check note
  line="$(printf '%s\n' "$CATALOG" | awk -F'|' -v n="$1" '$1==n')"
  if [ -z "$line" ]; then
    say "[$1] unknown tool (see --list)"; FAILED+=("$1"); return 0
  fi
  name="$(field "$line" 1)"; kind="$(field "$line" 2)"; spec="$(field "$line" 3)"
  check="$(field "$line" 4)"; note="$(field "$line" 5)"
  say "[$name] $note"
  if present "$check"; then say "  already installed -- skip"; return 0; fi
  local rc=0
  case "$kind" in
    pipx)  install_pipx "$spec" || rc=$? ;;
    pip)   # shellcheck disable=SC2086
           run "$PY" -m pip install --user $spec || rc=$?
           if [ "$rc" = 0 ] && [ "$name" = scrapling ]; then run scrapling install || rc=$?; fi ;;
    go)    if have_bin go; then run go install "$spec" || rc=$?; else say "  go not found: https://go.dev/dl/"; rc=1; fi
           if [ "$rc" = 0 ] && [ "$name" = pd-httpx ]; then
             say "  note: export PD_HTTPX_BIN=\"\$(go env GOPATH)/bin/httpx\" if the Python httpx CLI is first on PATH"
           fi ;;
    cargo) if have_bin cargo; then run cargo install "$spec" || rc=$?; else say "  cargo not found: https://rustup.rs (or a release binary from github.com/contentauth/c2patool)"; rc=1; fi ;;
    sys)   sys_hint "$spec"; return 0 ;;
    custom) install_custom "$name" || rc=$? ;;
  esac
  if [ "$rc" != 0 ]; then say "  FAILED (exit $rc) -- continuing"; FAILED+=("$name"); fi
  if [ "$rc" = 0 ] && [ "$name" = ghunt ]; then say "  next: ghunt login   (interactive, one time)"; fi
  return 0
}

list_tools() {
  printf '%-30s %-6s %-9s %s\n' TOOL KIND STATE NOTE
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    local name kind check note state
    name="$(field "$line" 1)"; kind="$(field "$line" 2)"; check="$(field "$line" 4)"; note="$(field "$line" 5)"
    if present "$check"; then state=installed; else state=missing; fi
    printf '%-30s %-6s %-9s %s\n' "$name" "$kind" "$state" "$note"
  done <<< "$CATALOG"
  say ""
  say "Docker services (setup-tools.sh --docker <svc>[,<svc>], file: tools/docker-compose.yml):"
  while IFS='|' read -r svc note; do printf '  %-16s %s\n' "$svc" "$note"; done <<< "$DOCKER_SERVICES"
  say "  timesketch       not in compose (too large): https://github.com/google/timesketch/tree/master/docker"
}

start_docker() {
  local svcs="$1"
  if [ -z "$svcs" ]; then
    say "Pick services: setup-tools.sh --docker crawl4ai,changedetection"
    while IFS='|' read -r svc note; do printf '  %-16s %s\n' "$svc" "$note"; done <<< "$DOCKER_SERVICES"
    return 0
  fi
  have_bin docker || { say "docker not found (setup-tools.sh --only docker prints the install command)"; FAILED+=(docker); return 0; }
  local args=() s
  IFS=',' read -ra list <<< "$svcs"
  for s in "${list[@]}"; do
    printf '%s\n' "$DOCKER_SERVICES" | grep -q "^$s|" || { say "unknown service: $s"; FAILED+=("$s"); continue; }
    args+=(--profile "$s")
  done
  [ "${#args[@]}" -eq 0 ] && return 0
  run docker compose -f "$COMPOSE_FILE" "${args[@]}" up -d || FAILED+=("docker:$svcs")
}

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

[ $# -eq 0 ] && usage 0
MODE=""; ONLY=""; DOCKER_SVCS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --list) MODE=list; shift ;;
    --all) MODE=all; shift ;;
    --only) MODE=only; ONLY="${2:?--only needs a name list}"; shift 2 ;;
    --docker)
      MODE=docker
      if [ $# -gt 1 ] && [ "${2#--}" = "$2" ]; then DOCKER_SVCS="$2"; shift 2; else shift; fi ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) usage 0 ;;
    *) say "unknown argument: $1"; usage 2 ;;
  esac
done

case "$MODE" in
  list) list_tools ;;
  all)
    while IFS= read -r line; do
      [ -z "$line" ] && continue
      install_one "$(field "$line" 1)"
    done <<< "$CATALOG" ;;
  only)
    IFS=',' read -ra names <<< "$ONLY"
    for n in "${names[@]}"; do install_one "$n"; done ;;
  docker) start_docker "$DOCKER_SVCS" ;;
  *) usage 2 ;;
esac

if [ "${#FAILED[@]}" -gt 0 ]; then
  say ""; say "Failed: ${FAILED[*]}"; exit 1
fi
[ "$MODE" = list ] || { say ""; say "Done. Check with: python3 $SCRIPT_DIR/osint-tool.py --list"; }
