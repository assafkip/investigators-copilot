#!/bin/bash
set -euo pipefail
# OSINT Toolkit Self-Diagnostic
# Run before starting any research to check available tools
# Usage: ./diagnose.sh

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="$SKILL_DIR/scripts"
WORKSPACE="$(cd "$SKILL_DIR/../.." && pwd)"

echo "=== OSINT TOOLKIT DIAGNOSTIC ==="
echo ""

# 1. API Tokens (env or file)
echo "📡 API Tokens:"
if [ -n "${APIFY_API_TOKEN:-}" ]; then
  echo "  ✅ APIFY_API_TOKEN (env)"
elif [ -f "$WORKSPACE/scripts/apify-api-token.txt" ]; then
  echo "  ✅ APIFY_API_TOKEN (file: scripts/apify-api-token.txt)"
else
  echo "  ❌ APIFY_API_TOKEN"
fi

if [ -n "${JINA_API_KEY:-}" ]; then
  echo "  ✅ JINA_API_KEY (env)"
elif [ -f "$WORKSPACE/scripts/jina-api-key.txt" ]; then
  echo "  ✅ JINA_API_KEY (file: scripts/jina-api-key.txt)"
else
  echo "  ❌ JINA_API_KEY"
fi

if [ -n "${PERPLEXITY_API_KEY:-}" ]; then
  echo "  ✅ PERPLEXITY_API_KEY (env)"
else
  echo "  ❌ PERPLEXITY_API_KEY"
fi

if [ -n "${PARALLEL_API_KEY:-}" ]; then
  echo "  ✅ PARALLEL_API_KEY (env)"
elif [ -f "$WORKSPACE/scripts/parallel-api-key.txt" ]; then
  echo "  ✅ PARALLEL_API_KEY (file: scripts/parallel-api-key.txt)"
else
  echo "  ❌ PARALLEL_API_KEY"
fi

if [ -n "${EXA_API_KEY:-}" ]; then
  echo "  ✅ EXA_API_KEY (env)"
else
  echo "  ⚠️  EXA_API_KEY (not set — exa.sh won't work)"
fi

if [ -n "${TAVILY_API_KEY:-}" ]; then
  echo "  ✅ TAVILY_API_KEY (env)"
else
  echo "  ❌ TAVILY_API_KEY"
fi

if [ -n "${BRIGHTDATA_MCP_URL:-}" ]; then
  echo "  ✅ BRIGHTDATA_MCP_URL (env)"
elif [ -f "$WORKSPACE/scripts/brightdata-mcp-url.txt" ]; then
  echo "  ✅ BRIGHTDATA_MCP_URL (file: scripts/brightdata-mcp-url.txt)"
else
  echo "  ❌ BRIGHTDATA_MCP_URL"
fi
echo ""

# 1b. Enrichment adapter keys + service URLs (all optional; keyless paths work without them)
# key_line VAR "what it unlocks" -- ✅ set, ⚪ unset (optional)
key_line() {
  if [ -n "${!1:-}" ]; then echo "  ✅ $1 ($2)"; else echo "  ⚪ $1 -- optional: $2"; fi
}
echo "🔑 Enrichment keys (osint-tool.py adapters, optional):"
key_line SHODAN_API_KEY "shodan host; keyless InternetDB fallback"
key_line URLSCAN_API_KEY "urlscan search quota"
key_line OTX_API_KEY "otx pulses + passive DNS"
key_line GREYNOISE_API_KEY "greynoise, ioc-reputation.py"
key_line ABUSEIPDB_API_KEY "abuseipdb, ioc-reputation.py"
key_line VT_API_KEY "ioc-reputation.py VirusTotal"
key_line CERTSPOTTER_API_KEY "certspotter quota"
key_line OPENCORPORATES_API_KEY "opencorporates registry"
key_line OPENSANCTIONS_API_KEY "opensanctions hosted API"
key_line YENTE_URL "opensanctions via local yente"
key_line COURTLISTENER_API_TOKEN "courtlistener higher limits"
key_line ETHERSCAN_API_KEY "wallet eth/erc20"
key_line TRONGRID_API_KEY "tron quota"
key_line GITHUB_TOKEN "github_user, git_osint, rate limits"
key_line GITLAB_TOKEN "gitlab_user"
key_line API_ID "telegram_phone (with API_HASH, PHONE_NUMBER)"
key_line API_HASH "telegram_phone"
key_line PHONE_NUMBER "telegram_phone"
key_line COMPANIES_HOUSE_API_KEY "/q-corp company-goat UK"
key_line COMPANY_PP_CONTACT_EMAIL "/q-corp SEC user-agent"
key_line FEC_API_KEY_QUERY_AUTH "/q-corp fec (DEMO_KEY works)"
key_line LDA_API_KEY "/q-corp lda-gov higher rate"
key_line GOOGLE_VISION_API_KEY "/q-face + reverse-image Vision backend"
key_line SEARCH4FACES_API_KEY "/q-face Search4faces"
key_line FACECHECK_API_KEY "/q-face FaceCheck.ID API"
if [ -n "${LANGEXTRACT_API_KEY:-}" ] || [ -n "${GEMINI_API_KEY:-}" ]; then
  echo "  ✅ LANGEXTRACT_API_KEY|GEMINI_API_KEY (extract-intake --ner langextract, SENDS TEXT TO GEMINI)"
