#!/bin/bash
# Apify API wrapper for OSINT skill
# Requires: APIFY_API_TOKEN env var
# Usage: ./apify.sh <action> [params]

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$(cd "$SKILL_DIR/../.." && pwd)"
[ -z "${APIFY_API_TOKEN:-}" ] && [ -f "$WORKSPACE/scripts/apify-api-token.txt" ] && export APIFY_API_TOKEN=$(head -1 "$WORKSPACE/scripts/apify-api-token.txt")

TOKEN="${APIFY_API_TOKEN:?ERROR: APIFY_API_TOKEN not set. Get one at https://console.apify.com/account/integrations}"
BASE="https://api.apify.com/v2"
AUTH=(-H "Authorization: Bearer $TOKEN")
# Spend caps on every run (2026-10-10). Override per call via env.
CAPS="maxItems=${APIFY_MAX_ITEMS:-100}&maxTotalChargeUsd=${APIFY_MAX_CHARGE_USD:-5}"

case "${1:-help}" in
  run)
    ACTOR_ID="$2"
    INPUT="$3"
    curl -s -X POST "$BASE/acts/$ACTOR_ID/runs?$CAPS" \
      "${AUTH[@]}" \
      -H "Content-Type: application/json" \
      -d "$INPUT"
    ;;
  results)
    RUN_ID="$2"
    curl -s "${AUTH[@]}" "$BASE/actor-runs/$RUN_ID/dataset/items"
    ;;
  run-status)
    RUN_ID="$2"
    curl -s "${AUTH[@]}" "$BASE/actor-runs/$RUN_ID"
    ;;
  store-search)
    QUERY="${*:2}"
    curl -s "${AUTH[@]}" "$BASE/store?limit=10&search=$(echo "$QUERY" | sed 's/ /+/g')"
    ;;
  linkedin)
    # LinkedIn profile via supreme_coder (works on free plan)
    URL="$2"
    curl -s -X POST "$BASE/acts/supreme_coder~linkedin-profile-scraper/runs?$CAPS" \
      "${AUTH[@]}" \
      -H "Content-Type: application/json" \
      -d "{\"urls\":[{\"url\":\"$URL\"}]}"
    ;;
  instagram)
    # Instagram profile scraper
    USERNAME="$2"
    curl -s -X POST "$BASE/acts/apify~instagram-profile-scraper/runs?$CAPS" \
      "${AUTH[@]}" \
      -H "Content-Type: application/json" \
      -d "{\"usernames\":[\"$USERNAME\"]}"
    ;;
  *)
    echo "Usage: apify.sh {run|results|run-status|store-search|linkedin|instagram} [args]"
    echo ""
    echo "Shortcuts:"
    echo "  linkedin <profile_url>  - scrape LinkedIn profile (\$0.005)"
    echo "  instagram <username>    - scrape Instagram profile"
    echo ""
    echo "General:"
    echo "  run <actor_id> <json>   - run any actor"
    echo "  results <run_id>        - get results"
    echo "  run-status <run_id>     - check run status"
    echo "  store-search <query>    - search Apify store"
    echo ""
    echo "Env: APIFY_API_TOKEN (required)"
    ;;
esac
