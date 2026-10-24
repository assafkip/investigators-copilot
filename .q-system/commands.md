# Q Investigation System -- Commands

Last updated: 2026-10-10

---

## /q-new-case -- Create New Investigation

**Purpose:** Scaffold a new investigation case from templates. Each investigation gets its own folder under `investigations/`.

**Steps:**
1. Ask for case name (short slug) and brief description
2. Generate case ID: `case-NNN-{slug}` (increment from highest existing)
3. Copy `templates/new-investigation/` to `investigations/case-NNN-{slug}/`
4. Write the new case folder name to `.active-case`
5. Update scope.md with case description and today's date
6. Suggest running `/q-scope` to define full parameters

---

## /q-begin -- Start Investigation Session

**Purpose:** Load all context for a case before starting work.

**Steps:**
1. Identify active case (if multiple, ask the founder)
2. Write the active case folder name (e.g., `case-001-example`) to `.active-case` so other commands and `/analyze` can resolve it without asking
3. Read in parallel: scope.md, collection-plan.md, investigation-state.md, last-handoff.md
4. Read preflight.md
5. Check for existing analyses in `output/analyses/` -- list any with their status (complete/in-progress) and last technique run
6. Output: case name, primary question, where we left off, top 3 priorities, blockers, active/completed analyses

---

## /q-end -- End Investigation Session

**Purpose:** Summarize changes and save state for session continuity.

**Steps:**
1. List all files modified this session
2. Update investigation-state.md with session summary
3. Create session log in memory/sessions/
4. Generate handoff note in memory/last-handoff.md
5. Report effort metrics

---

## /q-handoff -- Session Handoff

**Purpose:** Generate a context note for the next session. Saved to `memory/last-handoff.md`.

**Contents:** Session summary, in-progress work, decisions made, files modified, blocked items, suggested next action.

---

## /q-screenshots -- Capture Evidence Screenshots

**Purpose:** Capture every URL referenced in a report or brief as a chain-of-custody evidence item.

**Steps:**
1. Extract all URLs from the target file (skip mailto:, internal paths, API endpoints)
2. Skip URLs already captured (an EV item whose `source.json` has that `source_url`)
3. Write a batch file (`<url>\t<slug>\t[platform]\t[account]\t[note]` per line) and run
   `bash skills/osint/scripts/capture-evidence.sh --batch <file> --case <case>`
   (add `--social` per item for post media, `--archivebox` for an extra ArchiveBox copy; both additive)
4. Replace the raw URLs in the report with `[EV-NNNN]` citations; `render-report.py` renders them
5. An INCOMPLETE item (login wall, paywall, 404) is not cited: stop and tell the founder (fail-stop)

No `screenshots/` dump folder and no GO FULL PAGE extension: that pattern is deprecated by
`.claude/rules/evidence-capture-protocol.md`.

---

## /q-reality-check -- Stress-Test Conclusions

**Purpose:** Argue AGAINST current hypotheses to find weak spots before a client or attorney does.

**Steps:**
1. Read scope, findings, investigation state
2. For each hypothesis, argue the opposite
3. Rate each as STRONG / MODERATE / WEAK
4. For MODERATE/WEAK: what evidence would upgrade it? What's the simplest alternative?
5. Optional, for a draft brief/report: `python3 skills/osint/scripts/validate-citations.py <brief.md> --case <case>` -- dead links and citing sentences whose hard tokens are missing from the captured EV item become WEAK candidates
6. Write to findings/REALITY-CHECK-YYYY-MM-DD.md

---

## /q-scope -- Define Investigation Parameters

**Purpose:** Set or update the investigation's scope, hypotheses, and collection requirements.

**Steps:**
1. Ask the founder to describe the investigation (target, question, context)
2. Define:
   - **Primary question:** What are we trying to answer?
   - **Targets:** People, entities, domains, accounts to investigate
   - **Hypotheses:** Working theories to test
   - **Collection requirements:** What data do we need? From where?
   - **Boundaries:** What's out of scope? Legal/ethical limits?
