# Investigators Copilot

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Claude Code](https://img.shields.io/badge/Claude_Code-plugin-orange)](https://claude.com/claude-code)
[![GitHub stars](https://img.shields.io/github/stars/assafkip/investigators-copilot?style=social)](https://github.com/assafkip/investigators-copilot)
[![Topics](https://img.shields.io/badge/topics-osint%20%7C%20threat--intel%20%7C%20investigation-brightgreen)](https://github.com/topics/osint)

Investigation toolkit for [Claude Code](https://claude.com/claude-code). Case management, OSINT, structured analytic techniques, chain-of-custody evidence capture, and bundled MCP servers for infrastructure recon and threat intel.

Not just a scraper wrapper. A full investigation workflow — from case intake to evidence-grade dossier.

**Use it for:** OSINT, due diligence, threat intelligence, incident response, digital forensics, journalistic research, competitive intel, security research, CTF challenges.

## How it works

### Investigation lifecycle

```mermaid
flowchart LR
    Start([New case]) --> NewCase[/q-new-case/]
    NewCase --> Scope[/q-scope/]
    Scope --> Begin[/q-begin/]

    Begin --> Collect{Collection}
    Collect --> Intake[/q-intake<br/>client docs/]
    Collect --> OSINT[/q-osint<br/>platform-targeted/]
    Collect --> Sweep[/q-collect<br/>broad sweep/]
    Collect --> Target[/q-target<br/>profile/]

    Intake --> Evidence[(EV-NNNN<br/>evidence items<br/>Wayback + archive.today<br/>+ Chrome PDF + SHA-256)]
    OSINT --> Evidence
    Sweep --> Evidence
    Target --> Evidence

    Evidence --> Analyze{Analysis}
    Analyze --> Timeline[/q-timeline/]
    Analyze --> Link[/q-link<br/>graph edges/]
    Analyze --> ACH[/q-analyze<br/>Heuer's ACH/]
    Analyze --> Challenge[/q-challenge<br/>red team/]
    Analyze --> Reality[/q-reality-check/]

    Timeline --> Report{Report}
    Link --> Report
    ACH --> Report
    Challenge --> Report
    Reality --> Report

    Report --> Brief[/q-brief<br/>evidence-cited/]
    Report --> Debrief[/q-debrief<br/>internal/]
    Brief --> Export[/q-export/]
    Debrief --> Export
    Export --> End([Dossier delivered])

    style Evidence fill:#fef3c7,stroke:#d97706,stroke-width:2px
    style Start fill:#dbeafe,stroke:#2563eb
    style End fill:#dcfce7,stroke:#16a34a
```

Every URL routes through `capture-evidence.sh`. Every finding cites `[EV-NNNN]`. Every claim has an A-F reliability grade.

### Architecture

```mermaid
graph TB
    subgraph Claude[Claude Code]
        CC[/Claude Code session/]
    end

    subgraph copilot[Investigators Copilot plugin]
        direction TB
        subgraph Skills
            OSINT_S[osint<br/>6-phase workflow]
            SA_S[structured-analysis<br/>Heuer's ACH + tradecraft primer]
        end

        subgraph Commands[24 commands]
            CM[case mgmt]
            CL[collection]
            AN[analysis]
            RP[reporting]
        end

        subgraph Rules[Enforced rules]
            EC[evidence-capture-protocol]
            QI[q-investigation]
            TD[token-discipline]
            SY[sycophancy]
        end

        subgraph Templates
            NI[new-investigation]
            SS[sec-stack-case]
        end
    end

    subgraph MCP[Bundled MCP servers]
        OI[osint-infra<br/>whois, dns, wayback]
        TI[threat-intel<br/>VT, URLhaus, ThreatFox, crt.sh]
    end

    subgraph External[Optional external APIs]
        PPL[Perplexity]
        EXA[Exa]
        TAV[Tavily]
        APF[Apify<br/>55+ scrapers]
        JIN[Jina]
        BD[Bright Data]
    end

    subgraph Case[Case workspace]
        EVD[(investigations/case/<br/>evidence/ findings/<br/>targets/ timelines/)]
    end

    CC --> copilot
    copilot --> MCP
    copilot --> External
    copilot --> Case
    Rules -.enforces.-> Commands
    Commands -.uses.-> Skills

    style Case fill:#fef3c7,stroke:#d97706
    style MCP fill:#e0e7ff,stroke:#6366f1
    style Rules fill:#fee2e2,stroke:#dc2626
```

## What you get

### Skills

- **`osint`** — 6-phase investigation: tooling check → seed collection → optional internal intel → platform extraction → cross-reference → psychoprofile → completeness scoring → dossier.
- **`telegram-harvest`**, **`geo-sleuth`**, **`verification`**, **`leak-record-classifier`** - Telegram channel harvest, geolocation, source verification, and leaked-records CSV classification.
- **`structured-analysis`** — CIA tradecraft primer library (Heuer's ACH, key assumptions check, quality of information check, red team, premortem, 66-technique taxonomy). Apache 2.0, upstream [Blevene/structured-analysis-skill](https://github.com/Blevene/structured-analysis-skill).

### Commands (24)

**Case management:** `/q-new-case`, `/q-scope`, `/q-begin`, `/q-status`, `/q-checkpoint`, `/q-handoff`, `/q-end`

**Collection:** `/q-intake`, `/q-collect`, `/q-osint`, `/q-target`, `/q-screenshots`

**Analysis:** `/q-analyze`, `/q-challenge`, `/q-reality-check`, `/q-client-questions`, `/q-timeline`, `/q-link`

**Reporting:** `/q-brief`, `/q-debrief`, `/q-export`

**Specialized:** `/q-sec-stack` (SaaS security stack intel), `/q-corp` (public-records sweep), `/q-watch` (monitor URLs for changes)

### Not included

Two things are deliberately left out of this kit. The automated face-search pipeline (`face-search.py`, `/q-face`) is dual-use. TGSpyder is third-party code with its own license; `telegram-harvest` takes its location from `TGSPYDER_SRC`.

### MCP servers (bundled)

- **`osint-infra`** — WHOIS, DNS, reverse DNS, Wayback snapshots / fetch.
- **`threat-intel`** — VirusTotal, URLhaus, ThreatFox, crt.sh certificate transparency.

### Agent

- **`ryan`** - the investigation analyst. Owns collection, structured analysis, evidence tiering and gate compliance for an active case.

### Enrichment adapters

`skills/osint/scripts/osint-tool.py --list` prints 54 adapters (CT logs, RDAP, DoH, registries, sanctions, on-chain, identity). Each result carries an evidence tier: T1 for records, T3 for tool output that needs a crosslink.

### Rules (enforced)

- **`evidence-capture-protocol`** — every URL routes through `capture-evidence.sh` (Wayback + archive.today + Chrome PDF + SHA-256 + metadata). Atomic `EV-NNNN-<slug>/` folders. Reports cite by ID.
- **`q-investigation`** — fail-stop on errors, token discipline, state-vs-session file authority, source reliability A-F scale.
- **`token-discipline`** — stop conditions, retry limits.
- **`sycophancy-core`** — anti-RLHF drift, decision origin tagging.
- **`investigation-claims-ledger`** — derived claims trace to a command that was run (`resolve-deliverable.py`, `evidence_ledger.py`).

### Templates

- **`new-investigation/`** — full case scaffold (`canonical/`, `investigation/evidence|findings|targets|timelines/`, `memory/`, `output/`).
- **`sec-stack-case/`** — SaaS security stack investigation template.

## Install

```bash
# In Claude Code
/plugin install assafkip/investigators-copilot
```

Or clone:

```bash
git clone https://github.com/assafkip/investigators-copilot.git
```

## MCP server setup

```bash
cp .mcp.json.template .mcp.json
```

### `osint-infra` (no keys required)

```bash
cd mcp-servers/osint-infra
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### `threat-intel`

Get free keys:
- VirusTotal: https://virustotal.com/gui/join-us (500 req/day)
- abuse.ch (URLhaus + ThreatFox): https://auth.abuse.ch

```bash
export VT_API_KEY=...
export ABUSE_CH_AUTH_KEY=...
```

## Optional search / scrape APIs

All optional — the skill degrades gracefully. Run `bash skills/osint/scripts/diagnose.sh` to see what's active.

| Env var | Service | Get key |
|---|---|---|
| `PERPLEXITY_API_KEY` | Perplexity Sonar / Deep | https://perplexity.ai |
| `EXA_API_KEY` | Exa semantic search | https://exa.ai |
| `TAVILY_API_KEY` | Tavily agent search | https://tavily.com |
| `APIFY_TOKEN` | Apify scrapers (LinkedIn, IG, TikTok, YouTube, FB pages) | https://apify.com |
| `JINA_API_KEY` | Jina reader / deepsearch | https://jina.ai |
| `PARALLEL_API_KEY` | Parallel AI search | https://parallel.ai |
| `BRIGHTDATA_MCP_URL` | Bright Data MCP (Facebook, LinkedIn, geo-blocked) | https://brightdata.com |

## Optional: Telegram recon

Not bundled — install separately if needed:

```bash
git clone https://github.com/Darksight-Analytics/tgspyder.git
cd tgspyder && pip install -r requirements.txt && pip install -e .
```

## Typical workflow

```
/q-new-case acme-breach
/q-scope          # define question, targets, constraints
/q-begin          # resume session
/q-intake <file>  # ingest client-provided docs
/q-osint linkedin https://linkedin.com/in/someone
/q-collect domain acme.com
/q-target acme-ceo
/q-timeline       # reconstruct event sequence
/q-analyze ach    # analysis of competing hypotheses
/q-challenge      # red team own conclusions
/q-brief          # generate evidence-grounded report
/q-export         # final package
```

Every URL captured routes through the evidence protocol. Every report cites `[EV-NNNN]`. Every claim has an A-F reliability grade.

## Ethics

For:
- Authorized security testing and due diligence
- Journalistic and academic research on public figures
- Defensive threat intelligence and incident response
- CTF / educational contexts

Do not use on private individuals without consent, for harassment, doxxing, or stalking. You are responsible for compliance with local laws and platform terms of service.

## Provenance & sync

investigators-copilot is built from a live investigation practice. The commands, skills, and
rules here are the same files running real cases daily, synced automatically on
every upstream change through a build script that anonymizes case references
and gates the publish behind a client-indicator blocklist plus a gitleaks
secret scan. Case-specific tooling and client data never leave the source repo.

Enforcement hooks ship wired since v0.3.0 (`hooks/hooks.json`): a token-bleed
circuit breaker (PreToolUse) and a findings-attribution gate that blocks a
CONFIRMED/HIGH-CONFIDENCE finding citing an identifier still marked UNVERIFIED
(PostToolUse). Installing the plugin activates both; no manual settings edits.

## Contributing

Issues and PRs welcome. Backward-compatible additions preferred. Note that
synced paths (`commands/`, `skills/`, `rules/`, `.q-system/`, `mcp-servers/`)
are overwritten by the upstream sync; PRs against them are best raised as
issues so the change lands upstream first.

## For LLM agents

See [`llms.txt`](llms.txt) for a machine-readable capability summary with a decision matrix for when to use each skill, command, and MCP server.

## License

MIT. See [LICENSE](LICENSE).

The `skills/structured-analysis/` subdirectory is Apache 2.0 (see `skills/structured-analysis/LICENSE` and `NOTICE.md`).
