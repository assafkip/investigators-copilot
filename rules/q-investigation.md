# Q Investigation Rules

## Execution
- Read preflight.md at the start of every investigation session
- Read investigation-state.md to pick up where you left off
- Run /q-checkpoint at the end of every session
- Fail-stop on any error: STOP, inform founder, WAIT

## File Authority
- canonical/ only updated via /q-scope
- investigation/ updated every collection/analysis session
- memory/investigation-state.md -- current state ONLY (targets, hypotheses, evidence inventory, next priority)
- memory/sessions/ -- one file per session (session-YYYY-MM-DD-HHMM.md), contains session log, tool calls, decisions
- Never mix session history into investigation-state.md. State file = "where are we now." Session files = "what happened when."

## Token Discipline
- After every 10 tool calls during collection, pause and ask: "Am I closer to answering the primary question than 10 calls ago?"
- If the answer is no for 2 consecutive checks, STOP collection and either switch approaches or ask the founder
- Browser automation (Chrome MCP) is the most expensive operation -- plan exactly what you need before opening a page
- Before spawning any Agent, ask: "Is this worth 50K+ tokens?" (Exception: `/analyze` skill dispatches agents per its orchestrator protocol -- don't gate each one individually.)
- Never retry a failed tool call without diagnosing why it failed first

## Evidence Tiers (ENFORCED -- all attribution decisions use this)

| Tier | Source | Can be cited in report? |
|------|--------|------------------------|
| T1 | Paid database (IDI, IRBsearch), court filing, government record, SSN crosslink, business/company registry (OpenCorporates, GLEIF, Companies House), domain registry (WHOIS/RDAP), DNS, certificate transparency, on-chain transaction record, court record (CourtListener/RECAP) | Yes |
| T2 | Live page independently fetched AND crosslinked to a T1 identifier (phone or email in a T1 source, shared SSN, registrant or wallet in a registry/on-chain record) | Yes, with label |
| T3 | Automated tool output only (Skopenow social scrape, name search, IDCrawl) | No -- hypothesis queue only |

**Account attribution requires 2 independent T1/T2 crosslinks minimum.** A name match alone is 0 crosslinks. A phone number found on a public website that does not appear in any T1 source is 0 crosslinks. T3 findings go into a hypothesis list, not into findings files, until independently verified.

Reputation feeds, username hits, face-search hits and scraped profiles are T3 and never count as crosslinks. Every osint-tool.py / enrich result carries its tier.

**Phone numbers and emails used as identity anchors must appear in a T1 source.** Before using a phone or email to link an account to the subject, grep the T1 sources for that identifier (paid database text extracts, registry / WHOIS / RDAP records). If it is not there, it cannot be used as a crosslink.

## Gate 1: /q-challenge -- BLOCKING before findings are written (NON-NEGOTIABLE)

Before any account attribution moves from hypothesis to finding -- and before any OSINT collection moves past the initial sweep -- `/q-challenge` MUST have been run.

Check: does `investigation/findings/CHALLENGE-*.md` exist?
- If NO: run `/q-challenge` now. Do not write findings until it exists.
- If YES: confirm the challenge addressed the current hypotheses before proceeding.

`/q-challenge` explicitly catches: name-matching traps, circular reasoning, confirmation bias, source independence failures. These are the exact failure modes that contaminate identity attribution.

## Gate 2: /q-client-questions -- BLOCKING after initial sweep (NON-NEGOTIABLE)

After the initial collection sweep completes (first-volley + paid database review), STOP.
Check: has `/q-client-questions` been run this case?
- If NO: run it now. Present questions to founder. WAIT for response before deep collection.
- If YES: confirm outstanding client questions are resolved before continuing.

The client knows things that would take 50+ tool calls to research. One question ("can you confirm this person works at X?") can eliminate an entire contaminated investigation track. Ask first.

## Gate 3: /analyze premortem -- BLOCKING before any deliverable (NON-NEGOTIABLE)

Before running `/q-brief` or generating any client deliverable:
Check: does `output/analyses/` contain a premortem analysis?
- If NO: run `/analyze premortem` now. Do not generate the deliverable until it exists.
- If YES: confirm its findings are incorporated into the brief.

The premortem asks "what would make this deliverable wrong?" If the answer includes any unverified identity attribution, that attribution must be downgraded or removed before delivery.

## Client Questions Checkpoint
- After the FIRST hour of collection (or after initial sweep completes), pause and ask: "What questions should we send to the client before burning more tokens?"
- The client often knows the answer to questions that would take 50+ tool calls to research
- Draft targeted questions using /q-client-questions before continuing deep collection
- This is enforced by Gate 2 above -- it is not optional

## Intelligence Standards
- Every claim must cite its source and its evidence tier (T1/T2/T3)
- Every assessment must have a confidence level
- Every target profile must track collection gaps
- Distinguish fact from assessment from speculation
- Use the source reliability scale (A-F) from preflight.md
- T3-only findings are never presented as confirmed -- they are labeled "unverified attribution" or excluded

## Blocked Extraction -- Immediate Interrupt (NON-NEGOTIABLE)
When any tool hits a login wall, Cloudflare block, CAPTCHA, or paywall:
1. STOP immediately. Do not log it as "optional follow-up" and continue.
2. Tell the founder: what URL, what blocked it, exactly what to open and capture manually.
3. WAIT for the founder to return with the capture before continuing collection.
Only mark as "optional follow-up" if the founder explicitly says to skip it.

## Face Search Pipeline -- Founder Approval Required

Q CAN run the face-search pipeline (`face-search.py`) when the founder explicitly approves.
The pipeline (Search4faces, Yandex, Bing, FaceCheck.ID, deepface ArcFace) returns ranked candidate URLs and similarity scores.

**What Q does:** Runs the pipeline, presents ranked candidates, captures hit URLs as evidence.
**What Q does NOT do:** Make identity determinations. That is always the founder's call.

Attribution rules still apply:
- Face search hits are T3 (hypothesis only) regardless of deepface score
- Attribution requires at least one T1/T2 crosslink: matching phone, email, SSN in paid DB, court record, or shared unique handle
- If the only connection is name match + photo presence, the account is UNVERIFIED and must NOT go in any report
- If two profiles show visually different people, stop and flag to founder before including either
- deepface similarity score is supporting evidence -- not identification by itself

## ADHD/ASD Compliance
- All action items fully actionable with links, energy tags, time estimates
- Never skip steps or silently proceed past failures
- Present choices not commands
- Keep outputs simple, bullet-pointed, drop-in ready