3. Write to `canonical/scope.md`
4. Create initial target files in `investigation/targets/`
5. Create initial collection plan in `canonical/collection-plan.md`
6. Confirm with founder

---

## /q-intake [type] -- Add New Information

**Purpose:** Process new information into the investigation structure.

**Types:** target, finding, evidence, tip

**Steps:**
1. Ask for the information (or accept paste/file)
2. Classify: What type of information is this?
3. Assess reliability: How trustworthy is the source?
4. Route to appropriate file:
   - New person/entity -> `investigation/targets/[name].md`
   - Confirmed intelligence -> `investigation/findings/`
   - Raw data/screenshots -> `investigation/evidence/`
   - Timeline events -> `investigation/timelines/`
5. Cross-reference against existing targets and findings
6. Flag any new leads or connections surfaced
7. Update `memory/investigation-state.md`

**Client-provided document/CSV intake (mandatory order):** any file the client
hands us -- PDF, DOCX, image, or a leaked/breach-database CSV export -- goes
through `ingest-client-document.sh` (EV-NNNN registration) then
`extract-intake.py` (deterministic verbatim extraction) BEFORE any custom
script touches it. See `.claude/rules/evidence-capture-protocol.md`. For a
leaked-records CSV specifically (Maltego D4 export, subject identity
classification into confirmed/flagged/excluded tiers), use the
`leak-record-classifier` skill (`skills/leak-record-classifier/`)
instead of writing a classifier from scratch -- it's the shared scaffold two
prior cases independently reinvented. `evidence-pipeline-guard.py` blocks
skipping the ingest/extract step for any script written under a case's
`investigation/evidence/scripts/`.

**Side files from `extract-intake.py`** (per document, under `evidence/extracted/<stem>/`):
`iocs.json` (domains, IPs, emails, wallets, hashes), `entities.json`, `exif.json`. All are
T3 leads, not findings. Optional model NER: `--ner gliner` (local) or `--ner spacy`;
`--ner langextract` SENDS TEXT TO GEMINI and needs founder approval for client documents.
Follow-ups: `resolve-entities.py <csv> --out same_as.csv [--ftm out.jsonl]` (dedupe people/orgs
across sources); `ioc-reputation.py extracted/<doc>/iocs.json` (reputation leads only, and it
discloses the indicators to the providers queried).

---

## /q-target [name] -- Create or Update Target Profile

**Purpose:** Build a structured profile for an investigation target.

**Steps:**
1. Create/update `investigation/targets/[name].md` with:
   - **Identity:** Name, aliases, known accounts, affiliations
   - **Digital footprint:** Social media, domains, email patterns
   - **Connections:** Links to other targets, organizations, events
   - **Timeline:** Key events and activities
   - **Collection status:** What we have, what we need
   - **Assessment:** Current understanding, confidence level
2. Cross-reference against other target files for connections
3. Update `investigation/timelines/` if new events found
4. Flag collection gaps

---

## /q-collect -- Plan or Execute OSINT Collection

**Purpose:** Plan collection activities or process collected data.

**STEP ZERO (NON-NEGOTIABLE -- runs before anything else):**
Web-search every target handle, display name, and known alias before any Apify actor or platform scrape. Google AI Overviews, news articles, and personal bios frequently resolve the primary question in seconds. If a web search resolves the question, move to verification -- skip heavy collection.

```bash
# Perplexity search mode -- run both:
# "who runs @[handle]"
# "[display name] [platform] operator"
```

Scar: case-036 -- 117 posts scraped and multiple dead-end platform searches run before a basic Google search named the operator in the AI Overview. All of it was avoidable.