else
  echo "  ⚪ LANGEXTRACT_API_KEY|GEMINI_API_KEY -- optional: extract-intake --ner langextract"
fi
echo ""
echo "🐳 Optional services (tools/docker-compose.yml):"
key_line CRAWL4AI_URL "crawl.sh; default http://localhost:11235"
key_line CHANGEDETECTION_URL "watch.py"
key_line CHANGEDETECTION_API_KEY "watch.py"
key_line ARCHIVEBOX_URL "capture-evidence.sh --archivebox"
key_line ARCHIVEBOX_API_KEY "capture-evidence.sh --archivebox"
key_line SPIDERFOOT_URL "spiderfoot REST mode"
key_line AUTO_ARCHIVER_CONFIG "capture-evidence.sh --social auto-archiver"
echo ""

# 2. CLI tools
echo "🔧 CLI Tools:"
command -v mcporter &>/dev/null && echo "  ✅ mcporter" || echo "  ❌ mcporter"
[ -f ~/.local/node_modules/.bin/mcpc ] && echo "  ✅ mcpc (Apify actor discovery)" || echo "  ❌ mcpc (npm i @apify/mcpc)"
command -v jq &>/dev/null && echo "  ✅ jq" || echo "  ❌ jq"
command -v curl &>/dev/null && echo "  ✅ curl" || echo "  ❌ curl"
if command -v node &>/dev/null; then
  NODE_V=$(node -v 2>/dev/null)
  NODE_MAJOR=$(echo "$NODE_V" | sed 's/v//' | cut -d. -f1)
  if [ "$NODE_MAJOR" -ge 18 ]; then
    echo "  ✅ node $NODE_V (run_actor.js compatible)"
  else
    echo "  ⚠️  node $NODE_V (need 18+ for run_actor.js)"
  fi
else
  echo "  ❌ node (required for run_actor.js)"
fi
[ -f "$SKILL_DIR/scripts/run_actor.js" ] && echo "  ✅ run_actor.js (embedded, 55+ actors)" || echo "  ❌ run_actor.js (missing from skill)"
[ -f "$SKILL_DIR/scripts/run-actor.sh" ] && echo "  ✅ run-actor.sh (bash wrapper)" || echo "  ❌ run-actor.sh"
echo ""

# 2b. Optional binaries (install: scripts/setup-tools.sh --only <name>; --list for all)
echo "🧰 Optional tools (setup-tools.sh --list):"
for bin in maigret sherlock user-scanner holehe ghunt telegram-phone-number-checker gitrecon \
           dnstwist theHarvester bbot sf.py yt-dlp gallery-dl auto-archiver katana c2patool \
           exiftool zbarimg whois dig git docker pipx go edgar-pp-cli company-goat-pp-cli; do
  command -v "$bin" &>/dev/null && echo "  ✅ $bin" || echo "  ⚪ $bin"
done
if [ -n "${PD_HTTPX_BIN:-}" ] && [ -x "${PD_HTTPX_BIN}" ]; then
  echo "  ✅ projectdiscovery httpx (PD_HTTPX_BIN)"
