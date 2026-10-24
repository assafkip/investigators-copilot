#!/usr/bin/env python3
# findings-verify-hook.py -- PostToolUse gate for findings attribution confidence
#
# Wired in .claude/settings.json as a PostToolUse hook on Edit and Write tool calls.
# kipi update safety: .claude/settings.json is NOT overwritten by `kipi update`
# (only q-system/ and plugins/ propagate). The hook wiring entry is safe in project settings.json.
#
# Two checks on a findings file that uses CONFIRMED / HIGH CONFIDENCE language:
#   1. client-claims: an UNVERIFIED identifier from canonical/client-claims.json is cited.
#   2. hard tokens: every ISO date / IPv4 / email / ETH or BTC wallet stated in the finding
#      must appear in a text file (txt/md/json/csv/html) under investigation/evidence/**.
#      Dates on metadata lines (Date:/Updated:/...) or in the file's own name are exempt.
#      Bypass per file: <!-- hard-token-skip -->. Both block with exit 2.
#
# Self-test: python3 findings-verify-hook.py --self-test
import json
import pathlib
import re
import sys
import tempfile
import os

# Not inside "UNCONFIRMED" and not after "not " -- both read as the opposite label and
# blocked legitimate hypothesis writes (post-merge review, ASK-2613).
HIGH_CONFIDENCE_RE = re.compile(
    r"(?<![a-z])(?<!not )(?:CONFIRMED|HIGH[\s\-]+CONFIDENCE)", re.IGNORECASE)
# Any other explicit confidence label on a line ends inheritance of a CONFIRMED label
# from the paragraph or section above it.
OTHER_CONFIDENCE_RE = re.compile(
    r"\b(?:UNCONFIRMED|NOT\s+CONFIRMED|(?:LOW|MODERATE|MEDIUM)[\s\-]+CONFIDENCE|"
    r"POSSIBLE|SPECULATIVE|UNVERIFIED|HYPOTHES[IE]S)\b", re.IGNORECASE)
# Negated forms ("not yet confirmed", "never confirmed", "cannot be confirmed") are
# removed before the CONFIRMED search, and mark the line as non-high (Codex P2, PR #4).
NEGATED_CONFIRM_RE = re.compile(
    r"\b(?:not|never|cannot|can't|couldn't|unable\s+to|yet\s+to)\b(?:\s+\w+){0,2}?\s+confirm(?:ed)?\b",
    re.IGNORECASE)
# The finding template (templates/new-investigation/investigation/findings/_TEMPLATE.md)
# states the label alone under "## Confidence Level": **Confirmed** / **High** / ...
CONFIDENCE_SECTION_RE = re.compile(r"^\s*#+\s*confidence(?:\s+level)?\b", re.IGNORECASE)
TEMPLATE_HIGH_RE = re.compile(r"\b(?:confirmed|high)\b", re.IGNORECASE)
TEMPLATE_OTHER_RE = re.compile(r"\b(?:moderate|medium|low|speculative|possible|unconfirmed)\b",
                               re.IGNORECASE)
# Gate artifacts that live in findings/ and discuss "confirmed" without asserting it.
GATE_ARTIFACT_PREFIXES = ("CHALLENGE-", "REALITY-CHECK-")

# --- Hard-token check (port of kipi investigations/verify.py hard_tokens/unbacked_tokens) ---
# A stated HARD fact (ISO date / IPv4 / email / ETH or BTC wallet) in a CONFIRMED or HIGH
# CONFIDENCE finding must appear verbatim (case-insensitive) somewhere in the case's
# investigation/evidence/** text files. The analyst's say-so is not a source. Soft /
# interpretive claims carry no hard token and are not checked here.
HARD_TOKEN_SKIP = "<!-- hard-token-skip -->"
_HARD_TOKEN_RES = (
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),                                     # ISO date
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),                              # IPv4
    re.compile(r"\b[a-z0-9][a-z0-9._%+-]*@[a-z0-9.-]+\.[a-z]{2,}\b", re.I),  # email
    re.compile(r"\b0x[a-fA-F0-9]{40}\b"),                                    # ETH wallet
    re.compile(r"\b(?:bc1[ac-hj-np-z02-9]{6,87}|BC1[AC-HJ-NP-Z02-9]{6,87}|"
               r"[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b"),                         # BTC wallet
)
_ISO_DATE_RE = _HARD_TOKEN_RES[0]
# Document-metadata lines ("Date: 2026-10-10", "**Last updated:** ...") state when the
# finding was WRITTEN, not a fact about the subject; their dates are not hard claims.
_METADATA_LINE_RE = re.compile(
    r"^\s*(?:[-*>]\s*)?(?:\*\*|__)?\s*(?:id|date|updated|last[\s-]+updated|created|written|"
    r"generated|reviewed|as[\s-]+of)\s*(?:\*\*|__)?\s*:", re.I)