**GATE CHECK (blocking):** Before executing deep collection, verify:
- Does `investigation/findings/CHALLENGE-*.md` exist? If NO -- run `/q-challenge` first.
- Has `/q-client-questions` been run this case? If NO -- run it first and wait for founder response.
Both gates must be cleared before collection proceeds past the initial sweep.

**Steps:**
1. **Step Zero:** Web-search target handle and display name (see above). If primary question is resolved, go to verification.
2. Read `canonical/collection-plan.md` for outstanding requirements
3. Read `memory/investigation-state.md` for what's been collected
4. Identify highest-priority collection gaps
4. For each gap, suggest:
   - What to collect
   - Where to collect it (platform, source)
   - Tool/method to use
   - Expected yield
   - Energy tag + Time Est
5. Present as choices, not commands
6. When founder brings back data, process via `/q-intake`

**OSINT Toolkit:** Read `skills/osint/SKILL.md` for full tool catalog, actor IDs, and escalation flow.

**Quick reference -- collection scripts:**
```bash
# Self-diagnostics (run first)
bash skills/osint/scripts/diagnose.sh

# Parallel search across all engines
bash skills/osint/scripts/first-volley.sh "Target Name" "context"

# Merge and deduplicate results
bash skills/osint/scripts/merge-volley.sh /tmp/osint-<timestamp>

# Platform-specific
bash skills/osint/scripts/apify.sh linkedin "<url>"
bash skills/osint/scripts/apify.sh instagram "<handle>"
bash skills/osint/scripts/perplexity.sh search "query"
bash skills/osint/scripts/exa.sh people "Name"
bash skills/osint/scripts/tavily.sh search "query"
bash skills/osint/scripts/jina.sh read "<url>"
bash skills/osint/scripts/brightdata.sh scrape "<url>"

# Universal Apify runner (55+ actors)
bash skills/osint/scripts/run-actor.sh "actor/id" '{"input":"json"}'
```

**Escalation:** Level 1 (free, fast) -> Level 2 (source verify) -> Level 3 (social scrape) -> Level 4 (deep research, ~$0.50)

**Additional sources (manual/CLI):**
- Domain/WHOIS/DNS/CT records (T1, keyless): `python3 skills/osint/scripts/osint-tool.py rdap|doh|crtsh|certspotter <domain>`; `whois`, `dig` as fallback
- Any adapter: `python3 skills/osint/scripts/osint-tool.py --list` (54 adapters, each result tagged T1/T3)
- Web archives: Wayback CDX is research-only (not part of capture; cite only EV items)
- Google dorking: search operators via browser
- DNS/IP: `dig`, `nslookup`, Shodan
- Public records: platform-specific

---

## /q-osint [platform] [target] -- Platform-Specific Collection

**Purpose:** Run targeted OSINT collection on a specific platform. Uses the OSINT script library and actors.

**GATE CHECK (blocking):** Before running any platform collection:
- Does `investigation/findings/CHALLENGE-*.md` exist? If NO -- run `/q-challenge` first.
- Has `/q-client-questions` been run? If NO and initial sweep is complete -- run it first.
Any account found via platform collection is T3 (hypothesis only) until crosslinked to a T1 source (paid database). Do not write it to findings as confirmed until that crosslink exists.

**Before first use:** Run `bash skills/osint/scripts/diagnose.sh` to check available tools.

**LinkedIn:** `/q-osint linkedin [profile-url]`
- `bash skills/osint/scripts/apify.sh linkedin "<url>"` (profile data)
- Fallback: `bash skills/osint/scripts/brightdata.sh scrape "<url>"`
- Map connections to existing targets
- Output structured profile + activity patterns
- Save to `investigation/targets/[name].md`

**Instagram:** `/q-osint instagram [handle]`
- `bash skills/osint/scripts/apify.sh instagram "<handle>"` (profile + posts)
- Tagged posts: `bash skills/osint/scripts/run-actor.sh "apify/instagram-tagged-scraper" '{"username":"handle"}'`
- Comments: `bash skills/osint/scripts/run-actor.sh "apify/instagram-comment-scraper" '...'`

