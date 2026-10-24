#!/bin/bash
# crawl.sh -- page fetch / site map / deep crawl to markdown (T3 working material)
#
# Modes:
#   crawl.sh fetch <url> [--case <case>] [--out <dir>]
#       One page -> markdown. Backend order: crawl4ai Docker REST API
#       ($CRAWL4AI_URL), then Scrapling (python, if installed; handles many
#       Cloudflare/anti-bot pages). FAIL-CLOSED: if the body is empty or
#       shorter than $CRAWL_MIN_CHARS (default 200) the run exits 2 and no
#       success is reported (a login wall / challenge page is not content).
#   crawl.sh map <url> [--depth N] [--case <case>] [--out <dir>]
#       URL inventory via katana (projectdiscovery). No content, just URLs.
#   crawl.sh deep <url> [--depth N] [--max-pages N] [--case <case>] [--out <dir>]
#       BFS deep crawl through crawl4ai; one markdown file per page.
#
# Output goes to a run dir: --out <dir>, else with --case
#   investigations/<case>/investigation/evidence/raw-collections/<ts>-crawl-<mode>-<host>/
# else ${TMPDIR:-/tmp}/crawl-<ts>-<mode>-<host>/. The run dir path is printed
# on stdout (last line). Crawled text is NOT evidence: capture any page you
# will cite with capture-evidence.sh.
#
# Env:
#   CRAWL4AI_URL        default http://localhost:11235
#   CRAWL4AI_API_TOKEN  optional bearer token for the crawl4ai server
#   CRAWL_MIN_CHARS     fail-closed threshold for fetch (default 200)
#   CRAWL_TIMEOUT       per-request timeout seconds (default 90)
#
# Install (all optional, each mode reports what is missing):
#   docker run -d -p 11235:11235 --name crawl4ai --shm-size=1g unclecode/crawl4ai:latest
#   pip install "scrapling[fetchers]" && scrapling install
#   go install github.com/projectdiscovery/katana/cmd/katana@latest

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../../.." && pwd)"

CRAWL4AI_URL="${CRAWL4AI_URL:-http://localhost:11235}"
CRAWL_MIN_CHARS="${CRAWL_MIN_CHARS:-200}"
CRAWL_TIMEOUT="${CRAWL_TIMEOUT:-90}"

usage() {
  sed -n '4,15p' "$0" | sed 's/^# \{0,1\}//' >&2
  exit 1
}

MODE="${1:-}"
URL="${2:-}"
[ -z "$MODE" ] || [ -z "$URL" ] && usage
shift 2

case "$MODE" in fetch | map | deep) ;; *) echo "ERROR: unknown mode: $MODE" >&2; usage ;; esac
case "$URL" in http://* | https://*) ;; *) echo "ERROR: url must start with http(s)://" >&2; exit 1 ;; esac

DEPTH=2
MAX_PAGES=25
CASE=""
WANT_CASE=0
OUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --depth) DEPTH="${2:?--depth needs a number}"; shift 2 ;;
    --max-pages) MAX_PAGES="${2:?--max-pages needs a number}"; shift 2 ;;
    --case) CASE="${2:-}"; WANT_CASE=1; shift 2 ;;
    --out) OUT="${2:?--out needs a dir}"; shift 2 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage ;;
  esac
done

HOST="$(printf '%s' "$URL" | sed -E 's#^[a-zA-Z]+://##; s#[/?:].*$##' | tr -c 'A-Za-z0-9.-' '_')"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
if [ -n "$OUT" ]; then
  RUN_DIR="$OUT"
elif [ "$WANT_CASE" = "1" ]; then
  # shellcheck source=lib/active_case.sh
  source "$SCRIPT_DIR/lib/active_case.sh"
  resolve_case_dir "$CASE" || exit 1
  RUN_DIR="$CASE_DIR/investigation/evidence/raw-collections/${TS}-crawl-${MODE}-${HOST}"
else
  RUN_DIR="${TMPDIR:-/tmp}/crawl-${TS}-${MODE}-${HOST}"
fi
mkdir -p "$RUN_DIR"

crawl4ai_up() {
  curl -sS --max-time 5 -o /dev/null -w '%{http_code}' "$CRAWL4AI_URL/health" 2>/dev/null | grep -q '^200$'
}

