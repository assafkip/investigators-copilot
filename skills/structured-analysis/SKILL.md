---
name: analyze
description: Conduct structured analysis on any problem using CIA/IC analytic techniques — assess competing hypotheses, challenge assumptions, stress-test judgments, and produce defensible evidence-based assessments with full citations. Supports 18 techniques including ACH, Key Assumptions Check, What-If, Premortem, Cross-Impact Matrix, Contrasting Narratives, Devil's Advocacy, Red Hat Analysis, Alternative Futures, and Deception Detection.
argument-hint: "[technique or flags, e.g. ach, --guided, --no-osint]"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash, WebSearch, WebFetch, Agent
---

# Structured Analysis Skill

Apply CIA/IC Structured Analytic Techniques to produce defensible, evidence-based analytical assessments. Every claim must be cited. Every judgment must trace to technique outputs.

## Invocation

```
/analyze                          → Adaptive mode (auto-select techniques)
/analyze <technique>              → Direct mode (run one technique)
/analyze --guided                 → Guided mode (walk through all phases)
/analyze --resume <analysis-id>   → Resume or update existing analysis
/analyze --iterate <analysis-id>                → Re-run full analysis with new evidence
/analyze --iterate <analysis-id> <technique>    → Re-run specific technique(s)
/analyze --lean                   → Lean mode (abbreviated technique set)
/analyze --comprehensive          → Comprehensive mode (full rubric, adversarial + deception checks)
/analyze --no-osint               → Disable web research
```

Techniques: `customer-checklist`, `issue-redefinition`, `restatement`, `brainstorm`, `kac`, `ach`, `inconsistencies`, `cross-impact`, `what-if`, `premortem`, `counterfactual`, `narratives`, `bowtie`, `opportunities`, `devils-advocacy`, `red-hat`, `alt-futures`, `deception`

Flags combine: `/analyze --guided --no-osint` is valid.

## Q Investigation System Integration

This skill is integrated into the Investigators Copilot investigation system.

### Output Path Override

**All analysis output goes inside the active case folder**, not the project root.

When an active case exists (e.g., `investigations/case-001-example/`), replace every reference to `analyses/{{ANALYSIS_ID}}/` with:

```
investigations/<active-case>/output/analyses/{{ANALYSIS_ID}}/
```

If no active case is identified, ask the founder which case this analysis belongs to.

### Evidence Integration -- Tier 2 Local Files

When collecting Tier 2 (local file) evidence, **always include the active case's collected intelligence**. In addition to generic Glob discovery, explicitly search these directories:

- `investigations/<active-case>/investigation/targets/` -- target profiles with collection status and gaps
- `investigations/<active-case>/investigation/findings/` -- confirmed/assessed findings with confidence levels
- `investigations/<active-case>/investigation/evidence/` -- raw evidence and screenshots
- `investigations/<active-case>/investigation/timelines/` -- chronological event data
- `investigations/<active-case>/canonical/scope.md` -- hypotheses and collection requirements

This is the richest local evidence available. Prioritize it over generic file discovery.

### Feeding Results Back to Q

After any `/analyze` run completes, update the active case:
1. Add key findings to `investigation/findings/` (with citation back to the analysis)
2. Update `memory/investigation-state.md` with analysis summary and which techniques were run
3. If the analysis surfaced new collection gaps, flag them in `investigation-state.md` and suggest `/q-scope` to the founder (file authority: `canonical/` is only updated via `/q-scope`)

### OSINT Note

This system uses Apify/Exa/Jina for OSINT collection (not Firecrawl). When the skill needs web research, it should use the built-in WebSearch and WebFetch tools. For deeper collection, use `/q-osint` or `/q-collect` first, then run `/analyze --no-osint` on the collected evidence.

## Execution

**You MUST read the orchestrator protocol before proceeding.** It contains mode routing, technique selection logic, and the technique routing table.

### Step 0 — Context Inference

Before parsing explicit arguments, scan the conversation history for implicit inputs. Users often invoke `/analyze` mid-conversation after discussing a problem, providing data, or sharing links.

Extract from conversation context:
- **Problem statement**: What is the user trying to analyze? Look for questions, concerns, scenarios, or decisions under discussion.
- **Implicit technique hints**: Did the user mention assumptions, hypotheses, competing explanations, risks, or scenarios? Map these to techniques (e.g., "I'm not sure which explanation is right" → ACH, "what could go wrong" → Premortem).
- **Implicit flags**: Did the user indicate they want something quick (→ `--lean`), don't want web research (→ `--no-osint`), or want to walk through everything (→ `--guided`)?
- **Prior analysis**: Are there existing analyses in the active case's `output/analyses/` for the same topic? (→ suggest `--resume` or `--iterate`)
- **Evidence already provided**: Files shared, URLs pasted, data discussed — these become Tier 1/2 evidence.

