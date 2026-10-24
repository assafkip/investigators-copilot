#!/bin/bash
# recent-activity.sh -- keyless "what has this handle done lately" sweep (T3)
#
# Pulls the most recent public activity for a handle from platforms that expose
# it without an API key, normalises it into one JSON document and filters to the
# last N days. Every item is T3: automated tool output, a lead only.
#
#   Bluesky   public AppView  app.bsky.actor.getProfile + app.bsky.feed.getAuthorFeed
#   GitHub    REST            /users/<u> + /users/<u>/events/public  (60 req/h keyless;
#                             $GITHUB_TOKEN raises the limit if set)
#   Mastodon  instance API    /api/v1/accounts/lookup + /statuses (user@instance only;
#                             instances with DISALLOW_UNAUTHENTICATED_API_ACCESS refuse)
#   Threads   no keyless API  reported as manual (open https://www.threads.net/@<h>)
#
# Usage:
#   recent-activity.sh <handle> [--days N] [--limit N] [--case <case>]
#                      [--bluesky <h>] [--github <u>] [--mastodon <user@instance>]
#                      [--only bluesky,github,mastodon,threads]
#
# <handle> is used for every platform unless a per-platform flag overrides it.
# A Bluesky handle without a dot becomes <handle>.bsky.social. Mastodon runs
# only when a user@instance form is available.
#
# Output: JSON on stdout. With --case also saved to
#   investigations/<case>/investigation/evidence/raw-collections/<ts>-recent-activity-<handle>/
#
# Env (optional, for tests/mirrors): BSKY_API (default https://public.api.bsky.app),
#   GITHUB_API (default https://api.github.com), GITHUB_TOKEN.
#
# Requires: curl, jq

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../../.." && pwd)"

BSKY_API="${BSKY_API:-https://public.api.bsky.app}"
GITHUB_API="${GITHUB_API:-https://api.github.com}"
UA="workspace recent-activity.sh"

usage() {
  sed -n '17,24p' "$0" | sed 's/^# \{0,1\}//' >&2
  exit 1
}

HANDLE="${1:-}"
[ -z "$HANDLE" ] && usage
case "$HANDLE" in -h | --help) usage ;; esac
shift
HANDLE="${HANDLE#@}"

DAYS=30
LIMIT=50
CASE=""
WANT_CASE=0
BSKY_H=""
GH_U=""
MASTO=""
ONLY="bluesky,github,mastodon,threads"
while [ $# -gt 0 ]; do
  case "$1" in
    --days) DAYS="${2:?}"; shift 2 ;;
    --limit) LIMIT="${2:?}"; shift 2 ;;
    --case) CASE="${2:-}"; WANT_CASE=1; shift 2 ;;
    --bluesky) BSKY_H="${2#@}"; shift 2 ;;
    --github) GH_U="${2#@}"; shift 2 ;;
    --mastodon) MASTO="${2#@}"; shift 2 ;;
    --only) ONLY="${2:?}"; shift 2 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage ;;
  esac
done

command -v jq >/dev/null 2>&1 || { echo "ERROR: jq not installed" >&2; exit 1; }

[ -z "$BSKY_H" ] && BSKY_H="$HANDLE"
case "$BSKY_H" in *.*) ;; *) BSKY_H="$BSKY_H.bsky.social" ;; esac
[ -z "$GH_U" ] && GH_U="${HANDLE%%@*}"
if [ -z "$MASTO" ]; then
  case "$HANDLE" in *@*.*) MASTO="$HANDLE" ;; esac
fi

TMP="$(mktemp -d -t recent-XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

SINCE_EPOCH=$(( $(date -u +%s) - DAYS * 86400 ))
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

wants() { case ",$ONLY," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }

# get <url> <outfile> [extra curl args...] -> prints HTTP code
get() {
  local url="$1" out="$2"; shift 2
  curl -sS -L --max-time 25 -A "$UA" -o "$out" -w '%{http_code}' "$@" "$url" 2>/dev/null || echo "000"
}

# status_doc <platform> <status> <detail> -> writes a minimal per-platform JSON
status_doc() {
  jq -n --arg p "$1" --arg s "$2" --arg d "$3" '{platform: $p, status: $s, detail: $d, items: []}' > "$TMP/$1.json"
}