elif command -v go &>/dev/null && [ -x "$(go env GOPATH 2>/dev/null)/bin/httpx" ]; then
  echo "  ✅ projectdiscovery httpx (\$GOPATH/bin)"
else
  echo "  ⚪ projectdiscovery httpx (wappalyzer adapter)"
fi
PY_LIBS_OUT=$(python3 - <<'PYEOF' 2>/dev/null || true
import importlib.util
mods = [("phonenumbers", "phonenumbers"), ("dns", "dnspython"), ("openpyxl", "openpyxl"),
        ("splink", "splink"), ("presidio_anonymizer", "presidio"), ("gliner", "gliner"),
        ("langextract", "langextract"), ("spacy", "spacy"), ("followthemoney", "followthemoney"),
        ("stix2", "stix2"), ("shadowfinder", "shadowfinder"), ("scrapling", "scrapling")]
for mod, name in mods:
    ok = importlib.util.find_spec(mod) is not None
    print(("  ✅ py:" if ok else "  ⚪ py:") + name)
PYEOF
)
[ -n "$PY_LIBS_OUT" ] && echo "$PY_LIBS_OUT"
[ -x "$SKILL_DIR/../telegram-harvest/.venv/bin/python" ] && echo "  ✅ telegram-harvest venv" || echo "  ⚪ telegram-harvest venv (skills/telegram-harvest/setup.sh)"
echo ""

# 3. Internal Intelligence Tools
echo "📱 Internal Intelligence:"
if [ -f "$WORKSPACE/skills/telegram/scripts/tg.py" ]; then
  echo "  ✅ tg.py (Telegram history/search)"
else
  echo "  ❌ tg.py (no Telegram access)"
fi

if command -v himalaya &>/dev/null || [ -f ~/.local/bin/himalaya ]; then
  echo "  ✅ himalaya (email search)"
else
  echo "  ❌ himalaya (no email access)"
fi

if [ -d "$WORKSPACE/vault/crm" ]; then
  VAULT_COUNT=$(find "$WORKSPACE/vault/crm" -name "*.md" 2>/dev/null | wc -l)
  echo "  ✅ vault/crm ($VAULT_COUNT cards)"
else
  echo "  ❌ vault/crm (no CRM vault)"
fi

if [ -f "$WORKSPACE/scripts/twitter.py" ]; then
  echo "  ✅ twitter.py (X/Twitter reader)"
else
  echo "  ❌ twitter.py (no Twitter access)"
fi
echo ""

# 4. MCP servers
echo "🔌 MCP Servers:"
if command -v mcporter &>/dev/null; then
  MCPORTER_CONFIG="${MCPORTER_CONFIG:-./config/mcporter.json}"
  if [ -f "$MCPORTER_CONFIG" ]; then
    MCPORTER_CONFIG="$MCPORTER_CONFIG" mcporter list 2>/dev/null | grep -E "^[a-z]" | while read -r server; do
      echo "  ✅ $server"
    done
  else
    echo "  ⚠️  mcporter config not found at $MCPORTER_CONFIG"
  fi
else
  echo "  ⚠️  mcporter not installed (npm i -g mcporter)"
fi
echo ""