**Facebook:** `/q-osint facebook [url]`
- Pages: `bash skills/osint/scripts/run-actor.sh "apify/facebook-pages-scraper" '...'`
- Personal profiles: `bash skills/osint/scripts/brightdata.sh scrape "<url>"` (only Bright Data works)

**Reddit:** `/q-osint reddit [username]`
- Pull post/comment history: `python3 skills/osint/scripts/reddit-arctic.py user <username> --case <case>`
  (Arctic Shift archive, then PullPush, then Reddit RSS; also MCP `osint-infra` tool `reddit_user_history`).
  Do NOT use reddit.com JSON: it returns 403 from servers. Arctic Shift also keeps deleted posts.
- Map active subreddits and topics
- Identify behavioral patterns, posting times
- Cross-reference usernames and language patterns

**X/Twitter:** `/q-osint x [handle]`
- Pull tweet history (last 90 days)
- Map interactions (replies, RTs, mentions)
- Identify key relationships from engagement

**TikTok:** `/q-osint tiktok [handle]`
- `bash skills/osint/scripts/run-actor.sh "clockworks/tiktok-profile-scraper" '{"profiles":["handle"]}'`
- Discovery: `bash skills/osint/scripts/run-actor.sh "clockworks/tiktok-user-search-scraper" '{"keywords":"name"}'`

**YouTube:** `/q-osint youtube [channel]`
- `bash skills/osint/scripts/run-actor.sh "streamers/youtube-channel-scraper" '...'`

**Domain:** `/q-osint domain [domain.com]`
- Registration record (T1): `python3 skills/osint/scripts/osint-tool.py rdap domain.com --case <case>` (or `whois domain.com`)
- DNS (T1): `osint-tool.py doh domain.com`, mail posture `osint-tool.py dns_deep domain.com`
- Certificate transparency / subdomains (T1): `osint-tool.py crtsh domain.com`, `osint-tool.py certspotter domain.com`
- Hosting: `osint-tool.py asn <ip>`, `osint-tool.py shodan <ip>` (InternetDB keyless), `osint-tool.py reverse_ip <ip>` (T3)
- Lookalikes: `osint-tool.py typosquat domain.com` (dnstwist); tech: `osint-tool.py wappalyzer domain.com`
- Historical pages: Wayback is research-only (not submitted, not citable); capture the live page with `capture-evidence.sh`

**Identity sweep:** `/q-osint username|email|phone [value]`
- `python3 skills/osint/scripts/identity-sweep.py <handle|email|phone> --case <case>` -- every ready identity adapter (username/WhatsMyName, maigret, sherlock, holehe, gravatar, github/gitlab/npm/hn, phone, telegram_phone, xposedornot ...), merged, all T3
- Shortcut: `bash skills/osint/scripts/identity-lookup.sh sweep <value> [case]`
- Feed the saved `urls.tsv` to `capture-evidence.sh --batch` before citing anything

**Email:** `/q-osint email [address]`
- Check known breach databases (HIBP); `osint-tool.py xposedornot <email>`
- Identify associated accounts/platforms (`identity-sweep.py <email>`)
- Domain analysis for custom domains
- Contact enrichment: `bash skills/osint/scripts/run-actor.sh "vdrmota/contact-info-scraper" '{"urls":["site.com"]}'`

**Full sweep:** `/q-osint sweep [name]`
- Runs the OSINT skill's full pipeline (Phase 1 -> 2 -> 3)
- **Default first pass (Perplexity playbook, parallel with first-volley):**
  ```bash
  bash skills/osint/scripts/perplexity-playbook.sh <type> <slug> "<target>" --case <active-case> &
  bash skills/osint/scripts/first-volley.sh "Name" "context" &
  wait
  ```
  `<type>` = `person|company|domain|incident`. Playbook writes merged citations
  to `/tmp/osint-<slug>-<ISO8601>/evidence.json` and persists to the case's
  `raw-collections/`. Add `--capture` to auto-run `capture-evidence.sh --batch`
  on the deduped URL list.
