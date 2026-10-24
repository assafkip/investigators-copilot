---
name: osint
description: >
  Conduct deep OSINT research on individuals. Build full digital footprint, psychoprofile
  (MBTI/Big Five), career history, social graph with confidence scores. Recursive
  self-evaluation until completeness threshold is met. Includes internal intelligence
  (Telegram history, email, vault contacts) before going external.
  Use when: "osint", "досье", "research person", "find everything about", "пробей",
  "разведка", "due diligence", "background check", "digital footprint",
  "найди всё про", "собери информацию", "кто это", "профиль человека".
  NOT for: company/product research without a named person, competitive analysis,
  market research, content generation, or general web scraping tasks.
---

# OSINT Skill v3.2

Systematic intelligence gathering on individuals. From a name or handle to a scored
dossier with psychoprofile, career map, and entry points.

## Phase Router

Determine entry point from context:

- New name/handle/URL, "пробей", "find out about" → Phase 0 (full cycle)
- "Add LinkedIn/Instagram data" to existing dossier → Phase 2 (extraction)
- "Build psychoprofile" from existing data → Phase 4
- "Rate completeness" of existing dossier → Phase 5
- "Reformat" or "present" findings → Phase 6

Default (full research request): Phase 0 → 1 → 1.5 → 2 → 3 → 4 → 5 → 6.

## Environment

All API keys via environment variables. Never hardcode tokens.

- `PERPLEXITY_API_KEY` — Perplexity Sonar (fast answers + deep research)
- `EXA_API_KEY` — Exa AI (semantic search, company/people research, deep research)
- `TAVILY_API_KEY` — Tavily (agent-optimized search + extract, $0.005/req basic)
- `APIFY_API_TOKEN` — Apify scraping (LinkedIn, Instagram, Facebook)
- `JINA_API_KEY` — Jina reader/search/deepsearch
- `PARALLEL_API_KEY` — Parallel AI search
- `BRIGHTDATA_MCP_URL` — Bright Data MCP endpoint (full URL with token)
- `MCPORTER_CONFIG` — mcporter config path