EVIDENCE_TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv", ".html", ".htm"}


def hard_tokens(text: str) -> set:
    """High-precision facts asserted in `text`, lowercased. Empty set = nothing hard."""
    if not text:
        return set()
    out: set = set()
    for rx in _HARD_TOKEN_RES:
        out |= {m.group(0).lower() for m in rx.finditer(text)}
    return out


def unbacked_tokens(claim: str, source_text: str) -> set:
    """Hard tokens asserted in `claim` that do NOT appear in `source_text` (kipi parity)."""
    toks = hard_tokens(claim)
    if not toks:
        return set()
    src = (source_text or "").lower()
    return {t for t in toks if t not in src}


def _line_level(line: str):
    """'high', 'other' or None: the confidence label a single line carries."""
    stripped, negations = NEGATED_CONFIRM_RE.subn(" ", line)
    if HIGH_CONFIDENCE_RE.search(stripped):
        return "high"
    if negations or OTHER_CONFIDENCE_RE.search(stripped):
        return "other"
    return None


def template_confidence(content: str):
    """'high', 'other' or None: the label stated under a "## Confidence Level" heading.
    In the template the label sits alone in that section and the evidence lives in
    OTHER sections, so it is the document's default label (Codex P1, PR #4)."""
    in_section = False
    for line in content.splitlines():
        if line.lstrip().startswith("#"):
            in_section = bool(CONFIDENCE_SECTION_RE.match(line))
            continue
        if not in_section or not line.strip():
            continue
        if TEMPLATE_OTHER_RE.search(line):
            return "other"
        if TEMPLATE_HIGH_RE.search(line):
            return "high"
    return None


def confident_lines(content: str) -> list:
    """Lines whose effective label is CONFIRMED/HIGH: their own label, else the
    paragraph's, else the section heading's. The check is per finding, not per file,
    so a LOW-confidence finding next to a CONFIRMED one is not checked."""
    out, section, para = [], None, None
    default = template_confidence(content)
    for line in content.splitlines():
        if not line.strip():
            para = None
            continue
        level = _line_level(line)
        if line.lstrip().startswith("#"):
            section, para = level, None
            continue
        if level:
            para = level
        if (para or section or default) == "high":
            out.append(line)
    return out


def finding_hard_tokens(file_path: pathlib.Path, content: str) -> set:
    """Hard tokens of the CONFIRMED/HIGH parts of a finding, minus document-metadata
    dates (metadata lines and a date that is part of the finding's own filename)."""
    claim_lines = [ln for ln in confident_lines(content) if not _METADATA_LINE_RE.match(ln)]
    toks = hard_tokens("\n".join(claim_lines))
    own_dates = {m.group(0) for m in _ISO_DATE_RE.finditer(file_path.name)}
    return toks - own_dates


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MONTH_RE = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_MDY_RE = re.compile(_MONTH_RE + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", re.I)
_DMY_RE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+" + _MONTH_RE + r",?\s+(\d{4})", re.I)


def iso_dates_in(text: str) -> set:
    """ISO forms of month-name dates ("March 14, 2026", "14 Mar 2026") in evidence, so
    a finding that states 2026-03-14 is backed by evidence that spells the month."""
    out = set()
    for mon, day, year in _MDY_RE.findall(text):
        out.add(f"{year}-{_MONTHS[mon.lower()]:02d}-{int(day):02d}")
    for day, mon, year in _DMY_RE.findall(text):
        out.add(f"{year}-{_MONTHS[mon.lower()]:02d}-{int(day):02d}")
    return out


def unbacked_in_evidence(case_root: pathlib.Path, tokens: set) -> set:
    """Tokens not found in any text file under <case>/investigation/evidence/**."""
    missing = set(tokens)
    evidence = case_root / "investigation" / "evidence"
    if not evidence.is_dir():
        return missing
    for path in sorted(evidence.rglob("*")):
        if not missing:
            break
        if not path.is_file() or path.suffix.lower() not in EVIDENCE_TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"[findings-verify-hook] WARN: cannot read {path}: {exc}", file=sys.stderr)
            continue
        low = text.lower() + "\n" + " ".join(iso_dates_in(text))
        missing = {t for t in missing if t not in low}
    return missing