- Merge results, score confidence, identify platforms
- Populate target profile with all findings

**Email:** `/q-osint email [address]`
- Check known breach databases (HIBP)
- Identify associated accounts/platforms
- Domain analysis for custom domains
- Pattern matching against known targets

**Rules:**
- Always use Apify or API tools before Chrome
- Social posts: `capture-evidence.sh <url> <slug> --social` also downloads the post media into the same EV item (additive, never flips status)
- Every `osint-tool.py` / `enrich` result carries its tier; reputation, username and scraped-profile hits are T3 and never crosslinks
- Log all collection to `investigation/evidence/`
- Tag source reliability (A-F scale)
- Never exceed ethical/legal boundaries defined in scope

---

## /q-analyze -- Connect the Dots

**Purpose:** Review all collected data and surface patterns, connections, gaps.

**Steps:**
1. Read all target profiles in `investigation/targets/`
2. Read all findings in `investigation/findings/`
3. Read timeline in `investigation/timelines/`
4. Read any completed structured analyses in `output/analyses/` -- incorporate their key judgments, ACH matrices, and assumptions checks rather than re-deriving conclusions
5. Identify:
   - **Connections:** Links between targets not previously noted
   - **Patterns:** Behavioral patterns, timing correlations, shared infrastructure
   - **Gaps:** Missing information that would confirm/deny hypotheses
   - **Contradictions:** Data points that conflict
   - **New leads:** Targets or threads not yet in scope
6. For each finding, assess:
   - Confidence level (confirmed / high / moderate / low / speculative)
   - Supporting evidence (cite specific files)
   - Alternative explanations
7. Update `investigation/findings/` with new assessments
8. Update collection plan with new requirements
9. Present analysis to founder

---

## /q-link [target-a] [target-b] -- Map Relationships

**Purpose:** Explicitly map and document the relationship between two targets.

**Steps:**
1. Read both target profiles
2. Search evidence for any shared:
   - Organizations, employers, affiliations
   - Events, timeframes, locations
   - Digital infrastructure (domains, IPs, accounts)
   - Communication patterns
   - Third-party connections
3. Classify relationship: direct / indirect / inferred / unknown
4. Assess strength: strong / moderate / weak / speculative
5. Document in both target files + `investigation/findings/`
6. Update timeline if relationship has temporal dimension

---

## /q-timeline -- Build or Update Timeline

**Purpose:** Reconstruct chronological sequence of events.

**Steps:**
1. Read all target profiles and findings
2. Extract dated events
3. Build/update `investigation/timelines/master-timeline.md`
4. Identify:
   - Clusters of activity
   - Gaps (periods with no data)
   - Temporal correlations between targets
   - Sequence patterns (A always happens before B)
5. Present timeline to founder
6. Flag periods that need more collection

---

## /q-brief -- Generate Investigation Brief

**Purpose:** Produce a structured summary of current investigation state.

**GATE CHECK (blocking) -- ALL THREE must pass before brief generation:**
1. Does `investigation/findings/CHALLENGE-*.md` exist? If NO -- run `/q-challenge` first.
2. Has `/q-client-questions` been run and responses received? If NO -- stop.
3. Does `output/analyses/` contain a premortem analysis? If NO -- run `/analyze premortem` first.

If any gate fails, tell the founder which gate is missing and what to run. Do not generate the brief.

**Steps:**
1. Read scope, all targets, all findings, timeline
1b. Read any completed analyses in `output/analyses/` -- incorporate key judgments, confidence levels, and technique outputs into the brief
2. Generate brief with:
   - **Executive summary:** 3-5 bullet points answering the primary question (current state)
   - **Key findings:** Confirmed intelligence, with confidence levels and citations
   - **Target matrix:** All targets, their status, key connections
   - **Timeline summary:** Major events in chronological order
   - **Collection gaps:** What we still need
   - **Hypotheses status:** Which are supported/refuted/undetermined
   - **Recommended next steps:** Prioritized by impact, tagged with Energy + Time Est