# 5. Capability summary
echo "📊 Capabilities:"
([ -n "${APIFY_API_TOKEN:-}" ] || [ -f "$WORKSPACE/scripts/apify-api-token.txt" ]) && echo "  LinkedIn scraping (Apify): ✅" || echo "  LinkedIn scraping (Apify): ❌"
([ -n "${APIFY_API_TOKEN:-}" ] || [ -f "$WORKSPACE/scripts/apify-api-token.txt" ]) && echo "  Instagram scraping (Apify): ✅" || echo "  Instagram scraping (Apify): ❌"
([ -n "${APIFY_API_TOKEN:-}" ] || [ -f "$WORKSPACE/scripts/apify-api-token.txt" ]) && echo "  TikTok scraping (Apify clockworks): ✅" || echo "  TikTok scraping: ❌"
([ -n "${APIFY_API_TOKEN:-}" ] || [ -f "$WORKSPACE/scripts/apify-api-token.txt" ]) && echo "  YouTube scraping (Apify streamers): ✅" || echo "  YouTube scraping: ❌"
([ -n "${APIFY_API_TOKEN:-}" ] || [ -f "$WORKSPACE/scripts/apify-api-token.txt" ]) && echo "  Contact enrichment (Apify): ✅" || echo "  Contact enrichment: ❌"
([ -n "${APIFY_API_TOKEN:-}" ] || [ -f "$WORKSPACE/scripts/apify-api-token.txt" ]) && echo "  Google Maps (Apify): ✅" || echo "  Google Maps: ❌"
([ -n "${BRIGHTDATA_MCP_URL:-}" ] || [ -f "$WORKSPACE/scripts/brightdata-mcp-url.txt" ]) && echo "  Facebook scraping (Bright Data): ✅" || echo "  Facebook scraping: ❌"
([ -n "${BRIGHTDATA_MCP_URL:-}" ] || [ -f "$WORKSPACE/scripts/brightdata-mcp-url.txt" ]) && echo "  CAPTCHA bypass (Bright Data): ✅" || echo "  CAPTCHA bypass: ❌"
([ -n "${JINA_API_KEY:-}" ] || [ -f "$WORKSPACE/scripts/jina-api-key.txt" ]) && echo "  Deep search (Jina): ✅" || echo "  Deep search (Jina): ❌"
[ -n "${PERPLEXITY_API_KEY:-}" ] && echo "  Quick answers (Perplexity Sonar): ✅" || echo "  Quick answers (Perplexity): ❌"
[ -n "${PERPLEXITY_API_KEY:-}" ] && echo "  Deep research (Perplexity Deep): ✅" || echo "  Deep research (Perplexity): ❌"
[ -n "${TAVILY_API_KEY:-}" ] && echo "  Agent search (Tavily): ✅" || echo "  Agent search (Tavily): ❌"
[ -n "${EXA_API_KEY:-}" ] && echo "  Semantic search (Exa): ✅" || echo "  Semantic search (Exa): ❌"
[ -n "${EXA_API_KEY:-}" ] && echo "  People/Company search (Exa): ✅" || echo "  People/Company search (Exa): ❌"
([ -n "${PARALLEL_API_KEY:-}" ] || [ -f "$WORKSPACE/scripts/parallel-api-key.txt" ]) && echo "  AI search (Parallel): ✅" || echo "  AI search (Parallel): ❌"
[ -f "$WORKSPACE/skills/telegram/scripts/tg.py" ] && echo "  Telegram intel: ✅" || echo "  Telegram intel: ❌"
(command -v himalaya &>/dev/null || [ -f ~/.local/bin/himalaya ]) && echo "  Email intel: ✅" || echo "  Email intel: ❌"
has_py() { python3 -c "import $1" &>/dev/null; }
echo "  Infra records keyless (RDAP/DoH/crt.sh/certspotter/ASN, osint-tool.py): ✅"
[ -n "${SHODAN_API_KEY:-}" ] && echo "  Ports/services (Shodan host): ✅" || echo "  Ports/services (Shodan InternetDB keyless): ✅"
echo "  Company/LEI registry (GLEIF keyless): ✅"
[ -n "${OPENCORPORATES_API_KEY:-}" ] && echo "  Company registry (OpenCorporates): ✅" || echo "  Company registry (OpenCorporates): ❌"
echo "  Sanctions (OFAC SDN keyless): ✅"
([ -n "${OPENSANCTIONS_API_KEY:-}" ] || [ -n "${YENTE_URL:-}" ]) && echo "  Sanctions/PEP (OpenSanctions): ✅" || echo "  Sanctions/PEP (OpenSanctions): ❌"
echo "  Court records (CourtListener): ✅"
echo "  Crypto BTC/Solana/ENS keyless: ✅"
[ -n "${ETHERSCAN_API_KEY:-}" ] && echo "  Crypto ETH (Etherscan): ✅" || echo "  Crypto ETH (Blockscout keyless only): ✅"
echo "  Username sweep (curated + WhatsMyName, identity-sweep.py): ✅"
(command -v maigret &>/dev/null || command -v sherlock &>/dev/null) && echo "  Username sweep deep (maigret/sherlock): ✅" || echo "  Username sweep deep (maigret/sherlock): ❌"
command -v holehe &>/dev/null && echo "  Email account enumeration (holehe): ✅" || echo "  Email account enumeration (holehe): ❌"
command -v telegram-phone-number-checker &>/dev/null && [ -n "${API_ID:-}" ] && echo "  Telegram phone check: ✅" || echo "  Telegram phone check: ❌"
(command -v dnstwist &>/dev/null || has_py dnstwist) && echo "  Typosquat (dnstwist): ✅" || echo "  Typosquat (dnstwist): ❌"
echo "  Reddit history (reddit-arctic.py, keyless): ✅"
(command -v yt-dlp &>/dev/null || command -v gallery-dl &>/dev/null) && echo "  Social media capture (capture-evidence --social): ✅" || echo "  Social media capture (capture-evidence --social): ❌"
[ -n "${ARCHIVEBOX_URL:-}" ] && echo "  ArchiveBox copy (capture-evidence --archivebox): ✅" || echo "  ArchiveBox copy: ❌"
[ -n "${CHANGEDETECTION_URL:-}" ] && echo "  Page monitoring (watch.py / /q-watch): ✅" || echo "  Page monitoring (watch.py / /q-watch): ❌"
if curl -s -m 2 -o /dev/null -w '%{http_code}' "${CRAWL4AI_URL:-http://localhost:11235}/health" 2>/dev/null | grep -q '^200$'; then
  echo "  Crawl (crawl4ai reachable): ✅"
