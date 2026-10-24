# OSINT Toolkit Reference

## Table of Contents
1. [Search Tools](#search-tools)
2. [Scraping Tools](#scraping-tools)
3. [Apify Actor Runner](#apify-actor-runner-embedded)
4. [Apify Actor Catalog (55+)](#apify-actor-catalog)
5. [Actor Discovery](#actor-discovery)
6. [Shortcuts (apify.sh)](#shortcuts)
7. [Telegram](#telegram)
8. [Enrichment adapters (osint-tool.py)](#enrichment-adapters-osint-toolpy)
9. [Crawl, archive, watch](#crawl-archive-watch)
10. [Exports](#exports)
11. [Optional services and setup](#optional-services-and-setup)
12. [External tool catalog](#external-tool-catalog)
13. [Apify Troubleshooting](#apify-troubleshooting)
14. [Cost Reference](#cost-reference)

---

## Search Tools

### Brave Search (web_search built-in)
- No setup, FREE plan 2000 queries/month, rate limit 1/sec
- Best for: general web, articles, profile discovery
- Weakness: rate limited, no geo-targeting

### Jina s.reader (scripts/jina.sh search)
- Top 10 results as full markdown
- Best for: broad search with content extraction
- Weakness: can return wrong person on common names

### Parallel AI (scripts/parallel.sh search)
- AI-powered search with reasoning and citations
- Best for: social media discovery, cross-referencing
- Weakness: sometimes returns irrelevant AI-reasoned results

### Bright Data (scripts/brightdata.sh search)
- Google/Bing/Yandex with geo-targeting, bypasses CAPTCHA
- search-geo: `brightdata.sh search-geo ru "query"` (search as if from Russia)
- search-yandex: `brightdata.sh search-yandex "query"` (better for Russian targets)
- Batch: up to 10 queries

## Scraping Tools

### web_fetch (built-in)
- Basic URL → markdown. First attempt, fallback to better tools
- Fails on: LinkedIn, Facebook, Cloudflare

### Jina r.reader (scripts/jina.sh read)
- Clean markdown, faster than web_fetch
- Fails on: LinkedIn authwall, Facebook authwall, Instagram JS

### Bright Data (scripts/brightdata.sh scrape)
- **Bypasses EVERYTHING**: bot detection, CAPTCHA, authwall, Cloudflare
- The nuclear option. Use when others fail.
- Batch: up to 10 URLs via scrape-batch

---

## Apify Actor Runner (embedded)

`run_actor.js` — universal script that runs ANY Apify actor. Embedded from
[apify/agent-skills](https://github.com/apify/agent-skills) v1.3.0.

**Requirements:** Node.js 18+ (for global fetch), APIFY_API_TOKEN or APIFY_TOKEN env var.

### Via bash wrapper (recommended)

```bash
# Quick answer — top 5 results in chat
bash scripts/run-actor.sh "ACTOR_ID" 'JSON_INPUT'

# Export to CSV
bash scripts/run-actor.sh "ACTOR_ID" 'JSON_INPUT' --output /tmp/result.csv --format csv

# Export to JSON
bash scripts/run-actor.sh "ACTOR_ID" 'JSON_INPUT' --output /tmp/result.json --format json
```

### Direct node call

```bash
APIFY_TOKEN=$APIFY_API_TOKEN node scripts/run_actor.js \
  --actor "ACTOR_ID" --input 'JSON_INPUT'
```

### Spend guardrails (added 2026-10-10)

Upstream apify/agent-skills dropped this runner (moved to the Apify CLI), so the
copy here is maintained in Investigators Copilot. Every run now:

- passes `maxItems` (default 100, `--max-items N`) and `maxTotalChargeUsd`
  (default $5, `--max-charge-usd X`) to the Apify run API, so a run cannot
  overspend even if the actor misbehaves;
- probes the actor first: a **deprecated** actor exits 4 and is never started;
- estimates cost from the actor's current pricing (highest plan tier, so an
  upper bound): warns above $5, **refuses above $20** unless `--confirm-spend`.
- sends the token as a Bearer header, never in the URL.

`apify.sh` applies the same caps via `APIFY_MAX_ITEMS` / `APIFY_MAX_CHARGE_USD`.

---

## Apify Actor Catalog

### Instagram (12 actors)

| Actor ID | Best For | OSINT Use |
|----------|----------|-----------|
| `apify/instagram-profile-scraper` | Profile data, follower counts, bio | **Primary** — bio, location, links |
| `apify/instagram-post-scraper` | Individual post details, engagement | Content analysis |
| `apify/instagram-comment-scraper` | Comment extraction | Sentiment, social graph |
| `apify/instagram-hashtag-scraper` | Hashtag content, trending topics | Find target by hashtag |
| `apify/instagram-hashtag-stats` | Hashtag performance metrics | Audience analysis |
| `apify/instagram-reel-scraper` | Reels content and metrics | Video content style |
| `apify/instagram-search-scraper` | Search users, places, hashtags | Discovery |
| `apify/instagram-tagged-scraper` | Posts tagged with specific accounts | **Who tags them** = social graph |
| `apify/instagram-followers-count-scraper` | Follower count tracking | Influence assessment |
| `apify/instagram-scraper` | Comprehensive Instagram data | Full profile deep dive |
| `apify/instagram-api-scraper` | API-based Instagram access | Fallback scraper |
| `apify/export-instagram-comments-posts` | Bulk comment/post export | Large-scale extraction |

### Facebook (14 actors)

| Actor ID | Best For | OSINT Use |
|----------|----------|-----------|
| `apify/facebook-pages-scraper` | Page data, metrics, contact info | **Primary** for public pages |
| `apify/facebook-page-contact-information` | Emails, phones, addresses | Contact enrichment |
| `apify/facebook-posts-scraper` | Post content and engagement | Writing style analysis |
| `apify/facebook-comments-scraper` | Comment extraction | Sentiment analysis |
| `apify/facebook-likes-scraper` | Reaction analysis | Audience mapping |
| `apify/facebook-reviews-scraper` | Page reviews | Reputation analysis |
| `apify/facebook-groups-scraper` | Group content and members | Community membership |
| `apify/facebook-events-scraper` | Event data | Activity/interests |
| `apify/facebook-ads-scraper` | Ad creative and targeting | Competitor intel |
| `apify/facebook-search-scraper` | Search results | Discovery |
| `apify/facebook-reels-scraper` | Reels content | Video style |
| `apify/facebook-photos-scraper` | Photo extraction | Visual profile |
| `apify/facebook-marketplace-scraper` | Marketplace listings | Business activity |
| `apify/facebook-followers-following-scraper` | Follower/following lists | Social graph |

**Note:** Facebook personal profiles require Bright Data. These actors work with public Pages/Groups/Marketplace.

### TikTok (14 actors)

| Actor ID | Best For | OSINT Use |
|----------|----------|-----------|
| `clockworks/tiktok-scraper` | Comprehensive TikTok data | Full platform deep dive |
| `clockworks/free-tiktok-scraper` | Free TikTok extraction | **Budget fallback** |
| `clockworks/tiktok-profile-scraper` | Profile data, bio, stats | **Primary** — bio, follower data |
| `clockworks/tiktok-video-scraper` | Video details and metrics | Content analysis |
| `clockworks/tiktok-comments-scraper` | Comment extraction | Sentiment, audience |
| `clockworks/tiktok-followers-scraper` | Follower lists | Social graph |
| `clockworks/tiktok-user-search-scraper` | Find users by keywords | **Discovery** by name |
| `clockworks/tiktok-hashtag-scraper` | Hashtag content | Topic analysis |
| `clockworks/tiktok-sound-scraper` | Trending sounds | Cultural markers |
| `clockworks/tiktok-ads-scraper` | Ad content | Competitor ads |
| `clockworks/tiktok-discover-scraper` | Discover page content | Trending content |
| `clockworks/tiktok-explore-scraper` | Explore content | Algorithm analysis |
| `clockworks/tiktok-trends-scraper` | Trending content | Trend tracking |
| ~~`clockworks/tiktok-live-scraper`~~ | DEPRECATED on Apify Store (2026-10-10); the runner refuses it | -- |

### YouTube (5 actors)

| Actor ID | Best For | OSINT Use |
|----------|----------|-----------|
| `streamers/youtube-scraper` | Video data and metrics | Content analysis |
| `streamers/youtube-channel-scraper` | Channel info, subscriber data | **Primary** — channel metadata |
| `streamers/youtube-comments-scraper` | Comment extraction | Audience sentiment |
| `streamers/youtube-shorts-scraper` | Shorts content | Short-form style |
| ~~`streamers/youtube-video-scraper-by-hashtag`~~ | DEPRECATED on Apify Store (2026-10-10); the runner refuses it | -- |

### Google Maps (4 actors)

| Actor ID | Best For | OSINT Use |
|----------|----------|-----------|
| `compass/crawler-google-places` | Business listings, ratings, contact | **Primary** — verify business owners |
| `compass/google-maps-extractor` | Detailed business data | Deep business intel |
| `compass/Google-Maps-Reviews-Scraper` | Review extraction | Writing style in responses |
| `poidata/google-maps-email-extractor` | Email discovery from listings | Contact enrichment |

### Other Platforms (6 actors)

| Actor ID | Best For | OSINT Use |
|----------|----------|-----------|
| `apify/google-search-scraper` | Google search results | Structured search |
| `apify/google-trends-scraper` | Google Trends data | Interest tracking |
| `voyager/booking-scraper` | Booking.com hotel data | Travel/business intel |
| `voyager/booking-reviews-scraper` | Booking.com reviews | Reputation |
| `maxcopell/tripadvisor-reviews` | TripAdvisor reviews | Hospitality intel |
| `vdrmota/contact-info-scraper` | Contact enrichment from URLs | **Emails/phones from any site** |

### LinkedIn

LinkedIn actors are volatile on Apify. Current primary:
- `supreme_coder~linkedin-profile-scraper` via `apify.sh linkedin` → $0.005/profile
- Fallback: `brightdata.sh scrape` (always works, higher cost)
- If primary fails: `bash scripts/apify.sh store-search "linkedin scraper"`

### Added 2026-10-10 (verified live on Apify Store, not deprecated)

| Actor ID | Pricing | OSINT use |
|----------|---------|-----------|
| `apidojo/tweet-scraper` | pay per event (~$0.0004/tweet) | X/Twitter posts by handle or search |
| `apidojo/twitter-user-scraper` | pay per event | X profiles, followers, following |
| `apify/threads-profile-api-scraper` | pay per event | Meta Threads profiles |
| `tri_angle/truth-scraper` | pay per event | Truth Social accounts and posts |
| `tri_angle/telegram-scraper` | pay per event | Public Telegram channels (alternative to tgspyder) |
| `tri_angle/snapchat-scraper` | pay per event | Snapchat public profiles |
| `tri_angle/social-media-finder` | pay per event | Find a person's accounts across platforms from a name |
| `harvestapi/linkedin-profile-scraper` | pay per event | LinkedIn profile + email, no cookies |
| `harvestapi/linkedin-profile-search-by-name` | pay per event | Find LinkedIn profiles by name, no cookies |
| `johnvc/yandex-reverse-image-search` | pay per event | Yandex reverse image search (best engine for faces/places in RU/CIS) |
| `tri_angle/bing-search-scraper` | pay per event | Bing SERP for dorking |
| `janbuchar/github-contributors-scraper` | free | Contributors of a repo (git-email pivots) |
| `apify/web-fetch` | pay per event | Single-URL fetch tier before Bright Data |
| `apify/website-content-crawler` | free | Whole-site crawl to markdown |
| `apify/camoufox-scraper` | free | Anti-bot browser scrape (Cloudflare-heavy sites) |
| `apify/sitemap-extractor` | pay per event | Every URL a site publishes |
| `apify/facebook-hashtag-scraper` | pay per event | Facebook posts by hashtag |
| `tri_angle/website-changes-detector` | free | Page-change monitoring (see `/q-watch`) |

Run any of them through `run-actor.sh`; the spend guardrails apply.

---

## Actor Selection by OSINT Task

| OSINT Phase | What You Need | Primary Actors |
|-------------|---------------|----------------|
| **Profile discovery** | Find accounts | `apify/instagram-search-scraper`, `clockworks/tiktok-user-search-scraper`, `apify/facebook-search-scraper` |
| **Profile deep dive** | Extract bio/stats | `apify/instagram-profile-scraper`, `clockworks/tiktok-profile-scraper`, `streamers/youtube-channel-scraper` |
| **Social graph** | Who they interact with | `apify/instagram-tagged-scraper`, `apify/instagram-comment-scraper`, `clockworks/tiktok-followers-scraper`, `apify/facebook-followers-following-scraper` |
| **Content analysis** | Posts, videos, style | `apify/instagram-post-scraper`, `clockworks/tiktok-video-scraper`, `streamers/youtube-scraper` |
| **Contact enrichment** | Emails, phones | `vdrmota/contact-info-scraper`, `apify/facebook-page-contact-information`, `poidata/google-maps-email-extractor` |
| **Business verification** | Company, location | `compass/crawler-google-places`, `compass/google-maps-extractor` |
| **Psychoprofile signals** | Sentiment, style | `apify/instagram-comment-scraper`, `clockworks/tiktok-comments-scraper`, `streamers/youtube-comments-scraper` |

### Multi-Actor Workflows (OSINT-specific)

| Workflow | Step 1 → | Step 2 |
|----------|----------|--------|
| **Full Instagram** | `apify/instagram-profile-scraper` → | `apify/instagram-tagged-scraper` + `apify/instagram-comment-scraper` |
| **Business owner** | `compass/crawler-google-places` → | `vdrmota/contact-info-scraper` on website |
| **Content creator** | `streamers/youtube-channel-scraper` → | `streamers/youtube-comments-scraper` |
| **TikTok target** | `clockworks/tiktok-user-search-scraper` → | `clockworks/tiktok-profile-scraper` + `clockworks/tiktok-comments-scraper` |
| **Facebook page** | `apify/facebook-pages-scraper` → | `apify/facebook-posts-scraper` + `apify/facebook-page-contact-information` |

---

## Actor Discovery

When none of the 55+ actors fit, search the Apify Store dynamically:

```bash
# Via mcpc CLI (if installed)
APIFY_TOKEN=$APIFY_API_TOKEN mcpc --json mcp.apify.com \
  --header "Authorization: Bearer $APIFY_TOKEN" \
  tools-call search-actors keywords:="SEARCH_KEYWORDS" limit:=10

# Via Apify API directly
bash scripts/apify.sh store-search "keyword1 keyword2"
```

Tips:
- Use 1-3 simple keywords (e.g., "LinkedIn profiles", "Twitter scraper")
- Sort by: PAY_PER_EVENT (works with small budgets), high rating, high run count
- Actors on Apify are volatile — always have a Bright Data fallback

---

## Shortcuts

`apify.sh` provides quick shortcuts for common operations:

```bash
bash scripts/apify.sh linkedin "https://linkedin.com/in/..."  # $0.005
bash scripts/apify.sh instagram "handle"                       # free tier
bash scripts/apify.sh run <actor_id> '<json>'                  # any actor
bash scripts/apify.sh results <run_id>                         # get results
bash scripts/apify.sh run-status <run_id>                      # check status
bash scripts/apify.sh store-search "query"                     # find actors
```

For anything beyond shortcuts, use `run-actor.sh` — it handles polling,
timeout, and CSV/JSON export automatically.

---

## Telegram

- Public channel posts: `web_fetch https://t.me/s/{channel}` (free, last ~20 posts)
- Profile bio: `web_fetch https://t.me/{username}` (free, shows bio/title)
- Private messages: tg.py (Telegram skill) or mcporter telegram tools

---

## Enrichment adapters (osint-tool.py)

Generated from `python3 scripts/osint-tool.py --list --json` (2026-10-10, 54 adapters).
Re-run `--list` for live ready/missing state on this machine. Run one:
`python3 scripts/osint-tool.py <slug> <query> [--mode M] [--json] [--case <case>|--save]`.
The same registry backs the `osint-infra` MCP tools `enrich` / `enrich_providers` and
`identity-sweep.py`. Tier: T1 = the adapter returns a record (registry, DNS, CT, on-chain);
T3 = tool output, hypothesis queue only. Reputation feeds, username hits and scraped
profiles never count as crosslinks. GPL/AGPL tools are run as subprocesses only.
Missing binaries: `bash scripts/setup-tools.sh --only <name>`.

| Slug | Tier | Category | Key (env) | Binary | Modes | License note |
|---|---|---|---|---|---|---|
| `blockscout` | T1 | crypto | keyless | - | default | - |
| `blockstream` | T1 | crypto | keyless | - | default | - |
| `crypto_abuse` | T3 | crypto | keyless | - | default | - |
| `ens` | T1 | crypto | keyless | - | default | - |
| `solana` | T1 | crypto | keyless | - | default | - |
| `tron` | T1 | crypto | `TRONGRID_API_KEY` | - | default | - |
| `wallet` | T1 | crypto | `ETHERSCAN_API_KEY` | - | auto, btc, eth, erc20 | - |
| `disposable_email` | T3 | identity | keyless | - | default | - |
| `email_intel` | T3 | identity | keyless | - | triage, headers, holehe | - |
| `ghunt` | T3 | identity | keyless | `ghunt` | default | AGPL-3.0: subprocess only, never imported |
| `git_osint` | T3 | identity | keyless | `git` | default | - |
| `github_user` | T3 | identity | keyless | - | default | - |
| `gitlab_user` | T3 | identity | keyless | - | default | - |
| `gitrecon` | T3 | identity | keyless | `gitrecon` | both, github, gitlab | GPL-3.0: subprocess only, never imported |
| `gravatar` | T3 | identity | keyless | - | default | - |
| `hackernews_user` | T3 | identity | keyless | - | default | - |
| `holehe` | T3 | identity | keyless | `holehe` | default | GPL-3.0: subprocess only, never imported |
| `maigret` | T3 | identity | keyless | `maigret` | default | MIT; invoked as a subprocess |
| `npm_user` | T3 | identity | keyless | - | default | - |
| `phone` | T3 | identity | keyless | - | default | - |
| `sherlock` | T3 | identity | keyless | `sherlock` | default | MIT; invoked as a subprocess |
| `telegram_phone` | T3 | identity | `API_ID` | `telegram-phone-number-checker` | default | MIT; invoked as a subprocess |
| `user_scanner` | T3 | identity | keyless | `user-scanner` | default | invoked as a subprocess |
| `username` | T3 | identity | keyless | - | default, full, curated | WhatsMyName data CC BY-SA 4.0 (data/NOTICE.md) |
| `xposedornot` | T3 | identity | keyless | - | default | - |
| `asn` | T1 | infra | keyless | - | default | - |
| `bbot` | T3 | infra | keyless | `bbot` | passive, subdomain-enum, email-enum, cloud-enum | AGPL-3.0: subprocess only |
| `certspotter` | T1 | infra | `CERTSPOTTER_API_KEY` | - | default | - |
| `crtsh` | T1 | infra | keyless | - | default | - |
| `dns_deep` | T1 | infra | keyless | - | default | - |
| `doh` | T1 | infra | keyless | - | all, A, AAAA, NS, MX, TXT, CNAME, CAA, PTR | - |
| `infra` | T1 | infra | keyless | - | whois, rdap, dns, reverse, dns_deep | - |
| `ipwhois` | T3 | infra | keyless | - | default | - |
| `rdap` | T1 | infra | keyless | - | default | - |
| `reverse_ip` | T3 | infra | keyless | - | default | - |
| `ripestat` | T1 | infra | keyless | - | default | - |
| `shodan` | T3 | infra | `SHODAN_API_KEY` | - | auto, internetdb, host | - |
| `theharvester` | T3 | infra | keyless | - | crtsh,certspotter,hackertarget,rapiddns,duckduckgo,otx,urlscan | GPL-2.0: subprocess only |
| `typosquat` | T3 | infra | keyless | - | default | - |
| `wappalyzer` | T3 | infra | keyless | - | default | httpx/wappalyzergo: MIT; subprocess |
| `courtlistener` | T1 | records | `COURTLISTENER_API_TOKEN` | - | dockets, opinions, oral, people | - |
| `gleif` | T1 | records | keyless | - | name, lei | - |
| `opencorporates` | T1 | records | `OPENCORPORATES_API_KEY` | - | company, officer | - |
| `wikidata` | T3 | records | keyless | - | default | - |
| `abuseipdb` | T3 | reputation | `ABUSEIPDB_API_KEY` | - | default | - |
| `greynoise` | T3 | reputation | `GREYNOISE_API_KEY` | - | default | - |
| `otx` | T3 | reputation | `OTX_API_KEY` | - | default | - |
| `sans_isc` | T3 | reputation | keyless | - | default | - |
| `stopforumspam` | T3 | reputation | keyless | - | auto, ip, email, username | - |
| `urlscan` | T3 | reputation | `URLSCAN_API_KEY` | - | default | - |
| `ofac` | T1 | sanctions | keyless | - | default | - |
| `opensanctions` | T3 | sanctions | `OPENSANCTIONS_API_KEY` | - | entity, person, company, search | - |
| `darkweb` | T3 | search | keyless | - | default | - |
| `spiderfoot` | T3 | search | keyless | - | passive, footprint, investigate, all, results | MIT; subprocess / REST |

---

## Crawl, archive, watch

| Task | Command | Backend / needs |
|---|---|---|
| One page to markdown | `bash scripts/crawl.sh fetch <url> [--case C]` | crawl4ai (`CRAWL4AI_URL`, docker) then Scrapling; fail-closed under `CRAWL_MIN_CHARS` |
| URL inventory | `bash scripts/crawl.sh map <url> [--depth N]` | katana |
| Evidence capture (chain of custody) | `bash scripts/capture-evidence.sh <url> <slug> --case C` | Chrome headless; the only path that creates EV items |
| + post media | `capture-evidence.sh ... --social` | yt-dlp / gallery-dl / auto-archiver (`AUTO_ARCHIVER_CONFIG`); additive |
| + ArchiveBox copy | `capture-evidence.sh ... --archivebox` | `ARCHIVEBOX_URL`, `ARCHIVEBOX_API_KEY`; additive |
| Monitor a page | `python3 scripts/watch.py add <url> --case C`, `watch.py poll --capture` | local diff, or changedetection.io (`CHANGEDETECTION_URL`) |
| Reddit history | `python3 scripts/reddit-arctic.py user <name> --case C` | Arctic Shift, PullPush, RSS (keyless) |

Wayback / archive.today submission is not part of capture (local-only mode). Wayback CDX
may be read for research; anything cited still goes through `capture-evidence.sh`.

---

## Exports

| Format | Command | Notes |
|---|---|---|
| STIX 2.1 / MISP / CSV | `python3 scripts/export-intel.py stix\|misp\|csv\|all --case C [--tlp amber]` | no extra deps (`stix2` only for optional validation) |
| Timeline HTML | `python3 scripts/render-timeline.py --case C [--timesketch]` | `--timesketch` also writes an importable CSV |
| Map HTML | `python3 scripts/render-map.py --case C [--csv FILE]` | EXIF/analyst points, not verified locations |
| Redacted copy | `python3 scripts/redact-pii.py <export.md>` | presidio if installed, else regex |
| Report with inline evidence | `python3 scripts/render-report.py <in.md> <out.md>` | fails on broken `[EV-NNNN]` |

---

## Optional services and setup

- `bash scripts/setup-tools.sh --list` -- every optional tool with installed/missing state.
- `bash scripts/setup-tools.sh --docker crawl4ai,changedetection,archivebox,spiderfoot,yente` -- services from `tools/docker-compose.yml` (profiles, localhost-only ports 11235, 5000, 8010, 5001, 8000). Timesketch: official compose only (link in the compose file).
- Optional MCP servers (not loaded): `tools/mcp-optional.json`.

---

## External tool catalog

Curated pointer list of external tools by category (Bellingcat toolkit, OSINT Framework,
awesome-osint): [tool-catalog.md](tool-catalog.md). Everything there is T3 until crosslinked.

---

## Apify Troubleshooting

When an Apify actor fails:
1. Check if it blocks API on free plan ("run through UI only" error)
2. Check input field names (profileUrls vs urls vs user_name — varies per actor)
3. Check run status: `bash scripts/apify.sh run-status <run_id>`
4. Search for alternatives: `bash scripts/apify.sh store-search "platform scraper"`
5. Try the free-tier variant (e.g., `clockworks/free-tiktok-scraper`)
6. Fall back to Bright Data: `bash scripts/brightdata.sh scrape "<url>"`

---

## Cost Reference

| Tool | Cost | Notes |
|------|------|-------|
| LinkedIn (Apify supreme_coder) | $0.005/profile | |
| Instagram (Apify) | free tier | Limited runs |
| TikTok (Apify clockworks) | $0.01-0.05/profile | free-tiktok-scraper = free |
| YouTube (Apify streamers) | $0.01/channel | |
| Google Maps (Apify compass) | $0.01/listing | |
| Contact enrichment | $0.01/URL | |
| Facebook pages (Apify) | $0.01/page | Personal profiles = Bright Data |
| Facebook personal (Bright Data) | per-request | Check account balance |
| Jina | free tier with key | |
| Parallel | free tier with key | |
| Brave | free (2000/month) | |
| **Budget rule** | **≤$0.50 without asking** | **>$0.50 ask user** |