def check_hard_tokens(fp: pathlib.Path, content: str, case_root: pathlib.Path) -> int:
    if HARD_TOKEN_SKIP in content or fp.name.upper().startswith(GATE_ARTIFACT_PREFIXES):
        return 0
    tokens = finding_hard_tokens(fp, content)
    if not tokens:
        return 0
    missing = unbacked_in_evidence(case_root, tokens)
    if not missing:
        return 0
    listed = "\n".join(f"  - {t}" for t in sorted(missing))
    print(
        f"\n[findings-verify-hook] BLOCKED: this HIGH CONFIDENCE / CONFIRMED finding states "
        f"{len(missing)} hard fact(s) that appear nowhere under "
        f"{case_root.name}/investigation/evidence/ (txt/md/json/csv/html):\n{listed}\n"
        f"Remediation: capture the source (capture-evidence.sh / extract-intake.py) so the "
        f"token is in evidence, correct the token, or downgrade the confidence. If the token "
        f"is genuinely not a factual claim, add {HARD_TOKEN_SKIP} to the file.\n",
        file=sys.stderr,
    )
    return 2


def find_case_root(findings_path: pathlib.Path) -> pathlib.Path | None:
    """Walk up from the findings file to the case root (contains canonical/)."""
    p = findings_path.parent
    while p != p.parent:
        if (p / "canonical").is_dir():
            return p
        p = p.parent
    return None


def check_findings_file(file_path: str, content: str) -> int:
    """
    Returns 0 (pass) or 2 (block).
    Blocks if content contains HIGH CONFIDENCE or CONFIRMED and any identifier
    in the case's client-claims.json is still UNVERIFIED.
    """
    fp = pathlib.Path(file_path)

    # Scope guard: only fires on investigation findings files
    pattern = re.compile(r"investigations/.+/investigation/findings/.+\.md$")
    if not pattern.search(str(fp)):
        return 0

    # Check for high-confidence language (inline, or the template's Confidence Level)
    if not HIGH_CONFIDENCE_RE.search(content) and template_confidence(content) != "high":
        return 0

    # Find the case root
    case_root = find_case_root(fp)
    if not case_root:
        return 0

    claims_result = check_client_claims(content, case_root)
    if claims_result:
        return claims_result
    return check_hard_tokens(fp, content, case_root)


def check_client_claims(content: str, case_root: pathlib.Path) -> int:
    """Block when an UNVERIFIED client-claims.json identifier is cited."""
    claims_path = case_root / "canonical" / "client-claims.json"
    if not claims_path.exists():
        # No claims file -- legacy case, nothing to check here
        return 0

    claims = json.loads(claims_path.read_text())
    unverified = [
        e["value"]
        for e in claims.get("identifiers", [])
        if e.get("status", "UNVERIFIED") == "UNVERIFIED"
    ]

    if not unverified:
        return 0

    # Check if any unverified identifier appears in the file content
    for identifier in unverified:
        if identifier.lower() in content.lower():
            case_name = case_root.name
            print(
                f"\n[findings-verify-hook] BLOCKED: '{identifier}' is cited in a HIGH CONFIDENCE or CONFIRMED finding "
                f"but is still UNVERIFIED in {case_name}/canonical/client-claims.json\n"
                f"Remediation: run check-collision.sh {identifier} <type> {case_root} to verify the identifier first.\n",
                file=sys.stderr,
            )
            return 2

    return 0


def _expect(label: str, got: int, want: int) -> int:
    if got == want:
        print(f"PASS {label}")
        return 0
    print(f"FAIL {label}: expected exit {want}, got {got}", file=sys.stderr)
    return 1