# crawl4ai_request <json-body-file> <response-file>
crawl4ai_request() {
  local auth=()
  [ -n "${CRAWL4AI_API_TOKEN:-}" ] && auth=(-H "Authorization: Bearer ${CRAWL4AI_API_TOKEN}")
  curl -sS --max-time "$CRAWL_TIMEOUT" -o "$2" -w '%{http_code}' \
    -H 'Content-Type: application/json' ${auth[@]+"${auth[@]}"} \
    -X POST "$CRAWL4AI_URL/crawl" --data-binary @"$1" 2>/dev/null || echo "000"
}

# write_pages <crawl4ai-response> <run-dir> -- splits results into markdown files
# and an index.json; prints the number of pages that cleared the min-chars bar.
write_pages() {
  python3 - "$1" "$2" "$CRAWL_MIN_CHARS" <<'PYEOF'
import hashlib
import json
import sys
from pathlib import Path

resp_path, run_dir, min_chars = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3])
try:
    data = json.loads(Path(resp_path).read_text(encoding="utf-8"))
except ValueError as exc:
    sys.exit(f"ERROR: crawl4ai returned non-JSON: {exc}")

results = data.get("results") if isinstance(data, dict) else data
if results is None and isinstance(data, dict) and "markdown" in data:
    results = [data]
results = results or []


def markdown_of(item):
    md = item.get("markdown")
    if isinstance(md, dict):
        return md.get("fit_markdown") or md.get("raw_markdown") or ""
    return md or item.get("cleaned_html") or ""


index = []
kept = 0
for n, item in enumerate(results, start=1):
    text = markdown_of(item).strip()
    url = item.get("url", "")
    ok = bool(item.get("success", True)) and len(text) >= min_chars
    name = f"page-{n:03d}.md"
    if ok:
        (run_dir / name).write_text(f"<!-- source: {url} -->\n\n{text}\n", encoding="utf-8")
        kept += 1
    index.append({
        "n": n, "url": url, "file": name if ok else None, "chars": len(text),
        "status_code": item.get("status_code"), "ok": ok,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if ok else None,
    })
(run_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
print(kept)
PYEOF
}

# scrapling_fetch <url> <out-md> -- returns 0 on a body, 3 when not installed
scrapling_fetch() {
  python3 - "$1" "$2" <<'PYEOF'
import re
import sys

url, out = sys.argv[1], sys.argv[2]
try:
    import scrapling  # noqa: F401
except ImportError:
    sys.exit(3)

page = None
errors = []
try:
    from scrapling.fetchers import StealthyFetcher
    page = StealthyFetcher.fetch(url, headless=True, network_idle=True)
except Exception as exc:  # stealth browser not installed or blocked
    errors.append(f"stealthy: {exc}")
if page is None:
    try:
        from scrapling.fetchers import Fetcher
        page = Fetcher.get(url, stealthy_headers=True)
    except Exception as exc:
        errors.append(f"fetcher: {exc}")
if page is None:
    sys.exit("scrapling failed: " + "; ".join(errors))

html = ""
for attr in ("html_content", "body", "text"):
    val = getattr(page, attr, None)
    if isinstance(val, bytes):
        val = val.decode("utf-8", "replace")
    if isinstance(val, str) and val.strip():
        html = val
        break
try:
    from markdownify import markdownify
    text = markdownify(html)
except ImportError:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
with open(out, "w", encoding="utf-8") as fh:
    fh.write(text.strip() + "\n")
PYEOF
}

write_meta() {
  jq -n --arg mode "$MODE" --arg url "$URL" --arg backend "$1" --arg ts "$TS" \
    --arg status "$2" --argjson pages "${3:-0}" \
    '{mode: $mode, url: $url, backend: $backend, run_utc: $ts, status: $status,
      pages: $pages, tier: "T3",
      note: "Crawled text is working material. Capture cited pages with capture-evidence.sh."}' \
    > "$RUN_DIR/meta.json"
}

fail_closed() {
  write_meta "$1" "FAIL_EMPTY" 0
  echo "FAIL-CLOSED: $2" >&2
  echo "  Treat as a blocked extraction (login wall / challenge / empty page): stop and tell the founder." >&2
  exit 2
}