elif has_py scrapling; then
  echo "  Crawl (Scrapling fallback; crawl4ai not reachable): ✅"
else
  echo "  Crawl (crawl.sh: crawl4ai not reachable, Scrapling not installed): ❌"
fi
command -v katana &>/dev/null && echo "  Site spider (katana): ✅" || echo "  Site spider (katana): ❌"
[ -n "${GOOGLE_VISION_API_KEY:-}" ] && echo "  Reverse image / web entities (Google Vision): ✅" || echo "  Reverse image (Google Vision): ❌"
has_py shadowfinder && echo "  Shadow geolocation (shadowfinder.sh): ✅" || echo "  Shadow geolocation (shadowfinder.sh): ❌"
command -v c2patool &>/dev/null && echo "  C2PA provenance (verification skill): ✅" || echo "  C2PA provenance: ❌"
command -v exiftool &>/dev/null && echo "  EXIF extraction (intake/capture): ✅" || echo "  EXIF extraction: ❌"
has_py presidio_anonymizer && echo "  PII redaction (redact-pii.py presidio): ✅" || echo "  PII redaction (redact-pii.py regex only): ✅"
echo "  STIX/MISP/CSV export (export-intel.py, no deps): ✅"
has_py splink && echo "  Entity resolution (resolve-entities.py splink): ✅" || echo "  Entity resolution (splink): ❌"
echo ""

# 6. Adapter registry (osint-tool.py) -- never fatal
echo "🧩 osint-tool.py adapters:"
if ! python3 - "$SCRIPT_DIR/osint-tool.py" <<'PYEOF'
import json, subprocess, sys
out = subprocess.run([sys.executable, sys.argv[1], "--list", "--json"],
                     capture_output=True, text=True, timeout=120)
if out.returncode != 0:
    print("  ❌ osint-tool.py --list exited %d: %s" % (out.returncode, out.stderr.strip()[-300:]))
    sys.exit(1)
d = json.loads(out.stdout)
p = d.get("providers", [])
ready = [r for r in p if not r.get("missing")]
missing = [r for r in p if r.get("missing")]
print("  %d adapters: %d ready, %d missing a key or binary" % (len(p), len(ready), len(missing)))
for r in missing:
    print("  ⚪ %-20s %s  needs %s" % (r["slug"], r["tier"], ", ".join(r["missing"])))
errs = d.get("import_errors") or {}
for k, v in errs.items():
    print("  ❌ IMPORT ERROR %s: %s" % (k, v))
if not errs:
    print("  import errors: none")
PYEOF
then
  echo "  ❌ osint-tool.py --list failed (run it directly to see the error)"
fi
echo "  Full table: python3 $SCRIPT_DIR/osint-tool.py --list"
echo "  Install optional tools: bash $SCRIPT_DIR/setup-tools.sh --list"
echo ""
echo "=== END DIAGNOSTIC ==="