def hard_token_self_tests() -> int:
    """Tests 6-12: hard-token backing against investigation/evidence/**."""
    with tempfile.TemporaryDirectory() as tmp:
        case = pathlib.Path(tmp) / "workspace" / "investigations" / "case-hard-tokens"
        findings = case / "investigation" / "findings"
        evidence = case / "investigation" / "evidence" / "items" / "EV-0001-x"
        findings.mkdir(parents=True)
        evidence.mkdir(parents=True)
        (case / "canonical").mkdir()
        (evidence / "content.md").write_text(
            "Resolved 45.11.181.44 on 2026-03-14; contact Ops@Bad-Domain.xyz; "
            "paid 0xAbCdEf0123456789aBcDeF0123456789AbCdEf01.")
        target = str(findings / "FINDINGS-2026-10-10.md")
        backed = ("CONFIRMED: host 45.11.181.44 seen 2026-03-14, email ops@bad-domain.xyz, "
                  "wallet 0xabcdef0123456789abcdef0123456789abcdef01.")
        unbacked = "HIGH CONFIDENCE: the actor used 203.0.113.77 on 2026-01-01."
        fails = 0
        fails += _expect("Test 6: hard tokens all backed by evidence -> pass",
                         check_findings_file(target, backed), 0)
        fails += _expect("Test 7: unbacked IPv4 + date in CONFIRMED finding -> block",
                         check_findings_file(target, unbacked), 2)
        fails += _expect("Test 8: bypass marker skips the hard-token check",
                         check_findings_file(target, unbacked + "\n" + HARD_TOKEN_SKIP), 0)
        fails += _expect("Test 9: unbacked token without CONFIRMED/HIGH language -> pass",
                         check_findings_file(target, "Possible: the actor used 203.0.113.77."), 0)
        meta = "Date: 2026-12-31\nCONFIRMED (2026-10-10): soft claim with no hard facts."
        fails += _expect("Test 10: metadata-line date and filename date are not claims",
                         check_findings_file(target, meta), 0)
        btc = "CONFIRMED: payout to bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq."
        fails += _expect("Test 11: unbacked BTC wallet -> block", check_findings_file(target, btc), 2)
        bare = pathlib.Path(tmp) / "workspace" / "investigations" / "case-no-evidence"
        (bare / "canonical").mkdir(parents=True)
        (bare / "investigation" / "findings").mkdir(parents=True)
        fails += _expect("Test 12: no evidence dir at all -> block on a hard token",
                         check_findings_file(str(bare / "investigation" / "findings" / "F.md"),
                                             unbacked), 2)
        fails += _expect("Test 13: UNCONFIRMED / not confirmed is not a CONFIRMED label",
                         check_findings_file(target, "Status: UNCONFIRMED. Not confirmed: "
                                             "203.0.113.77 was used."), 0)
        fails += _expect("Test 14: CHALLENGE-*.md gate artifact is not hard-token checked",
                         check_findings_file(str(findings / "CHALLENGE-2026-10-10.md"),
                                             "Is it confirmed? Alternative host 203.0.113.77."), 0)
        mixed = ("Finding 1 (CONFIRMED): soft claim.\n"
                 "Finding 2 (LOW confidence): 203.0.113.9 may be related.")
        fails += _expect("Test 15: LOW-confidence finding beside a CONFIRMED one -> pass",
                         check_findings_file(target, mixed), 0)
        fails += _expect("Test 16: tokens under a CONFIRMED heading are still checked",
                         check_findings_file(target, "## Finding 3 -- CONFIRMED\n\n"
                                             "Host 203.0.113.9 served the kit."), 2)
        (evidence / "page.md").write_text("Registered on March 2, 2026 per the registrar.")
        fails += _expect("Test 17: month-name evidence date backs an ISO date",
                         check_findings_file(target, "CONFIRMED: registered 2026-03-02."), 0)
        tmpl = ("# Finding: kit host\n\n> ID: F-001 | Created: 2026-01-02 | Last updated: 2026-01-03\n\n"
                "## Summary\n\nThe kit was served from 203.0.113.9.\n\n"
                "## Confidence Level\n\n**High**\n\n## Supporting Evidence\n\n| x | y |\n")
        fails += _expect("Test 18: template finding (label alone under Confidence Level) is checked",
                         check_findings_file(target, tmpl), 2)
        fails += _expect("Test 19: template finding with a Low label is not checked",
                         check_findings_file(target, tmpl.replace("**High**", "**Low**")), 0)
        fails += _expect("Test 20: template ID/Created metadata line dates are not claims",
                         check_findings_file(target, tmpl.replace("203.0.113.9", "the panel")), 0)
        for neg in ("not yet confirmed", "never confirmed", "cannot be confirmed"):
            fails += _expect(f"Test 21: '{neg}' is not a CONFIRMED label",
                             check_findings_file(target, f"Attribution {neg}: 203.0.113.77."), 0)
        assert unbacked_tokens("seen 1.2.3.4", "log: 1.2.3.4") == set()
        assert unbacked_tokens("soft claim", "") == set()
    return fails