do_bluesky() {
  local enc code
  enc=$(jq -rn --arg v "$BSKY_H" '$v|@uri')
  code=$(get "$BSKY_API/xrpc/app.bsky.feed.getAuthorFeed?actor=$enc&limit=$([ "$LIMIT" -gt 100 ] && echo 100 || echo "$LIMIT")" "$TMP/bsky.raw")
  if [ "$code" != "200" ]; then status_doc bluesky error "HTTP $code for $BSKY_H"; return; fi
  get "$BSKY_API/xrpc/app.bsky.actor.getProfile?actor=$enc" "$TMP/bsky.profile" >/dev/null || true
  jq --arg h "$BSKY_H" --argjson since "$SINCE_EPOCH" --slurpfile prof <(cat "$TMP/bsky.profile" 2>/dev/null || echo '{}') '
    {platform: "bluesky", status: "ok", account: $h,
     profile: (($prof[0] // {}) | {did, handle, displayName, description, followersCount, followsCount, postsCount, createdAt}),
     items: [(.feed // [])[] | .post as $p
       | {time: ($p.record.createdAt // $p.indexedAt), kind: (if .reason then "repost" else "post" end),
          text: ($p.record.text // ""),
          url: ("https://bsky.app/profile/" + $p.author.handle + "/post/" + ($p.uri | split("/") | last)),
          author: $p.author.handle}
       | select(((.time // "") | sub("\\.[0-9]+"; "") | sub("\\+00:00$"; "Z") | try fromdateiso8601 catch 0) >= $since)]}
  ' "$TMP/bsky.raw" > "$TMP/bluesky.json" 2>/dev/null || status_doc bluesky error "unparseable response"
}

do_github() {
  local auth=() code
  [ -n "${GITHUB_TOKEN:-}" ] && auth=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
  code=$(get "$GITHUB_API/users/$GH_U/events/public?per_page=$([ "$LIMIT" -gt 100 ] && echo 100 || echo "$LIMIT")" "$TMP/gh.raw" \
    -H "Accept: application/vnd.github+json" ${auth[@]+"${auth[@]}"})
  if [ "$code" != "200" ]; then status_doc github error "HTTP $code for $GH_U"; return; fi
  get "$GITHUB_API/users/$GH_U" "$TMP/gh.profile" -H "Accept: application/vnd.github+json" ${auth[@]+"${auth[@]}"} >/dev/null || true
  jq --arg u "$GH_U" --argjson since "$SINCE_EPOCH" --slurpfile prof <(cat "$TMP/gh.profile" 2>/dev/null || echo '{}') '
    {platform: "github", status: "ok", account: $u,
     profile: (($prof[0] // {}) | {login, name, company, blog, location, email, bio, twitter_username, created_at, public_repos}),
     items: [.[] | {time: .created_at, kind: .type, repo: .repo.name,
                    url: ("https://github.com/" + .repo.name),
                    text: ((.payload.commits // []) | map(.message) | join(" | ") | .[0:300])}
             | select((.time | try fromdateiso8601 catch 0) >= $since)]}
  ' "$TMP/gh.raw" > "$TMP/github.json" 2>/dev/null || status_doc github error "unparseable response"
}

do_mastodon() {
  if [ -z "$MASTO" ]; then status_doc mastodon skipped "needs user@instance (pass --mastodon)"; return; fi
  local user="${MASTO%@*}" inst="${MASTO##*@}" code id
  code=$(get "https://$inst/api/v1/accounts/lookup?acct=$user" "$TMP/m.acct")
  if [ "$code" != "200" ]; then status_doc mastodon error "lookup HTTP $code on $inst (instance may require auth)"; return; fi
  id=$(jq -r '.id // empty' "$TMP/m.acct")
  [ -n "$id" ] || { status_doc mastodon error "no account id"; return; }
  code=$(get "https://$inst/api/v1/accounts/$id/statuses?limit=$([ "$LIMIT" -gt 40 ] && echo 40 || echo "$LIMIT")" "$TMP/m.raw")
  if [ "$code" != "200" ]; then status_doc mastodon error "statuses HTTP $code"; return; fi
  jq --arg a "$MASTO" --argjson since "$SINCE_EPOCH" --slurpfile acct "$TMP/m.acct" '
    {platform: "mastodon", status: "ok", account: $a,
     profile: ($acct[0] | {acct, display_name, note, followers_count, following_count, statuses_count, created_at, url}),
     items: [.[] | {time: .created_at, kind: (if .reblog then "boost" else "post" end), url: (.url // .uri),
                    text: ((.content // "") | gsub("<[^>]+>"; " ") | .[0:500])}
             | select((.time | sub("\\.[0-9]+"; "") | try fromdateiso8601 catch 0) >= $since)]}
  ' "$TMP/m.raw" > "$TMP/mastodon.json" 2>/dev/null || status_doc mastodon error "unparseable response"
}

do_threads() {
  status_doc threads manual "No keyless API. Open https://www.threads.net/@${HANDLE%%@*} and capture with capture-evidence.sh"
}

for p in bluesky github mastodon threads; do
  if wants "$p"; then "do_$p"; fi
done

shopt -s nullglob
FILES=("$TMP"/bluesky.json "$TMP"/github.json "$TMP"/mastodon.json "$TMP"/threads.json)
EXISTING=()
for f in "${FILES[@]}"; do [ -f "$f" ] && EXISTING+=("$f"); done

jq -s --arg h "$HANDLE" --arg ts "$NOW" --argjson days "$DAYS" '
  {handle: $h, queried_at: $ts, window_days: $days, tier: "T3",
   note: "Automated public-activity sweep. Same handle on two platforms is NOT the same person without a T1/T2 crosslink.",
   platforms: (map({key: .platform, value: .}) | from_entries),
   total_items: (map(.items | length) | add // 0)}
' ${EXISTING[@]+"${EXISTING[@]}"} > "$TMP/out.json"

if [ "$WANT_CASE" = "1" ]; then
  # shellcheck source=lib/active_case.sh
  source "$SCRIPT_DIR/lib/active_case.sh"
  resolve_case_dir "$CASE" || exit 1
  DEST="$CASE_DIR/investigation/evidence/raw-collections/$(date -u +%Y%m%dT%H%M%SZ)-recent-activity-$(printf '%s' "$HANDLE" | tr -c 'A-Za-z0-9._-' '_')"
  mkdir -p "$DEST"
  cp "$TMP/out.json" "$DEST/recent-activity.json"
  echo "[recent-activity] saved: $DEST" >&2
fi

cat "$TMP/out.json"