### Step 0.1 — Validate Assumptions

If context inference produced any results, present them to the user for confirmation before proceeding:

```
Based on our conversation, here's what I'm picking up:

**Problem**: [inferred problem statement]
**Mode**: [inferred mode + rationale]
**Techniques**: [inferred techniques, if any]
**Flags**: [inferred flags, if any]
**Prior context**: [files, data, or evidence already in conversation]

Does this look right? Adjust anything before I proceed.
```

If the user provided explicit arguments, those always take precedence — but still surface any useful context (e.g., "You asked for ACH. I also noticed you shared [file] earlier — I'll include that as evidence.").

If no conversation context exists and no arguments were provided, proceed directly to Adaptive mode (the orchestrator will prompt for a problem statement).

### Steps 1–6 — Main Execution

1. Read `protocols/orchestrator.md` (relative to this skill's directory)
2. Parse explicit arguments → determine mode and flags (merge with Step 0 inferences, explicit args win)
3. Follow the orchestrator's instructions for the detected mode
4. For technique execution, follow the orchestrator's Technique Execution Contract:
   - **1 technique** (Direct mode): Execute in-context — read protocol, read template, execute SETUP → PRIME → EXECUTE → ARTIFACT → FINDINGS → HANDOFF, write artifact to `{{ANALYSIS_DIR}}/working/`
   - **2+ techniques**: Dispatch to background subagents in dependency-aware tiers — each subagent reads protocol/template, executes the technique, writes the artifact, and returns only a compact findings summary. Main context accumulates summaries and file paths, not full technique work.
5. For evidence gathering: read and execute `protocols/evidence-collector.md`
6. For report synthesis: dispatch per `protocols/report-generator.md` Phase A/B architecture

## Self-Correction (3 Layers)

- **Layer 1** (after each technique, silent): Protocol compliance check — all steps completed? All template sections filled? No unfilled `{{PLACEHOLDER}}` tokens?
- **Layer 2** (before report, silent): Analytical self-critique — 8 checks:
  - 3a. Assumption audit
  - 3b. Evidence balance
  - 3c. Confidence calibration
  - 3d. Alternative check
  - 3e. Missing voices
  - 3f. Internal consistency audit (cross-artifact validation)
  - 3g. Analytical bias scan (sycophancy, anchoring, vividness, completion, authority)
  - 3h. Quality score (quantitative 1-5 with pass/fail threshold)
- **Layer 3** (before finalization): Human review gate — present summary (including quality score), incorporate feedback
- **Auto-Remediation Gate** (between Phase A and Phase B): HIGH-severity Layer 2 flags (evidence imbalance >2:1, unstated critical premises, strong counter-arguments, sycophancy/anchoring bias, quality score < 3.0) trigger automatic remediation — the orchestrator invokes the iteration handler to collect targeted evidence, re-run flagged techniques (max 3), and regenerate the report before the user sees it. Capped at 1 cycle. Zero overhead when no HIGH flags exist.
- **Critique-to-Iteration Bridge** (after results): Remaining MEDIUM/LOW flags from Layer 1 and Layer 2 are mapped to specific technique re-runs and evidence collection focuses, presented as ready-to-run `/analyze --iterate` commands. Only fires when actionable flags exist beyond what auto-remediation already addressed. All flags and their statuses are written to `next-steps.md` in the analysis root — a standalone ledger tracking OPEN, REMEDIATED, RESOLVED, and DEFERRED items across iterations. The `--iterate` handler reads this file as its primary input.

## Citation Requirement

Every claim in every artifact must be cited. No exceptions. Citation methods:
- **OSINT**: `[Source](URL)` — Retrieved: YYYY-MM-DD
- **FILE**: `[filename:line_range]`
- **USER**: `[User-provided, session context]`
- **ANALYSIS**: `[Derived via technique_name]`
- **PRIOR-ITERATION**: `[PRIOR-v{N}: technique_name]`

OSINT is never presented as fact — always "according to [source]".

## Reference Library

For deep background on any technique, read `library/00-prime.md` (relative to this skill's directory) and the specific library files referenced in each protocol. The library contains the full theoretical foundation, axioms, selection matrices, and empirical critiques underlying this skill.