3. **Evidence pass:** Every URL the brief relies on must be an `[EV-NNNN]` item. Capture missing ones with `capture-evidence.sh --batch <file> --case <case>` (see /q-screenshots), then render with `render-report.py <brief.md> <out.md>` (fails on a broken citation).
4. Save to `output/briefs/brief-YYYY-MM-DD.md`
5. Present to founder

---

## /q-status -- Quick Snapshot

**Purpose:** Fast overview of investigation state.

**Steps:**
1. Read `memory/investigation-state.md`
2. Output compact summary:
   - Targets: X total, Y fully profiled, Z with gaps
   - Findings: X confirmed, Y assessed, Z speculative
   - Collection: X sources tapped, Y outstanding
   - Analyses: list any in `output/analyses/` with technique(s) and status
   - Hypotheses: status of each
   - Top 3 priorities

---

## /q-debrief -- Process Conversation or Source

**Purpose:** Extract structured findings from a conversation, interview, document, or source.

**Steps:**
1. Ask founder to describe or paste the source material
2. Extract:
   - New targets or entities mentioned
   - Facts (with reliability assessment)
   - Timeline events (with dates)
   - Relationships between entities
   - Contradictions with existing findings
   - New collection leads
3. Route to appropriate investigation files
4. Cross-reference against existing data
5. Update `memory/investigation-state.md`
6. Append relationship triples to `memory/graph.jsonl` -- always
   the INSTANCE KB, never a case folder's `memory/` (local-only, never committed).
   One JSON object per line, format:
   `{"s":"<subject>","p":"<predicate>","o":"<object>","t":"YYYY-MM-DD"}`
   Predicates: `works_at`, `role_is`, `knows`, `communicates_with`, `uses_alias`,
   `associated_with`, `controls`, `owns`, `targets`, `located_in`.
   Query by grep: `grep '"s":"<name>"' memory/graph.jsonl`

---

## /q-export [format] -- Export Investigation Data

**Purpose:** Export investigation data in a structured format.

**Formats:** markdown, json, timeline-html, stix, misp, csv, map. Flag: `--redact`.

**Steps:**
1. Gather all investigation files, including `output/analyses/` (structured analysis reports, technique artifacts, evidence registries)
2. Export in requested format:
   - **markdown:** Full investigation report, with structured analysis appendix (technique outputs, ACH matrices, key assumptions)
   - **json:** Structured data (targets, findings, links, timeline, analysis summaries)
   - **timeline-html:** `python3 skills/osint/scripts/render-timeline.py --case <case>` (`--timesketch` adds a Timesketch import CSV)
   - **stix | misp | csv:** `python3 skills/osint/scripts/export-intel.py stix|misp|csv|all --case <case> [--tlp clear|green|amber|red]`
   - **map:** `python3 skills/osint/scripts/render-map.py --case <case>` (EXIF/analyst points, not verified locations)
3. **Evidence pass:** Every URL in the report and appendix must be an `[EV-NNNN]` item (capture missing ones via `capture-evidence.sh --batch`, see /q-screenshots); render markdown with `render-report.py`.
4. **`--redact`:** `python3 skills/osint/scripts/redact-pii.py <export.md>` writes `<stem>.redacted.md` next to it (presidio if installed, else regex). Share the redacted copy; keep the original in the case.
5. Save to `output/exports/`
6. Present to founder

---

## /q-checkpoint -- Save State

**Purpose:** Save current investigation state. Auto-triggers at session end.

**Steps:**
1. Update `memory/investigation-state.md` with:
   - Session summary
   - What was collected/analyzed
   - Outstanding tasks
   - Next priority