Enrichment adapters (`scripts/osint-tool.py`, all optional; keyless paths work without them).
`python3 scripts/osint-tool.py --list` shows what each adapter is missing.
- Infra / reputation: `SHODAN_API_KEY` (else keyless InternetDB), `URLSCAN_API_KEY`, `OTX_API_KEY`, `GREYNOISE_API_KEY`, `ABUSEIPDB_API_KEY`, `VT_API_KEY` (ioc-reputation.py), `CERTSPOTTER_API_KEY`
- Records / sanctions: `OPENCORPORATES_API_KEY`, `OPENSANCTIONS_API_KEY` or `YENTE_URL` (local yente), `COURTLISTENER_API_TOKEN`
- Crypto: `ETHERSCAN_API_KEY`, `TRONGRID_API_KEY`
- Identity: `GITHUB_TOKEN`, `GITLAB_TOKEN`, `API_ID` + `API_HASH` + `PHONE_NUMBER` (+ `TELEGRAM_SESSION_DIR`) for telegram_phone; `OSINT_USERNAME_WORKERS`, `OSINT_USERNAME_SITE_TIMEOUT`
- /q-corp (`install-pp.sh`): `COMPANY_PP_CONTACT_EMAIL`, `COMPANIES_HOUSE_API_KEY`, `FEC_API_KEY_QUERY_AUTH`, `LDA_API_KEY`
- Images: `GOOGLE_VISION_API_KEY` (reverse-image.sh, /q-face Vision backend), `SEARCH4FACES_API_KEY`, `FACECHECK_API_KEY`, `SHADOWFINDER_CACHE`
- Intake NER: `GLINER_MODEL`; `LANGEXTRACT_API_KEY` or `GEMINI_API_KEY` + `LANGEXTRACT_MODEL` (langextract SENDS TEXT TO GEMINI -- not for client documents without approval)
- Services (`tools/docker-compose.yml`): `CRAWL4AI_URL` (default http://localhost:11235), `CRAWL4AI_API_TOKEN`, `CRAWL_MIN_CHARS`, `CHANGEDETECTION_URL` + `CHANGEDETECTION_API_KEY`, `ARCHIVEBOX_URL` + `ARCHIVEBOX_API_KEY`, `SPIDERFOOT_URL`, `AUTO_ARCHIVER_CONFIG`, `SOCIAL_TIMEOUT_SEC`
- Endpoint overrides: `OSINT_DOH_URL`, `OSINT_ETH_RPC_URL`, `OSINT_SOLANA_RPC_URL`, `OSINT_ENS_RESOLVER`, `OSINT_BLOCKSCOUT_URL`, `OSINT_CACHE_DIR`, `PD_HTTPX_BIN`
- Telegram harvest: `TGSPYDER_SRC`. Opt-in hooks: `Q_SCOPE_HOOK`, `Q_SCOPE_EXTRA`, `Q_BUDGET_HOOK`, `Q_BUDGET_FILE`, `Q_WORKSPACE` (see `scripts/hooks/README.md`)

Install optional tools: `bash scripts/setup-tools.sh --list` (then `--only <name>`, `--all`, `--docker <svc>`).

## Scripts

Run from skill dir: `bash scripts/<name>.sh`.
Each script validates env vars, exits with descriptive error + URL to get the key.

**Client-provided document intake (do this before any custom extraction script):**
- `ingest-client-document.sh <file> <slug> <document|screenshot_only> --case <case>` — registers a client-provided file as an EV-NNNN evidence item (SHA-256 + chain-of-custody). See `.claude/rules/evidence-capture-protocol.md`.
- `extract-intake.py --case <case>` — deterministic verbatim extraction (no LLM, no network) for everything in `investigation/intake/`. Handlers: PDF, DOCX, DOC, CSV, PNG/JPG/TIFF, EML. No `.md` handler yet (markdown intake is already plain text — copy verbatim into `evidence/extracted/<stem>/text.md` by hand if the pipeline guard needs it satisfied).
- `evidence-pipeline-guard.py` (wired as a hook) blocks writing/running a custom script under a case's `investigation/evidence/scripts/` until both of the above have run for that case's intake. A case-local extraction script should only exist for a genuinely new capability (e.g. platform-specific OCR, a non-portable OS-native OCR engine) — upstream anything generally useful into `extract-intake.py` instead of duplicating the scaffold per case (lesson from the 2026-07-21 extraction-dedup audit: 2 cases had reinvented Maltego-CSV classification, 5 more had reinvented file extraction).

**Search & Research:**
- `diagnose.sh` — run FIRST. Capability map of all tools.
- **Perplexity (first-pass default):** when operating through Claude, call the MCP tool `mcp__perplexity-ask__perplexity_ask` directly. It returns an AI answer with citations (equivalent to `sonar` mode). Use the shell script for `search` (ranked web results), `reason` (reconcile contradictions), and `deep` (long-form research) modes, or from bash pipelines.
- `perplexity.sh` — `search <query>` | `sonar <query>` (AI answer) | `reason <query>` (sonar-reasoning-pro, compare leads / reconcile contradictions) | `deep <query>` (deep research). Required by `first-volley.sh` and any bash-only pipeline.
- `tavily.sh` — `search <query>` (basic $0.005) | `deep <query>` (advanced) | `extract <url>`
- `exa.sh` — `search <query>` | `company <name>` | `people <name>` | `crawl <url>` | `deep <prompt>`
- `first-volley.sh "Name" "context"` — parallel search, all engines at once.
- `merge-volley.sh <outdir>` — deduplicate and merge first-volley results.

**Scraping:**
- `apify.sh` — `linkedin <url>` | `instagram <handle>` | `run` | `results` | `store-search`
- `run-actor.sh` — **universal Apify runner (55+ actors).** Embedded from [apify/agent-skills](https://github.com/apify/agent-skills).
  Quick answer: `bash scripts/run-actor.sh "actor/id" '{"input":"json"}'`
  Export: `bash scripts/run-actor.sh "actor/id" '{"input":"json"}' --output /tmp/out.csv`
- `jina.sh` — `read <url>` | `search <query>` | `deepsearch <query>`
- `parallel.sh` — `search <query>` | `extract <url>`
- `brightdata.sh` — `scrape <url>` | `scrape-batch` | `search` | `search-geo <cc>` | `search-yandex`

**Setup & diagnostics:**
- `diagnose.sh` -- keys, binaries, capabilities, and the `osint-tool.py` adapter summary (ready/missing/import errors).
- `setup-tools.sh` -- `--list` | `--only <name>[,<name>]` | `--all` | `--docker <svc>[,<svc>]` [`--dry-run`]. pipx/pip/go/cargo installs; system packages are printed, never sudo'd.
- `dead-hooks-lint.py` -- flags hooks in settings files whose script is missing.
- `mcp-client.py <mcp_url> --list-tools` -- list an MCP server's tools.

**Enrichment (adapters, every result carries its tier):**
- `osint-tool.py --list` | `osint-tool.py <slug> <query> [--mode M] [--json] [--case <case>|--save]` -- 54 adapters (infra, records, sanctions, crypto, identity, reputation). Table: `references/tools.md` "Enrichment adapters". Same adapters via MCP `osint-infra` tools `enrich` / `enrich_providers`.
- `identity-sweep.py <handle|email|phone> [--case <case>] [--only a,b] [--skip a,b]` -- every ready identity adapter on one value, merged, T3. Shortcut: `identity-lookup.sh sweep <value> [case]`.
- `identity-lookup.sh keybase|github|mastodon|leakcheck <query>` -- keyless single lookups.
- `reddit-arctic.py user|sub|thread <x> [--case <case>]` -- Reddit history: Arctic Shift, then PullPush, then RSS (reddit.com JSON 403s from servers).
- `install-pp.sh list|install|run <name> --case C -- <args>` -- printing-press public-records CLIs (SEC EDGAR, Form D, Companies House, FEC, LDA, FAA, EU tenders) for `/q-corp`.
- `ioc-reputation.py extracted/<doc>/iocs.json [--sources ...] [--out rep.csv]` -- reputation leads for extracted indicators (T3; exposes indicators to providers).

**Crawl, archive, watch:**
- `crawl.sh fetch <url> [--case C]` | `crawl.sh map <url> [--depth N]` -- crawl4ai, then Scrapling; fail-closed on empty/challenge pages. `map` uses katana.
- `capture-evidence.sh ... [--social] [--archivebox]` -- additive media download (yt-dlp / gallery-dl / auto-archiver) and ArchiveBox copy; never flips an item's status, never edits source.json.
- `watch.py add|list|poll|remove` -- page monitoring (local diff or changedetection.io) for `/q-watch`.

**Images & geo:**
- `reverse-image.sh <image|url> [--case C]` -- Google Vision web detection (`GOOGLE_VISION_API_KEY`).
- `shadowfinder.sh find|sun ... [--case C]` -- bellingcat ShadowFinder shadow-length geolocation.
- `face-search.py` -- `/q-face` pipeline (founder approval required; hits are T3).

**Intake, analysis, exports:**
- `extract-intake.py --case <case> [--ner gliner|langextract|spacy]` -- also writes `iocs.json`, `entities.json`, `exif.json` side files (T3 leads).
- `resolve-entities.py <csv/json ...> --out same_as.csv [--ftm out.jsonl]` -- entity resolution (splink or fallback).
- `validate-citations.py <report.md> --case <case>` -- link liveness (HEAD/GET) plus a check that the citing sentence's hard tokens appear in the captured EV item.
- `export-intel.py stix|misp|csv|all --case <case> [--tlp ...]` -- threat-intel exports.
- `render-timeline.py --case <case> [--timesketch]` -- HTML timeline (or Timesketch CSV).
- `render-map.py --case <case> [--csv FILE]` -- map of geotagged evidence.
- `redact-pii.py <file.md> [--engine auto|presidio|regex]` -- writes a redacted copy for `/q-export --redact`.
- `render-report.py`, `resolve-deliverable.py`, `findings-verify-hook.py` -- report rendering and pre-delivery checks (see `.claude/rules/`).

**Related skills (siblings of this one under `skills/`):**
- `geo-sleuth/` -- geolocate / chronolocate a photo, outputs routed into EV-NNNN items.
- `verification/` -- SIFT, C2PA provenance (`c2patool`), account authenticity, coordinated-behavior checks.
- `telegram-harvest/` -- no-LLM Telegram channel harvest to XLSX (`setup.sh` once, then `scripts/harvest.py`).
- `leak-record-classifier/`, `structured-analysis/` -- unchanged.

## Research Escalation Flow

**Принцип: от дешёвого к дорогому, от быстрого к глубокому.**

### Level 1: Quick Answers (секунды, ~$0.00)
Начни ВСЕГДА с этого. Получи быстрый контекст прежде чем копать.
Запускай ВСЕ параллельно:
```bash
# Perplexity (default: MCP tool, not the shell script)
#   Claude call: mcp__perplexity-ask__perplexity_ask with a structured prompt
#   (see "Prompt Templates" section — use the Entity Profile template, not ad-hoc "Who is X")
# Shell fallback (bash pipelines or when you need sonar explicitly):
#   bash skills/osint/scripts/perplexity.sh sonar "<structured prompt from Entity Profile template>"
# Brave Search — классический поиск
web_search "<Name> <company> <role>"
# Tavily — agent-optimized search с AI answer
bash skills/osint/scripts/tavily.sh search "<Name> <context>"
# Exa — семантический поиск + company/people research
bash skills/osint/scripts/exa.sh search "<Name> <context>"
bash skills/osint/scripts/exa.sh people "<Name>"
```
→ Получаешь: быстрые факты, ссылки, контекст.
→ Решение: достаточно? → Phase 6. Нужно больше? → Level 1.5.

### Level 1.2: Keyless records + identity sweep (free, run alongside Level 1)

Records first: a registry/DNS/CT/on-chain row is T1 and can carry a crosslink; a search hit cannot.
```bash
# Infra records (T1): RDAP/WHOIS, DNS over HTTPS, certificate transparency, ASN
python3 skills/osint/scripts/osint-tool.py rdap example.com --case <case>
python3 skills/osint/scripts/osint-tool.py doh example.com
python3 skills/osint/scripts/osint-tool.py crtsh example.com
python3 skills/osint/scripts/osint-tool.py certspotter example.com
# Company / court / sanctions records
python3 skills/osint/scripts/osint-tool.py gleif "Acme Corp"
python3 skills/osint/scripts/osint-tool.py courtlistener "Acme Corp"
python3 skills/osint/scripts/osint-tool.py ofac "Name"
# Identity: every ready identity adapter on a handle / email / phone (all T3)
python3 skills/osint/scripts/identity-sweep.py <handle|email|phone> --case <case>
# Reddit history (archive keeps deleted posts)
python3 skills/osint/scripts/reddit-arctic.py user <username> --case <case>
```
Tier reminder: every `osint-tool.py` / `enrich` result prints its tier. Reputation feeds,
username hits, face-search hits and scraped profiles are T3 and never count as crosslinks
(`.claude/rules/q-investigation.md`). `--case` saves `results.json` + `urls.tsv`; feed
`urls.tsv` to `capture-evidence.sh --batch` before citing anything.

### Level 1.5: Breach Intel (free, run before any social scraping)

**HudsonRock Cavalier** -- unauthenticated, instant, often CRITICAL. Run this immediately after Level 1 before spending a dollar on scraping.

```bash
# By domain (employees + third-party exposure)
curl -s "https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-domain?domain=target.com" | jq .

# By email (individual credential exposure)
curl -s "https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-email?email=user@target.com" | jq .

# Email-to-platform account lookup (holehe) -- FREE, no auth needed
# Checks 100+ platforms to see which have accounts registered to an email
# Install: pip install holehe --break-system-packages
# Use: holehe target@email.com
# [+] = registered  [-] = not registered  [x] = rate limited (inconclusive)
# Does NOT require the password. Does NOT trigger resets.
# Key for prior-identity investigations: run against all subject-confirmed emails
holehe target@email.com

# By URL (stealer log hits for a specific page)
curl -s "https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-url?url=https://target.com/login" | jq .
```

**Field interpretation:**
- `employees` -- internal credential exposure (employee machines infected by stealers)
- `users` -- customer/user credential exposure
- `third_parties` -- supply-chain exposure (vendors, contractors whose machines had target creds)
- `data.stealer_families` -- which malware families (Redline, Vidar, Raccoon, etc.)
- `data.dates_compromised` -- recency of the breach (fresh = high risk of active abuse)
- `data.employees_urls` -- exact internal URLs captured (shows depth of access)

**Severity mapping:**
- ≥10 employees exposed → **CRITICAL** (regardless of data age)
- 1-9 employees exposed → **HIGH**
- ≥1 end-user exposed → **MEDIUM**
- 0 hits + old mail MX (NXDOMAIN on `mail.target.com`) + current cloud MX → **CRITICAL SSO_EXPOSURE** (on-prem → cloud migration = password reuse window)

**HIBP domain check (complement to Cavalier):**
```bash
curl -s "https://haveibeenpwned.com/api/v3/breacheddomain/target.com" \
  -H "hibp-api-key: ${HIBP_API_KEY}" | jq .
```

→ Cavalier hit? Document severity, log to `investigation/findings/breach-intel.md`, continue to Level 2.
→ No hit? Still run Level 2 -- stealers don't catch everything.

### Level 1.6: Identity & Leak Lookups (free, no key, run alongside Level 1.5)

Keyless public APIs -- no scraping, no captcha risk. Cheap enough to run on every target as a matter of course.

```bash
# Keybase -- cryptographically signed social proofs (T2-grade: the proof
# is signed by the linked account, not a name-match guess)
bash skills/osint/scripts/identity-lookup.sh keybase "<username>"

# GitHub -- profile often leaks real email/location for technical targets
bash skills/osint/scripts/identity-lookup.sh github "<username>"

# Mastodon -- federated search (mastodon.social vantage point only)
bash skills/osint/scripts/identity-lookup.sh mastodon "<name or handle>"

# LeakCheck public tier -- low-rate credential exposure check, complements
# HudsonRock Cavalier above
bash skills/osint/scripts/identity-lookup.sh leakcheck "<email>"
```

→ Hits here are still T3 hypotheses until crosslinked per the evidence-tier rules -- a signed Keybase proof or a GitHub-listed email is a strong crosslink candidate; a Mastodon display-name match alone is not.

### Level 2: Source Verification (секунды-минуты, ~$0.01)
Проверяй источники из Level 1 через fetch:
```bash
# Читай найденные URL
web_fetch "<url_from_perplexity>"
bash skills/osint/scripts/jina.sh read "<url>"
bash skills/osint/scripts/parallel.sh extract "<url>"
```
→ Получаешь: подтверждённые факты, cross-reference.
→ Совпадает? → дополняй досье. Нужно глубже? → Level 3.

### Level 3: Social Media Deep Dive (~$0.01-0.10)
Подключай scraping для соцсетей:
```bash
# LinkedIn
bash skills/osint/scripts/apify.sh linkedin "<url>"
# Instagram
bash skills/osint/scripts/apify.sh instagram "<handle>"
# Facebook, заблокированные сайты
bash skills/osint/scripts/brightdata.sh scrape "<url>"
```
→ Получаешь: структурированные профили, фото, связи.

### Level 4: Deep Research (~$0.05-0.50)
Если нужно копать ещё глубже — формируй развёрнутый промпт и отправляй в deep research.
Запускай ВСЕ параллельно (30-60 сек каждый):
```bash
# Perplexity Deep Research — use a template from "Prompt Templates" section
bash skills/osint/scripts/perplexity.sh deep "<filled-in Entity Profile or Network Mapping template>"
# Perplexity Reasoning — reconcile contradictions surfaced in Level 1-3
bash skills/osint/scripts/perplexity.sh reason "<filled-in Contradiction Reconciliation template>"
# Exa Deep Research
bash skills/osint/scripts/exa.sh deep "<detailed prompt>"
# Parallel AI Deep Search
bash skills/osint/scripts/parallel.sh search "<detailed query>"
# Jina DeepSearch
bash skills/osint/scripts/jina.sh deepsearch "<query>"
```

**Правило:** Level 4 промпт должен быть РАЗВЁРНУТЫМ — включай всё что уже знаешь
из Level 1-3, чтобы deep research не повторял базовые факты, а копал дальше.

## Prompt Templates (Perplexity MCP / shell)

Every OSINT query to Perplexity (`mcp__perplexity-ask__perplexity_ask`, `perplexity.sh sonar|reason|deep`) must follow the 5-part pattern. Ad-hoc queries produce summary blobs; structured queries produce source-anchored tables we can route to `investigation/findings/`.

### 5-part pattern
- **Objective:** what we're trying to determine
- **Entities:** names, aliases, domains, companies, handles, locations
- **Time window:** current / last 30 days / since YYYY-MM-DD
- **Source types:** public web, social, filings, archived pages, forums; exclude aggregators
- **Output:** table, timeline, confidence levels, direct URLs

### Reusable templates

**Entity profile** (mode: `deep` or `sonar`)
```
Use public sources only to profile <TARGET>. Identify associated social profiles,
domains, companies, locations, and public activity since <DATE>. Prioritize primary
sources (social, filings, forums); exclude news aggregators and obvious duplicates.
Output: table with source URL, evidence snippet, date, confidence (high/medium/low),
followed by a timeline of key events. End with "what is missing or weakly supported?"
```

**Network mapping** (mode: `deep`)
```
Map connections between <ENTITY_A> and <ENTITY_B>. Find shared infrastructure,
co-mentions, emails, social links, funding ties from public sources (GitHub, LinkedIn,
WHOIS, SEC filings) in the last 2 years. Return a table: nodes, edges, source URLs,
link strength (strong/moderate/weak/speculative); highlight contradictions.
```

**Event timeline** (mode: `deep`)
```
Reconstruct the timeline of <EVENT> from public mentions on forums, social, blogs,
and official statements since <DATE>. Focus on IOCs, affected parties, responses.
Output: chronological table (date, source URL, key fact, credibility grade). End
with a "gaps in evidence" list and suggested follow-up queries.
```

**Infrastructure recon** (mode: `deep`)
```
Enumerate public-facing infrastructure for <DOMAIN_OR_IP>: subdomains, hosting
provider, tech stack, linked domains, certificates, and changes since <DATE>.
Pull from Shodan/Censys/VirusTotal/CT-log-style public data. Output: table with
asset, details, source URL, last observed; end with an exposure risk assessment.
```

**Geolocation** (mode: `sonar` or `deep`)
```
Find public geolocation signals for <TARGET>. Correlate images, posts, metadata,
check-ins from Instagram/X/Telegram since <DATE>. Privacy-compliant sources only.
Output: table with estimated lat/long, source URL, confidence; note any conflicting
locations.
```

**Contradiction reconciliation** (mode: `reason`)
```
I have these conflicting claims about <TARGET>:
1. <CLAIM_A> (source: <URL_A>)
2. <CLAIM_B> (source: <URL_B>)
Reason step-by-step about which is more likely correct, what additional evidence
would resolve the conflict, and what the most plausible combined narrative is.
Output: assessment, confidence, missing evidence, recommended next queries.
```

### Routing rules
- All URLs surfaced by Perplexity go through `bash skills/osint/scripts/capture-evidence.sh` before being cited in any brief or report.
- Map Perplexity confidence (high/medium/low) to our A-F source reliability scale when writing to `investigation/findings/`.
- `reason` mode output is the preferred input to `/analyze ach` when reconciling contradictions.

## Default Perplexity entry point: `perplexity-playbook.sh`

For the first research pass on any target, run the playbook rather than crafting ad-hoc `sonar` calls. The playbook runs a fixed, target-type-specific query set in parallel, then merges citations with URL normalization and dedupe into a reproducible run directory.

```bash
# Target types: person | company | domain | incident
bash skills/osint/scripts/perplexity-playbook.sh person "jane-doe" "Jane Doe, CEO Acme"
bash skills/osint/scripts/perplexity-playbook.sh domain "acmecorp-com" "acmecorp.com"

# Fully automated pass: playbook -> capture -> persist to active case
bash skills/osint/scripts/perplexity-playbook.sh company "acme-inc" "Acme Inc" \
  --capture --case case-001-example
```

Output lives at `/tmp/osint-<slug>-<ISO8601>/`: `evidence.json` (merged citations), `urls.txt`, `urls.tsv` (batch input for `capture-evidence.sh`), `report.md`, `run_manifest.json`. With `--case`, artifacts are copied to `investigations/<case>/investigation/evidence/raw-collections/`.

**Use `perplexity.sh` modes directly only for follow-up queries outside the target-type doctrine** (e.g., `reason` for contradiction reconciliation, `deep` for a specific Level 4 deep dive). The playbook is the default so that first-pass research is uniform, auditable, and parallel.

## Swarm Mode (DEFAULT)

OSINT research runs as a **swarm of parallel sub-agents on Sonnet**.
The main agent is the coordinator — it does NOT scrape itself.

### How it works:
1. Main agent runs Phase 0 (tooling check) and Phase 1 (seed collection) to get initial context
2. Main agent spawns 3-5 sub-agents via `sessions_spawn` with `model: sonnet`, `mode: run`
3. Each sub-agent gets a focused task + all known data from Phase 1
4. Sub-agents return results → main agent merges into dossier

### Task split pattern:
- **Agent 1: YouTube/Content** — extract transcripts via Apify (NOT yt-dlp, NOT BrightData — YouTube blocks them). 3-5 videos, speech style, topics. Use `streamers/youtube-channel-scraper` for channel data
- **Agent 2: Facebook deep** — BrightData scrape: profile, posts, about, photos, friends (use m.facebook.com for more data). For public Pages: `apify/facebook-pages-scraper` + `apify/facebook-page-contact-information`
- **Agent 3: Social platforms** — Instagram (Apify + tagged/comments scrapers), DOU, company websites, LinkedIn (BrightData). Contact enrichment: `vdrmota/contact-info-scraper` on found websites
- **Agent 4: TikTok + Regional** — TikTok profile/videos (`clockworks/tiktok-profile-scraper`), local registries, press, university records, Yandex search, Google Maps (`compass/crawler-google-places` if business owner)
- **Agent 5: Deep research** — Perplexity deep, Exa deep, Parallel deep (if needed)

### Rules:
- Always pass ALL known data to each sub-agent (names, URLs, emails, phones, context)
- Each sub-agent saves results to `/tmp/osint-<subject>-<task>.md`
- Main agent waits for all results, then runs Phase 3-6 (cross-reference, psychoprofile, dossier)
- Budget: each sub-agent ≤$0.15, total swarm ≤$0.50
- YouTube transcripts: use **Apify** actors, NOT BrightData or yt-dlp (both blocked by YouTube)

### Why swarm:
- 5 agents × 5 min = 10 min total (vs 30+ min sequential)
- Sonnet is 5x cheaper than Opus
- Parallel scraping avoids rate limit stacking on single IP

---

## Phase 0: Tooling Self-Check

1. Execute `bash skills/osint/scripts/diagnose.sh`.
2. Log available vs missing tools.
3. Check internal tools: `tg.py` (Telegram history), `himalaya` (email), vault contacts.
4. If Bright Data unavailable → Facebook and LinkedIn deep scrape limited. Inform user.
5. If Apify unavailable → Instagram and LinkedIn structured data limited.
6. Proceed with available toolset.

## Phase 1: Seed Collection

**Start with Level 1 (quick answers) ALWAYS before heavy scraping.**

1. Parse user input. Extract identifiers: names, handles, URLs, companies, locations.
2. **Perplexity fast pass (default first-pass OSINT):**
   - Claude orchestration: call MCP tool `mcp__perplexity-ask__perplexity_ask` with the question. Returns AI answer + citations in-session.
   - Bash pipeline fallback: `bash skills/osint/scripts/perplexity.sh search "Who is <Name>, <context>"` (ranked web results) or `sonar` (AI answer).
3. **Brave + Parallel in parallel:**
   ```bash
   web_search "<Name> <company>"
   bash skills/osint/scripts/first-volley.sh "Full Name" "context"
   ```
4. **Review Perplexity citations** — fetch and verify top sources:
   ```bash
   web_fetch "<citation_url_1>"
   web_fetch "<citation_url_2>"
   ```
5. Parse & merge: `bash skills/osint/scripts/merge-volley.sh /tmp/osint-<timestamp>`.
6. Collect all identifiers into seed list. Deduplicate.
7. Flag name collisions (common names → verify with company/location cross-reference).
8. **Decision point:** enough context? → skip to Phase 4. Need social media? → Phase 2. Need deep dive? → Level 4 (deep research).

**Rate limiting:** wait 1s between Brave queries, 2s between Jina calls.
Do NOT hammer APIs in tight loops — stagger parallel launches.

## Phase 1.5: Internal Intelligence

**Before going external, check what we already know.** This phase mines local sources
that may contain gold — prior conversations, emails, vault contacts.

### Telegram History
If `tg.py` is available (check Phase 0):
```bash
# Search by name/handle in Telegram
python3 skills/telegram/scripts/tg.py search "Name" 20
# If we have their username/id — read conversation history
python3 skills/telegram/scripts/tg.py history <username_or_id> 50
```

**What to extract from Telegram history:**
- Communication style (formal/informal, language, emoji patterns)
- Topics discussed — what they care about, what they ask for
- Response patterns — reply speed, active hours → timezone
- Shared links/files — projects they work on
- How they address the user — relationship dynamics
- Mentioned colleagues, partners, competitors → social graph seeds
- Pricing discussions, deal terms (if business contact)

⚠️ **Telegram history is Grade A intelligence** — unfiltered, real-time, authentic.
Weight it higher than curated LinkedIn/Instagram profiles.
⚠️ **Privacy:** internal intelligence stays in the dossier. Never quote DMs in public outputs.

### Email History
If `himalaya` is available:
```bash
# Search emails by name or domain
~/.local/bin/himalaya search "from:name@domain.com OR to:name@domain.com" -f INBOX
# Or by name
~/.local/bin/himalaya search "Name Surname" -f INBOX
~/.local/bin/himalaya search "Name Surname" -f Sent
```

**What to extract from email:**
- Formal communication style vs Telegram style (contrast = insight)
- Business proposals, invoices → financial relationship
- CC'd people → organizational map
- Signature block → title, phone, company, social links (often richer than LinkedIn)

### Vault / CRM Check
```bash
# Check if we already have a card
grep -rl "Name" vault/crm/ vault/contacts/ 2>/dev/null
# Check MOC indexes (adjust paths to your vault structure)
grep -i "name" vault/MOC/*.md 2>/dev/null
```

**If vault card exists:** read it, note last_accessed, existing tags, prior interactions.
Don't duplicate — enrich the existing card after research completes.

### Node Camera/Location (if paired device available)
If meeting in person and node is available, `nodes camera_snap` can capture context.
Only with explicit user permission.

### Internal Intelligence Summary
After Phase 1.5, you should know:
- Do we have prior relationship? (cold/warm/hot contact)
- What language do they prefer?
- What's their communication style?
- Any existing business context?
- Social graph seeds from conversations

This context shapes Phase 2 priorities — if we already know their career from emails,
focus external research on psychoprofile and social media instead.

## Phase 2: Platform Extraction

Read `references/platforms.md` ONLY when needing URL patterns or extraction signals.

Tool priority (primary → fallback). **If primary fails, switch immediately. Never retry same tool.**

- LinkedIn: `apify.sh linkedin` → `brightdata.sh scrape` → `jina.sh read`
- Instagram: `apify.sh instagram` → `brightdata.sh scrape`
- Instagram deep: `run-actor.sh "apify/instagram-tagged-scraper"` (who tags them), `apify/instagram-comment-scraper` (sentiment)
- Facebook personal: `brightdata.sh scrape` → none (only Bright Data works)
- Facebook pages/groups: `run-actor.sh "apify/facebook-pages-scraper"` → `brightdata.sh scrape`
- TikTok: `run-actor.sh "clockworks/tiktok-profile-scraper"` → `clockworks/tiktok-scraper` (comprehensive)
- TikTok discovery: `run-actor.sh "clockworks/tiktok-user-search-scraper"` (find by keywords)
- YouTube: `run-actor.sh "streamers/youtube-channel-scraper"` → `jina.sh read` → `brightdata.sh scrape`
- Telegram channels: `web_fetch t.me/s/{channel}` → `jina.sh read`
- Twitter/X: `python3 scripts/twitter.py tweet <url>` → `jina.sh read`
- Google Maps (businesses): `run-actor.sh "compass/crawler-google-places"`
- Contact enrichment: `run-actor.sh "vdrmota/contact-info-scraper"` (extract emails/phones from any URL)
- Any site: `jina.sh read` → `brightdata.sh scrape`

**run-actor.sh** = universal Apify runner (embedded, 55+ actors). See `references/tools.md` for full actor catalog.

Read `references/tools.md` ONLY when troubleshooting a failed tool.

### ⚠️ Content Platform Rule (CRITICAL)

When you find YouTube, podcast, blog, or conference talks — read `references/content-extraction.md` **immediately** and extract 3-5 pieces of content on the spot.

Do NOT just note the URL. Extract transcripts/text NOW.
A 20-minute YouTube video reveals more about a person than their entire LinkedIn.
Content platforms are the #1 source for psychoprofile — skipping them = shallow dossier.

### Email Harvest

Run in parallel across all 6 sources. Do NOT rely on a single source.

```bash
# 1. IntelX phonebook (paid, highest yield for corporate domains)
curl -s "https://2.intelx.io/phonebook/search" \
  -H "x-key: ${INTELX_API_KEY}" \
  -d '{"term":"target.com","buckets":[],"lookuplevel":0,"maxresults":100,"timeout":0,"datefrom":"","dateto":"","sort":4,"media":0,"terminate":[]}' | jq .

# 2. Hunter.io (free tier: 25/mo, paid for bulk)
curl -s "https://api.hunter.io/v2/domain-search?domain=target.com&api_key=${HUNTER_API_KEY}" | jq '.data.emails[].value'

# 3. crt.sh SAN extraction (free, no auth)
curl -s "https://crt.sh/?q=%25@target.com&output=json" | jq -r '.[].name_value' | grep '@' | sort -u

# 4. DuckDuckGo SERP scrape
bash skills/osint/scripts/perplexity.sh search "site:target.com email OR contact filetype:html"

# 5. Wayback CDX email harvest (free)
curl -s "http://web.archive.org/cdx/search/cdx?url=*.target.com/*&output=json&fl=original&filter=statuscode:200&collapse=urlkey" \
  | jq -r '.[][0]' | grep -Eo '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}' | sort -u

# 6. Bright Data SERP (catches what DDG misses)
bash skills/osint/scripts/brightdata.sh search '"@target.com" email contact'
```

**Email pattern inference** -- after harvest, infer the domain's naming convention:

Candidate templates to test (mark each TENTATIVE until Hunter.io or 2+ live addresses confirm):
```
firstname@           lastname@           f.lastname@
firstname.lastname@  firstnamelastname@  flastname@
firstname_lastname@  f_lastname@
```

**Rules:**
- Extract dominant pattern from Hunter.io `pattern` field if available -- it overrides inference
- Discard addresses with numeric-only local parts (spam traps)
- Filter regex: `^[a-zA-Z][a-zA-Z0-9._%+-]{1,}@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`
- If 3+ harvested addresses match one template → mark template FIRM, generate candidates for known names
- Cross-reference all harvested emails against Cavalier (Level 1.5) for breach exposure

**Output:** write to `investigation/targets/[org]-emails.md` with source, confidence (TENTATIVE/FIRM/CONFIRMED), and Cavalier hit status per address.

### OpSec-Aware Targets

If initial searches return unusually little for someone who should have a footprint:

1. **Wayback Machine:** `web_fetch "https://web.archive.org/web/2024*/target-url"` — deleted profiles, old bios
2. **Google Cache:** `web_search "cache:domain.com/path"` — recently removed pages
3. **Yandex Cache:** `brightdata.sh search-yandex "Name"` — Yandex indexes CIS deeper and caches longer
4. **Username variations:** try transliteration (Иванов → ivanov, ivanoff), birth year suffixes, company abbreviations
5. **Reverse image search:** if photo found, check for other profiles using same avatar
6. **Conference archives:** speaker bios often survive after profiles are deleted

## Phase 3: Cross-Reference & Confidence Scoring

### Step 1: Fact Table
List every claim as a row: fact | source 1 | source 2 | grade.

### Step 2: Cross-check key facts
For each critical fact (employer, role, location, education):
- Compare LinkedIn title vs Telegram signature vs email signature vs company website
- If 2+ match → Grade A
- If only 1 source → Grade B
- If inferred (timezone from messages, geotag) → Grade C
- If single unverified mention → Grade D

### Step 3: Resolve contradictions
If LinkedIn says "CEO" but company site says "Co-founder" — flag explicitly. Include both with sources. Do NOT silently pick one.

### Step 4: Name collision check
If common name — verify at least 2 facts (company + city, or photo + company) link to same person. If unsure, split into separate entities.

### Confidence grades (source-level):

- **A (confirmed)**: 2+ independent sources, or official/verified profile, or direct Telegram/email conversation
- **B (probable)**: 1 credible source (LinkedIn, official media, company site)
- **C (inferred)**: indirect evidence (photo geotag, timezone from message patterns, connections)
- **D (unverified)**: single mention, could be wrong

Internal intelligence (Phase 1.5) counts as an independent source.

### Asset confidence (claim-level) -- TENTATIVE / FIRM / CONFIRMED

Track individual claims separately from source grades. A single A-grade source can establish FIRM; two independent sources establish CONFIRMED.

| Asset type | TENTATIVE | FIRM | CONFIRMED |
|------------|-----------|------|-----------|
| Email address | Found in 1 source, unvalidated | Pattern matches domain convention OR Hunter.io confirms | SMTP verify passes OR Cavalier hit OR direct reply |
| Domain / subdomain | DNS resolves | HTTP 200 response | Active service + cert SAN match |
| Person identity | Name match only | Name + photo OR name + employer | Name + photo + 2nd identifier (DOB, location, contact) |
| Employment | 1 source (LinkedIn self-reported) | LinkedIn + company site OR press mention | Official filing OR payroll-adjacent (email domain + badge) |
| Location | IP geolocation or single mention | 2 independent geolocations OR Telegram timezone match | Direct confirmation or flight/hotel record |
| Breach exposure | Cavalier 1-4 employees hit | Cavalier ≥5 employees OR HIBP domain breach | Fresh stealer data (<6 months) + active credential validation |
| Social account | Handle found | Handle + profile data extracted | Handle + account activity + cross-platform ID match |

**Upgrade rules:**
- TENTATIVE → FIRM: add one corroborating source of a different type (not just a second scrape of the same platform)
- FIRM → CONFIRMED: direct validation (live check, file download, reply received) OR 3+ independent sources
- Never cite a TENTATIVE claim in a client brief without explicit uncertainty labeling
- TENTATIVE claims that cannot be upgraded after 2 collection attempts → flag as COLLECTION GAP in `investigation-state.md`

**How source grade and asset confidence relate:**
- Source grade (A-D) describes how reliable the source is
- Asset confidence (TENTATIVE/FIRM/CONFIRMED) describes how certain we are about the specific claim
- A D-grade source can still upgrade an asset to FIRM if it independently corroborates a TENTATIVE claim from an A-grade source

## Phase 4: Psychoprofile

Read `references/psychoprofile.md` ONLY at this phase.

1. Collect text samples: posts, bios, interviews, channel content, **Telegram messages** (highest signal).
2. Assess MBTI per dimension with cited behavioral evidence and confidence (high/medium/low).
3. Quantify writing style: sentence length, emoji density, self-reference rate.
4. **Compare formal (LinkedIn/email) vs informal (Telegram/Instagram) voice** — the delta reveals the real person.
5. Deduce values from actions, not self-reported claims.
6. Zodiac ONLY if DOB confirmed (Grade A or B).

## Phase 5: Completeness Evaluation (Recursive)

### Axis 1: Data Coverage (pass/fail per dimension)

9 mandatory checks. If any fail, flag as critical gap:

1. Subject correctly identified? (not a namesake)
2. Current role/company confirmed?
3. At least 2 social platforms found?
4. At least 1 contact method (email/phone/messenger)?
5. Career history has 2+ verifiable positions?
6. Location (current) established?
7. At least 1 photo found?
8. No unresolved contradictions between sources?
9. Internal intelligence checked? (Telegram/email/vault — even if empty)

### Axis 2: Depth Score (8 weighted criteria)

| Dimension | Weight | What to score (1-10) |
|-----------|--------|---------------------|
| Identity | 0.15 | Full name, DOB, location, education, photo |
| Career | 0.20 | Completeness of work history, current role clarity |
| Digital footprint | 0.15 | Number of platforms found, account activity level |
| Psychoprofile | 0.15 | MBTI confidence, writing style quantified, values deduced |
| Internal intel | 0.10 | Telegram/email history depth, vault data |
| Personal life | 0.05 | Family, hobbies, lifestyle, pets |
| Cross-reference | 0.10 | How many facts are A-grade, contradiction count |
| Actionability | 0.10 | Entry points identified, approach strategy clear |

Weighted sum (1-10) = **Depth Score**.

### Axis 3: Source Diversity

Count unique source types used (max 12):
LinkedIn, Instagram, Facebook, Telegram DM, Telegram channel, VK, Twitter/X,
company website, press/media articles, conference profiles, government/business registries,
email correspondence.

- 8+ source types = Excellent
- 5-7 = Good
- 2-4 = Shallow
- 1 = Insufficient

### Gap Analysis

| Depth Score | Coverage | Diagnosis | Action |
|------------|----------|-----------|--------|
| 8+ | All pass | Strong dossier | Proceed to Phase 6 |
| 8+ | Some fail | Deep but blind spots | Target failed checks, 1 more cycle |
| <7 | All pass | Wide but shallow | Deepen via interviews/articles/deepsearch |
| <7 | Some fail | Restart needed | Different search angle, new tool combination |

### Stopping Criteria

**(a)** Depth Score ≥ 8.0 AND all coverage checks pass → exit to Phase 6
**(b)** 3 cycles completed → deliver best available with honest assessment
**(c)** Two cycles with delta < 0.5 → plateau reached, deliver with note

### Calibration Benchmarks

- **9-10**: full career timeline, 5+ platforms, confirmed DOB, psychoprofile with high confidence, family/hobbies known, multiple entry points, Telegram history analyzed. Equivalent to a professional PI report.
- **7-8**: career outline, 3+ platforms, most facts B-grade or above, psychoprofile with medium confidence. Solid due diligence.
- **5-6**: basic bio, 1-2 platforms, some gaps. Quick background check level.
- **<5**: minimal data found. Name + current role at best. Flag as insufficient.

## Phase 6: Dossier Output

Read `assets/dossier-template.md` before rendering. Follow the template structure exactly.
No markdown tables in output (Telegram cannot render). Bullet lists only.
Report Depth Score, source count, source types, and total API spend.

If internal intelligence was used, add a separate **"из переписки"** section
(marked as internal/confidential, not for sharing outside).

## Budget

- ≤$0.50 per target: spend without asking.
- >$0.50: ask user before proceeding.
- Track cumulative spend per research session.

## Troubleshooting

- **All tools return empty**: target has minimal digital presence. Try Bright Data Yandex search (better for CIS region), search by company + role instead of name.
- **Wrong person keeps appearing**: add company name, city, or role to all queries. Use quotes around full name.
- **LinkedIn blocked**: use `brightdata.sh scrape` as primary instead of Apify.
- **Apify actor dead/changed**: check `apify.sh store-search "linkedin scraper"` for alternatives. Actors on Apify are volatile — always have a Bright Data fallback.
- **Depth Score stuck at 6-7**: likely missing press/media articles or internal intel. Search industry publications (AdIndex, Sostav, Forbes, Kommersant for Russian market). Try `jina.sh deepsearch`. Check Telegram history.
- **No social media found**: person may use pseudonyms. Search by email, phone, or company employee page. Search Apify store: `bash scripts/apify.sh store-search "people search"`. If `mcpc` installed: `APIFY_TOKEN=$APIFY_API_TOKEN mcpc --json mcp.apify.com --header "Authorization: Bearer $APIFY_TOKEN" tools-call search-actors keywords:="people search" limit:=10`. Check Telegram contacts by phone.
- **TikTok scraper fails**: try `clockworks/free-tiktok-scraper` (free tier) as fallback. TikTok usernames often differ from other platforms — search by real name via `clockworks/tiktok-user-search-scraper`.
- **Need emails from website**: use `vdrmota/contact-info-scraper` — it crawls the site and extracts all contact info.
- **Rate limited (429)**: back off 5s, then 15s. Switch to fallback tool. Never retry immediately.

## Meta Ad Library Hidden API Collection

Use `scripts/meta-ad-library-hidden-api.sh` when Meta Ad Library pages expose public ad data in the browser but Apify actors return empty results. This is for public Ad Library data only. Do not store cookies, session headers, `fb_dtsg`, `lsd`, bearer tokens, or browser profile material in the repo.

### Setup

```bash
brew install go
git clone https://github.com/mvanhorn/cli-printing-press /tmp/cli-printing-press
(cd /tmp/cli-printing-press && go build -o "$HOME/go/bin/cli-printing-press" ./cmd/cli-printing-press)
```

### Capture request shape

1. Open the target ad in a logged-in Chrome session:
   `https://www.facebook.com/ads/library/?id=<AD_ID>`
2. Export a HAR from Chrome DevTools after the ad details load.
3. Run Printing Press over the HAR:

```bash
bash scripts/meta-ad-library-hidden-api.sh \
  --case case-001-example \
  --sniff-har /path/to/meta-ad-library.har
```

4. Convert the discovered Ad Library request into `config/meta-ad-library/request-template.json`.
5. Set `status` to `ready`. The `replay.command` array must write raw JSON to stdout and may use:
   - `{{AD_ID}}` for the current ad ID
   - `{{ENV:NAME}}` for required environment variables held outside git

### Replay and evidence routing

```bash
bash scripts/meta-ad-library-hidden-api.sh \
  --case case-001-example \
  2346460479208627 1798738457767270
```

Outputs are written to `investigations/<case>/investigation/evidence/raw/meta-ad-library-hidden-api/`:

- `<ad_id>-raw.json` -- raw hidden API response
- `<ad_id>-normalized.json` -- stable Q evidence fields
- `run-manifest.json` -- timestamp, ad IDs, status, reason, and paths
- `investigation/findings/F-010-facebook-ad-attribution.md` -- created only when advertiser or page identity is recovered

### CDP search

Use this when the question starts from a suspicious landing domain, scam phrase, or advertiser/page label and US Meta Ad Library API coverage is not enough.

```bash
bash scripts/meta-ad-library-hidden-api.sh \
  --case case-001-example \
  --cdp-search-domain example-shop.com

bash scripts/meta-ad-library-hidden-api.sh \
  --case case-001-example \
  --cdp-search-keyword "cat eye colorful seeds"

bash scripts/meta-ad-library-hidden-api.sh \
  --case case-001-example \
  --cdp-search-advertiser "FlowerSeed Shop"
```

This launches isolated Chrome with a temporary profile, searches public US Ad Library UI results for the domain, captures rendered DOM text plus relevant network metadata, and removes the temporary browser profile at the end.

Additional outputs:

- `<mode>-<query>-raw.json` -- query-level raw capture references and parsed ads
- `<mode>-<query>-normalized.json` -- normalized advertiser/page, landing URLs when available, Library IDs, status, dates, and creative text
- `cdp-capture/<mode>-<query>-dom.txt` -- rendered DOM evidence
- `cdp-capture/<mode>-<query>-network-index.json` -- network response metadata without request headers
- `cdp-capture/<mode>-<query>-network-body-*.json` -- selected redacted JSON/text response bodies when CDP exposes them

Domain mode records the searched domain as `landing_url_source=query_domain` when the rendered card does not expose a destination URL. Keyword and advertiser modes only record landing URLs when the UI or captured response body exposes them.

### Printing Press capture

Use this to turn the same isolated CDP search into a sanitized HAR and Printing Press analysis artifacts:

```bash
bash scripts/meta-ad-library-hidden-api.sh \
  --case case-001-example \
  --printing-press-capture \
  --cdp-search-domain example-shop.com
```

Additional outputs:

- `printing-press/<mode>-<query>-sanitized.har` -- HAR with cookies, auth headers, token-like headers, and token-like body values removed
- `printing-press/<mode>-<query>-spec.yaml` -- Printing Press browser-sniff spec
- `printing-press/<mode>-<query>-analysis.json` -- endpoint analysis sidecar
- `printing-press/<mode>-<query>-samples/` -- redacted endpoint samples
- `printing-press/<mode>-<query>-capture-summary.json` -- Q summary with replay still marked blocked until manual validation

Do not set `config/meta-ad-library/request-template.json` to `status=ready` from capture alone. Only mark it ready after a sanitized replay command is validated and writes JSON without storing session material.

Current replay readiness, 2026-06-26:

- `--printing-press-capture --cdp-search-domain example-shop.com` completed.
- Printing Press produced a spec, analysis, samples, and sanitized HAR.
- The captured endpoints were `/ads/library/` HTML plus low-confidence `/ajax/qm/` and `/ajax/bz` calls.
- No validated JSON ad-data replay endpoint was found.
- `request-template.json` must remain `status=needs_capture`.

Replay can be marked ready only when a sanitized command writes JSON evidence to stdout, contains advertiser/page/creative/landing/status fields, and works without cookies, auth headers, `fb_dtsg`, `lsd`, bearer tokens, or browser profile material.

### CDP detail capture

Use this when you already have visible Library IDs and need deeper per-ad evidence:

```bash
bash scripts/meta-ad-library-hidden-api.sh \
  --case case-001-example \
  --cdp-detail 2004513076810141 4027982630835003
```

This opens each public Ad Library detail URL directly:

```text
https://www.facebook.com/ads/library/?id=<LIBRARY_ID>
```

Detail outputs:

- `<library_id>-detail-raw.json` -- detail capture, sanitized links, parsed fields, and artifact paths
- `<library_id>-detail-normalized.json` -- advertiser/page, creative, landing URLs, dates, status, page URLs, transparency links, page ID hints, and missing fields
- `cdp-capture/<library_id>-detail-dom.txt` -- rendered detail DOM evidence
- `cdp-capture/<library_id>-detail-network-index.json` -- sanitized network metadata
- `cdp-capture/<library_id>-detail-network-body-*` -- selected redacted response bodies when CDP exposes them

`--printing-press-capture` may be combined with `--cdp-detail`, but replay remains blocked until a validated hidden JSON endpoint is found.

### CDP page/entity pivot

Use this after detail capture recovers Facebook page or page-filter IDs:

```bash
bash scripts/meta-ad-library-hidden-api.sh \
  --case case-001-example \
  --cdp-page 61575232177183 654188471104939
```

This opens the public Facebook page URL and Ad Library page-filter URL for each ID, then writes:

- `<page_id>-page-raw.json` -- captured sources, links, parsed fields, and artifact paths
- `<page_id>-page-normalized.json` -- page name, page URLs, websites, page ID hints, visible Library IDs, count/transparency text, and business entity when visible
- `cdp-capture/<page_id>-page-dom.txt` -- rendered public page and Ad Library page-filter DOM evidence
- `cdp-capture/<page_id>-page-network-index.json` -- sanitized network metadata

Do not claim legal/business entity attribution unless the normalized output contains visible evidence for it.

### Failure modes

- Template missing or `status != ready`: fail-stop with `run-manifest.json` status `blocked`.
- Replay command exits non-zero: fail-stop and do not write attribution.
- Empty or non-JSON response: fail-stop and do not write attribution.
- Missing advertiser/page fields: normalized JSON lists `missing_fields`; do not upgrade attribution confidence.
- CDP search finds no visible ads: fail-stop with `run-manifest.json` status `blocked`.
- CDP search finds ads but no advertiser/page identity: write `partial` status and do not write attribution.
- Printing Press missing or browser-sniff failure: fail-stop after writing the sanitized HAR/capture summary where possible; do not mark replay ready.
- CDP detail captures a page but no advertiser/page identity: write `partial` status and preserve DOM/network artifacts for manual review.
- CDP page/entity pivot finds no visible page/entity fields: write `partial` status and preserve DOM/network artifacts for manual review.

## Anti-Patterns

1. Never start with a single tool. Launch all available in parallel.
2. Never retry a failed tool more than once. Switch to fallback.
3. Never guess DOB, family, or zodiac.
4. Never attribute data without cross-referencing against namesakes.
5. Never include unsourced facts.
6. Never reveal OSINT methods in public messages.
7. Never exceed 3 recursive cycles. Diminishing returns.
8. Never rate Depth Score 9+ without justification.
9. Never skip psychoprofile. Without it, dossier = Wikipedia article.
10. Never skip Phase 1.5 (internal intel). Telegram history is often the richest source.
11. Never quote DMs verbatim in shareable outputs. Summarize and cite.
12. Never hammer APIs without rate limiting. Stagger requests.
13. Never treat a redirect/affiliate-marketing domain as isolated without pivoting on its affiliate/tracking/click ID. Extract the ID from the URL or redirect chain and search for every other site or page carrying the same one -- the ID is the operator's fingerprint, not the domain name. (Founder-directed, case-001-example, 2026-09-04.)
14. Never conclude a page is inert, dormant, or "just a placeholder" from its title or a scan summary alone. Read the actual DOM/rendered source: tracking pixels, third-party ad or affiliate JS, meta-refresh, hidden iframes, and references to other cluster domains all live there and are invisible from the title. (Same origin as #13.)