do_fetch() {
  local backend="none" chars=0
  if crawl4ai_up; then
    backend="crawl4ai"
    jq -n --arg url "$URL" '{urls: [$url], crawler_config: {type: "CrawlerRunConfig", params: {cache_mode: "bypass"}}}' \
      > "$RUN_DIR/.request.json"
    local code
    code="$(crawl4ai_request "$RUN_DIR/.request.json" "$RUN_DIR/.response.json")"
    if [ "$code" = "200" ]; then
      local kept
      kept="$(write_pages "$RUN_DIR/.response.json" "$RUN_DIR")"
      if [ "$kept" -ge 1 ]; then
        mv "$RUN_DIR/page-001.md" "$RUN_DIR/page.md"
        rm -f "$RUN_DIR/.request.json" "$RUN_DIR/.response.json"
        write_meta crawl4ai OK 1
        echo "$RUN_DIR"
        return 0
      fi
      echo "[crawl] crawl4ai body under ${CRAWL_MIN_CHARS} chars, trying Scrapling" >&2
    else
      echo "[crawl] crawl4ai HTTP $code, trying Scrapling" >&2
    fi
    rm -f "$RUN_DIR/.request.json" "$RUN_DIR/.response.json" "$RUN_DIR/index.json"
  else
    echo "[crawl] crawl4ai not reachable at $CRAWL4AI_URL, trying Scrapling" >&2
  fi

  local rc=0
  scrapling_fetch "$URL" "$RUN_DIR/page.md" || rc=$?
  if [ "$rc" = "3" ]; then
    [ "$backend" = "none" ] && {
      write_meta none NOT_CONFIGURED 0
      echo "NotConfigured: no crawl backend. Start crawl4ai (docker run -d -p 11235:11235 unclecode/crawl4ai:latest)" >&2
      echo "  or pip install \"scrapling[fetchers]\" && scrapling install" >&2
      exit 3
    }
    fail_closed crawl4ai "crawl4ai returned no usable body and Scrapling is not installed"
  fi
  [ "$rc" = "0" ] || fail_closed scrapling "Scrapling fetch failed (exit $rc)"
  chars="$(wc -c < "$RUN_DIR/page.md" | tr -d ' ')"
  if [ "$chars" -lt "$CRAWL_MIN_CHARS" ]; then
    rm -f "$RUN_DIR/page.md"
    fail_closed scrapling "body is $chars chars (< $CRAWL_MIN_CHARS)"
  fi
  write_meta scrapling OK 1
  echo "$RUN_DIR"
}

do_map() {
  if ! command -v katana >/dev/null 2>&1; then
    write_meta katana NOT_CONFIGURED 0
    echo "NotConfigured: katana not installed. go install github.com/projectdiscovery/katana/cmd/katana@latest" >&2
    exit 3
  fi
  katana -u "$URL" -d "$DEPTH" -silent -jc -timeout 15 -ct "${CRAWL_TIMEOUT}s" 2>/dev/null \
    | sort -u > "$RUN_DIR/urls.txt" || true
  local count
  count="$(wc -l < "$RUN_DIR/urls.txt" | tr -d ' ')"
  [ "$count" -gt 0 ] || fail_closed katana "katana returned no URLs"
  write_meta katana OK "$count"
  echo "[crawl] $count URLs -> $RUN_DIR/urls.txt" >&2
  echo "$RUN_DIR"
}

do_deep() {
  if ! crawl4ai_up; then
    write_meta crawl4ai NOT_CONFIGURED 0
    echo "NotConfigured: deep mode needs crawl4ai at $CRAWL4AI_URL" >&2
    echo "  docker run -d -p 11235:11235 --name crawl4ai --shm-size=1g unclecode/crawl4ai:latest" >&2
    exit 3
  fi
  jq -n --arg url "$URL" --argjson depth "$DEPTH" --argjson maxp "$MAX_PAGES" '{
    urls: [$url],
    crawler_config: {type: "CrawlerRunConfig", params: {
      cache_mode: "bypass",
      deep_crawl_strategy: {type: "BFSDeepCrawlStrategy",
        params: {max_depth: $depth, max_pages: $maxp, include_external: false}}
    }}
  }' > "$RUN_DIR/.request.json"
  local code kept
  code="$(crawl4ai_request "$RUN_DIR/.request.json" "$RUN_DIR/.response.json")"
  [ "$code" = "200" ] || fail_closed crawl4ai "crawl4ai deep crawl HTTP $code"
  kept="$(write_pages "$RUN_DIR/.response.json" "$RUN_DIR")"
  rm -f "$RUN_DIR/.request.json" "$RUN_DIR/.response.json"
  [ "$kept" -ge 1 ] || fail_closed crawl4ai "deep crawl produced no page over ${CRAWL_MIN_CHARS} chars"
  write_meta crawl4ai OK "$kept"
  echo "[crawl] $kept pages -> $RUN_DIR" >&2
  echo "$RUN_DIR"
}

command -v jq >/dev/null 2>&1 || { echo "ERROR: jq not installed" >&2; exit 1; }

case "$MODE" in
  fetch) do_fetch ;;
  map) do_map ;;
  deep) do_deep ;;
esac