2. Verify target files are consistent with findings, timeline, and any structured analysis conclusions in `output/analyses/`
3. Flag any inconsistencies (including between Q findings and /analyze outputs)
4. Confirm save

---

## /analyze -- Structured Analytic Techniques (SAT)

**Purpose:** Run IC-standard Structured Analytic Techniques on investigation data. This is a Claude Code skill (not a Q command) -- it has its own orchestrator, evidence collector, and self-correction layers.

**Skill location:** `skills/structured-analysis/SKILL.md`

**When to use `/analyze` vs Q commands:**
- `/analyze ach` -- formal hypothesis testing with diagnosticity matrix. Use when you have 3+ competing hypotheses and need to systematically evaluate evidence for/against each.
- `/analyze kac` -- structured assumptions check. Use when key judgments rest on assumptions that haven't been tested.
- `/analyze deception` -- detect planted/false information. Use when source reliability is uncertain or adversary may be seeding disinformation.
- `/analyze premortem` -- failure-mode analysis. Use before delivering a brief to stress-test conclusions.
- `/analyze --lean` -- quick run (restatement + KAC + inconsistencies). Good mid-investigation sanity check.
- `/analyze --no-osint` -- analyze already-collected evidence only. **Recommended for most Q investigation use** since we collect via `/q-osint` first.
- `/q-challenge` -- still use for quick informal gut checks mid-session
- `/q-reality-check` -- still use for fast stress-tests when full SAT is overkill

**Output routing:** All analysis artifacts write to the active case's `output/analyses/<analysis-id>/`. The skill's SKILL.md has the path override instructions.

**Typical Q workflow:**
1. Collect evidence: `/q-osint`, `/q-collect`
2. Run analysis: `/analyze ach --no-osint` (uses collected evidence as Tier 2 local files)
3. Results auto-feed back into `investigation/findings/` and `investigation-state.md`
4. Brief the client: `/q-brief` (incorporates analysis findings)

---

## /q-challenge -- Challenge Assumptions

**Purpose:** Force a structured challenge of all investigation assumptions and hypotheses at the midpoint. Prevents confirmation bias and circular reasoning.

**Steps:**
1. Read `canonical/scope.md` for hypotheses
2. Read ALL files in `investigation/findings/`
3. Read key evidence files
4. Read `memory/investigation-state.md`
5. For each hypothesis, evaluate:
   - What evidence SUPPORTS this? (cite files)
   - What evidence CONTRADICTS this? (cite files)
   - What would DISPROVE this? (describe the test)
   - Have we actually looked for disproving evidence?
   - Is this based on fact, inference, or assumption?
   - Could the same evidence support a different explanation?
6. Check for: circular reasoning, name-matching traps, confirmation bias, source independence, community inference vs. identification
7. Write to `investigation/findings/CHALLENGE-YYYY-MM-DD.md`
8. Present revised confidence levels and top 3 weakest assumptions as choices

---

## /q-client-questions -- Draft Client Questions

**Purpose:** Draft targeted questions for the client based on current collection gaps. The client often knows the answer to things that would take 50+ tool calls to research.

**Steps:**
1. Read `canonical/scope.md` for hypotheses
2. Read `canonical/collection-plan.md` for outstanding gaps
3. Read `investigation/targets/` for collection status
4. Read `memory/investigation-state.md` for what's been tried
5. Draft 3-5 questions that target the biggest collection gaps, ask about relationships, and request identification of unknown persons
6. Format as a copy-paste-ready email
7. Present to founder for review -- never send directly

---

## /q-face [image_path] -- Reverse Face Search

**Purpose:** Complete end-to-end face identification pipeline. Detects and crops faces, runs web-scale search across 4 engines, runs deepface ArcFace comparison against top candidates, returns ranked results for founder review.

**Activation:** Runs when founder explicitly approves. No case gate required -- founder approval is the gate.