def self_test() -> int:
    print("=== findings-verify-hook.py --self-test ===")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)

        # Build a fake case structure
        case_path = tmp_path / "workspace" / "investigations" / "case-test-selftest"
        findings_dir = case_path / "investigation" / "findings"
        canonical_dir = case_path / "canonical"
        findings_dir.mkdir(parents=True)
        canonical_dir.mkdir(parents=True)

        claims = {
            "subject_name": "Test Subject",
            "identifiers": [
                {"value": "unverifiedhandle", "type": "username", "status": "UNVERIFIED", "verified_by": ""},
                {"value": "verifiedhandle", "type": "username", "status": "VERIFIED", "verified_by": "dataset-collision-check"},
            ],
        }
        (canonical_dir / "client-claims.json").write_text(json.dumps(claims, indent=2))

        findings_file = str(findings_dir / "FINDINGS-2026-06-26.md")

        # Test 1: block on CONFIRMED + UNVERIFIED identifier
        content_block = "## Attribution\n\nCONFIRMED: unverifiedhandle belongs to the subject."
        result = check_findings_file(findings_file, content_block)
        if result == 2:
            print("PASS Test 1: blocked on CONFIRMED + UNVERIFIED identifier")
        else:
            print(f"FAIL Test 1: expected exit 2, got {result}", file=sys.stderr)
            return 1

        # Test 2: block on HIGH CONFIDENCE (mixed case) + UNVERIFIED identifier
        content_block2 = "High Confidence -- unverifiedhandle is the primary account."
        result = check_findings_file(findings_file, content_block2)
        if result == 2:
            print("PASS Test 2: blocked on 'High Confidence' (mixed case)")
        else:
            print(f"FAIL Test 2: expected exit 2, got {result}", file=sys.stderr)
            return 1

        # Test 3: no-op when identifier is VERIFIED
        content_ok = "HIGH CONFIDENCE: verifiedhandle is attributed to the subject."
        result = check_findings_file(findings_file, content_ok)
        if result == 0:
            print("PASS Test 3: pass when cited identifier is VERIFIED")
        else:
            print(f"FAIL Test 3: expected exit 0, got {result}", file=sys.stderr)
            return 1

        # Test 4: no-op on non-findings file path
        non_findings = str(tmp_path / "workspace" / "investigations" / "case-test" / "output" / "report.md")
        result = check_findings_file(non_findings, content_block)
        if result == 0:
            print("PASS Test 4: no-op on out-of-scope file path")
        else:
            print(f"FAIL Test 4: expected exit 0, got {result}", file=sys.stderr)
            return 1

        # Test 5: no-op when no client-claims.json (legacy case)
        legacy_case = tmp_path / "workspace" / "investigations" / "case-legacy"
        legacy_findings = legacy_case / "investigation" / "findings"
        legacy_findings.mkdir(parents=True)
        (legacy_case / "canonical").mkdir()
        result = check_findings_file(str(legacy_findings / "FINDINGS.md"), content_block)
        if result == 0:
            print("PASS Test 5: no-op when client-claims.json is absent (legacy case)")
        else:
            print(f"FAIL Test 5: expected exit 0, got {result}", file=sys.stderr)
            return 1

    failed = hard_token_self_tests()
    if failed:
        return failed

    print("\n=== ALL SELF-TESTS PASSED ===")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        return self_test()

    # Hook invocation: read JSON from stdin (Claude Code PostToolUse hook format)
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Edit", "Write", "MultiEdit"):
        return 0

    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    # PostToolUse: the file on disk is the result of the edit. Checking only new_string
    # missed a token added under a CONFIRMED label outside the edited span (ASK-2613).
    content = ""
    try:
        content = pathlib.Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        content = tool_input.get("new_string", "") or tool_input.get("content", "")

    return check_findings_file(file_path, content)


if __name__ == "__main__":
    sys.exit(main())
