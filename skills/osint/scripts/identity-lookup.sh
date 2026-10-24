#!/bin/bash
# Free, keyless identity/leak lookups (no captcha, no login wall, no scraping)
# Sources verified live 2026-07-03. Two adjacent sources (phonebook.cz API,
# psbdmp.ws) were dropped from this script because their hostnames no
# longer resolve -- do not re-add without re-verifying with curl -sv first.
# Usage: identity-lookup.sh keybase <username>
#        identity-lookup.sh github <username>
#        identity-lookup.sh mastodon <query>
#        identity-lookup.sh leakcheck <email>
#        identity-lookup.sh sweep <handle|email|phone> [case]
#          -> runs identity-sweep.py: every ready identity adapter, merged, T3
set -euo pipefail

CMD="${1:?Usage: identity-lookup.sh keybase|github|mastodon|leakcheck|sweep <query> [case]}"
QUERY="${2:?Missing query}"
UA="investigators-copilot-osint/1.0 (+investigation tooling)"

case "$CMD" in
  sweep)
    # All ready identity adapters at once (osint-tool.py framework). Results are T3.
    TARGET="$QUERY"
    CASE="${3:-}"
    python3 "$(dirname "$0")/identity-sweep.py" "$TARGET" ${CASE:+--case "$CASE"}
    ;;
  keybase)
    # Verified identities + cryptographically signed social proofs (T2-grade,
    # not a name-match hypothesis -- the proof is signed by the account).
    curl -s -H "User-Agent: $UA" \
      "https://keybase.io/_/api/1.0/user/lookup.json?usernames=$QUERY" \
      | python3 -c "
import json, sys
d = json.load(sys.stdin)
them = d.get('them') or []
if not them or them[0] is None:
    print('No Keybase user found for that username.')
    sys.exit(0)
u = them[0]
basics = u.get('basics', {})
profile = u.get('profile', {})
print(f\"👤 {basics.get('username','')}\")
if profile.get('full_name'): print(f\"   Name: {profile['full_name']}\")
if profile.get('location'): print(f\"   Location: {profile['location']}\")
proofs = u.get('proofs_summary', {}).get('all', [])
if proofs:
    print(f'   Verified proofs ({len(proofs)}):')
    for p in proofs:
        print(f\"     - {p.get('proof_type','')}: {p.get('nametag','')}\")
else:
    print('   No verified social proofs on this account.')
"
    ;;
  github)
    # Public profile often leaks real email + location even for accounts
    # that don't think of GitHub as social media. Unauthenticated: 60
    # req/hr per IP. Set GITHUB_TOKEN for a higher limit (optional).
    if [ -n "${GITHUB_TOKEN:-}" ]; then
      GH_RESPONSE=$(curl -s -H "User-Agent: $UA" -H "Accept: application/vnd.github.v3+json" \
        -H "Authorization: Bearer $GITHUB_TOKEN" \
        "https://api.github.com/users/$QUERY")
    else
      GH_RESPONSE=$(curl -s -H "User-Agent: $UA" -H "Accept: application/vnd.github.v3+json" \
        "https://api.github.com/users/$QUERY")
    fi
    echo "$GH_RESPONSE" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if d.get('message') == 'Not Found':
    print('No GitHub user found.')
    sys.exit(0)
print(f\"👤 {d.get('login','')} (id {d.get('id','')})\")
for label, key in [('Name','name'), ('Email','email'), ('Company','company'),
                    ('Location','location'), ('Blog','blog')]:
    if d.get(key): print(f'   {label}: {d[key]}')
if d.get('twitter_username'): print(f\"   Twitter: @{d['twitter_username']}\")
print(f\"   Repos: {d.get('public_repos',0)}  Followers: {d.get('followers',0)}  Created: {d.get('created_at','')}\")
print(f\"   URL: {d.get('html_url','')}\")
"
    ;;
  mastodon)
    # Federated search on the mastodon.social instance. Query can be a
    # handle or a keyword; the instance itself is just one search vantage
    # point into the fediverse, not exhaustive.
    curl -s -H "User-Agent: $UA" \
      --data-urlencode "q=$QUERY" --data-urlencode "type=accounts" --data-urlencode "limit=10" -G \
      "https://mastodon.social/api/v2/search" \
      | python3 -c "
import json, sys
d = json.load(sys.stdin)
accounts = d.get('accounts', [])
if not accounts:
    print('No Mastodon accounts found.')
    sys.exit(0)
for a in accounts:
    print(f\"👤 {a.get('display_name','')} (@{a.get('acct','')})\")
    print(f\"   {a.get('url','')}\")
    print(f\"   Followers: {a.get('followers_count',0)}  Created: {a.get('created_at','')}\")
    note = (a.get('note') or '').strip()
    if note: print(f'   Bio: {note[:150]}')
    print()
"
    ;;
  leakcheck)
    # LeakCheck public tier: minimal credential-exposure check, no key,
    # low rate limit. Run this alongside the existing HudsonRock Cavalier
    # / holehe Level 1.5 checks, not instead of them.
    curl -s -H "User-Agent: $UA" -H "Accept: application/json" \
      --data-urlencode "check=$QUERY" -G \
      "https://leakcheck.io/api/public" \
      | python3 -c "
import json, sys
d = json.load(sys.stdin)
if not d.get('success'):
    print('LeakCheck: no result (or rate limited -- public tier is low-volume).')
    sys.exit(0)
found = d.get('found', 0)
if found:
    print(f'⚠️  Found in {found} breach source(s)')
else:
    print('No breach hits on LeakCheck public tier.')
fields = d.get('fields', [])
if fields: print(f\"   Exposed field types: {', '.join(fields)}\")
sources = d.get('sources', [])
if sources:
    print(f'   Sources ({len(sources)}):')
    for s in sources[:20]:
        print(f\"     - {s.get('name','')} ({s.get('date','')})\")
"
    ;;
  *)
    echo "Unknown command: $CMD (use keybase|github|mastodon|leakcheck|sweep)" >&2
    exit 1
    ;;
esac