**Steps:**
1. Run the pipeline:
   ```
   python3 skills/osint/scripts/face-search.py <image_path> \
     --case <case-slug> --gender male
   ```
   - Phase 1: deepface detects + crops all faces, classifies gender, isolates target
   - Phase 2: Search4faces API + Yandex (Selenium) + Bing Visual Search (Selenium) + FaceCheck.ID API + Google Cloud Vision web detection (when `GOOGLE_VISION_API_KEY` is set)
   - Phase 3: Downloads top 5 candidate profile photos, runs deepface ArcFace comparison, ranks by score
   - Phase 4: Routes top 10 hit URLs through `capture-evidence.sh` for chain of custody
2. Review ranked candidates output -- DEEPFACE MATCH entries are highest confidence
3. Check manually: **Lenso.ai** (lenso.ai) and **FaceCheck.ID** (facecheck.id)
4. Direct image comparison (after identifying a candidate photo):
   ```
   python3 face-search.py <image_path> --confirm <candidate_image_path>
   ```
5. Route confirmed account leads through `/q-intake`

**First run -- verify environment:**
```
python3 skills/osint/scripts/face-search.py --setup
```

**Options:**
- `--gender male|female|all` -- target specific face in group photos
- `--no-confirm` -- skip deepface comparison phase (faster, web results only)
- `--no-capture` -- skip evidence capture (dry run)
- `--top N` -- number of candidates to deepface-confirm (default: 5)

**API keys (optional -- pipeline runs without them, more engines = better coverage):**
- `SEARCH4FACES_API_KEY` -- 500M+ VK/OK.ru/TikTok profiles
- `FACECHECK_API_KEY` -- FaceCheck.ID paid API (Selenium fallback if absent)
- `GOOGLE_VISION_API_KEY` -- Cloud Vision WEB_DETECTION backend (pages with matching images; page matches, not identities). Standalone: `bash skills/osint/scripts/reverse-image.sh <image> --case <case>`

**Identity rule:**
- Q presents ranked candidates. Founder makes the identity call.
- Face search hits are T3 (hypothesis only). Attribution requires T1/T2 crosslink.
- deepface score is supporting evidence -- not identification by itself.

**Venv:** `skills/osint/face-env/` (Python 3.12 + deepface + tensorflow + selenium)

---

## /q-watch [add|remove|list|poll] -- Monitor URLs for Changes

**Purpose:** Watch case URLs/profiles and route every change into the evidence chain. Full steps: `.claude/commands/q-watch.md`.

**Steps:**
1. `python3 skills/osint/scripts/watch.py add "<url>" --label "<label>"` (also `list`, `remove`)
2. `watch.py poll` (report) or `watch.py poll --capture` (changed URLs -> `capture-evidence.sh --batch`); bounded by `--max` / `--deadline`
3. Backend: local SHA-256 diff, or changedetection.io when `CHANGEDETECTION_URL` + `CHANGEDETECTION_API_KEY` are set (`setup-tools.sh --docker changedetection`)
4. A change is a T3 lead; only the EV item created by `--capture` is citable

---

## /q-corp [subject] -- Public-Records Sweep

**Purpose:** Company/person public records (SEC EDGAR, Form D, UK Companies House, FEC, LDA lobbying, FAA registry, EU tenders). Full steps: `.claude/commands/q-corp.md`.

**Steps:**
1. `bash skills/osint/scripts/install-pp.sh list` (install missing CLIs with `install-pp.sh install [name ...]`, needs Go)
2. Run each source through the saving wrapper: `bash install-pp.sh run <name> --case <case> -- <cli args>`
3. Keyless registry adapters alongside: `osint-tool.py gleif "<name>"`, `osint-tool.py opencorporates "<name>"` (key), `osint-tool.py courtlistener "<name>"`, `osint-tool.py ofac "<name>"`
4. A registry record is T1 for "this record says X"; capture any record page you will cite with `capture-evidence.sh`
