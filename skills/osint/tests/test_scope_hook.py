"""Opt-in scope + budget PreToolUse hooks: roster from scope.md, gate decisions, fail-open."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "scripts" / "hooks"
sys.path.insert(0, str(HOOKS))
import budget  # noqa: E402
import scope  # noqa: E402

SCOPE_MD = """# Investigation Scope

## Targets

| Target | Type | Status | Priority |
|--------|------|--------|----------|
| Acme Holdings (acme-corp.com) | company | active | P1 |
| @shadyseller | handle | active | P1 |
| 198.51.100.7 | ip | active | P2 |
| | | | |

- ops@acme-corp.com (registrant email)

## Hypotheses

| ID | Hypothesis |
|----|-----------|
| H1 | evil-other.com is related |
"""


@pytest.fixture
def roster():
    return scope.roster_from_scope_text(SCOPE_MD)


def test_roster_parsing(roster):
    assert {"acme-corp.com", "@shadyseller", "shadyseller", "198.51.100.7", "ops@acme-corp.com"} <= roster
    assert "evil-other.com" not in roster  # hypotheses section is not scope


@pytest.mark.parametrize("cmd,allowed", [
    ("python3 skills/osint/scripts/osint-tool.py crtsh acme-corp.com --case x", True),
    ("python3 scripts/osint-tool.py crtsh https://www.mail.acme-corp.com/login", True),   # subdomain + url
    ("python3 scripts/osint-tool.py crtsh evil-other.com", False),
    ("python3 scripts/osint-tool.py --json shodan 198.51.100.7", True),
    ("python3 scripts/osint-tool.py reverse_ip acme-corp.com", False),                    # enumeration
    ("python3 scripts/osint-tool.py maigret shadyseller", True),
    ("python3 scripts/osint-tool.py maigret otheruser", False),
    ("whois acme-corp.com", True),
    ("whois evil-other.com | head", False),
    ("dig +short TXT evil-other.com", False),
    ("dig acme-corp.com MX", True),
    ("bash scripts/perplexity.sh search 'who runs acme-corp.com'", True),
    ("bash scripts/perplexity.sh search 'is evil-other.com linked to acme'", False),
    ("bash scripts/first-volley.sh 'Acme Holdings' 'fraud'", True),
    ("bash scripts/crawl.sh fetch https://acme-corp.com/about", True),
    ("bash scripts/crawl.sh deep https://evil-other.com --depth 2", False),
    ("bash scripts/capture-evidence.sh https://news.example/story slug", True),            # preservation not gated
    ("ls -la && cat notes.md", True),
])
def test_bash_gate(roster, cmd, allowed):
    ok, reason = scope.gate("Bash", {"command": cmd}, roster)
    assert ok is allowed, (cmd, reason)
    if not ok:
        assert "LEAD" in reason


def test_mcp_gate(roster):
    assert scope.gate("mcp__osint-infra__whois_lookup", {"domain": "acme-corp.com"}, roster)[0]
    assert not scope.gate("mcp__osint-infra__whois_lookup", {"domain": "evil-other.com"}, roster)[0]
    assert not scope.gate("mcp__threat-intel__reverse_whois", {"registrant": "ops@acme-corp.com"}, roster)[0]
    assert scope.gate("mcp__perplexity-ask__perplexity_ask", {"query": "acme-corp.com owner"}, roster)[0]
    assert not scope.gate("mcp__perplexity-ask__perplexity_ask", {"query": "evil-other.com owner"}, roster)[0]
    assert scope.gate("Read", {"file_path": "/x/evil-other.com.md"}, roster)[0]


def _run_hook(script, event, env):
    return subprocess.run([sys.executable, str(HOOKS / script)], input=json.dumps(event),
                          capture_output=True, text=True, env=env, timeout=20)


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "workspace"
    case = ws / "investigations" / "case-999-test"
    (case / "canonical").mkdir(parents=True)
    (case / "memory").mkdir()
    (case / "canonical" / "scope.md").write_text(SCOPE_MD)
    (ws / ".active-case").write_text("case-999-test\n")
    return ws


def test_scope_hook_subprocess_deny_allow_and_fail_open(workspace):
    env = {"Q_WORKSPACE": str(workspace), "PATH": "/usr/bin:/bin"}
    deny = _run_hook("scope_hook.py", {"tool_name": "Bash", "tool_input": {"command": "whois evil-other.com"}}, env)
    assert deny.returncode == 0
    out = json.loads(deny.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "evil-other.com" in out["permissionDecisionReason"]
    allow = _run_hook("scope_hook.py", {"tool_name": "Bash", "tool_input": {"command": "whois acme-corp.com"}}, env)
    assert allow.returncode == 0 and allow.stdout == ""
    # kill switch
    off = _run_hook("scope_hook.py", {"tool_name": "Bash", "tool_input": {"command": "whois evil-other.com"}},
                    {**env, "Q_SCOPE_HOOK": "0"})
    assert off.stdout == ""
    # garbage stdin -> fail open
    bad = subprocess.run([sys.executable, str(HOOKS / "scope_hook.py")], input="not json",
                         capture_output=True, text=True, env=env, timeout=20)
    assert bad.returncode == 0 and bad.stdout == ""
    # no active case -> no gate
    (workspace / ".active-case").write_text("")
    none = _run_hook("scope_hook.py", {"tool_name": "Bash", "tool_input": {"command": "whois evil-other.com"}}, env)
    assert none.stdout == ""


def test_budget_charge_and_deny(tmp_path):
    path = str(tmp_path / "b.json")
    budget.write_budget(path, 2)
    assert budget.check_and_charge(path) == (True, 1, 2)
    assert budget.check_and_charge(path) == (True, 2, 2)
    assert budget.check_and_charge(path) == (False, 3, 2)
    (tmp_path / "zero.json").write_text('{"cap": 0, "count": 5}')
    assert budget.check_and_charge(str(tmp_path / "zero.json"))[0] is True
    assert budget.check_and_charge(str(tmp_path / "missing.json"))[0] is True


def test_budget_hook_subprocess(workspace):
    env = {"Q_WORKSPACE": str(workspace), "PATH": "/usr/bin:/bin"}
    ev = {"tool_name": "Bash", "tool_input": {"command": "whois acme-corp.com"}}
    # unarmed: no-op
    assert _run_hook("budget_hook.py", ev, env).stdout == ""
    budget_file = workspace / "investigations" / "case-999-test" / "memory" / "tool-budget.json"
    budget.write_budget(str(budget_file), 1)
    assert _run_hook("budget_hook.py", ev, env).stdout == ""
    second = _run_hook("budget_hook.py", ev, env)
    assert json.loads(second.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert json.loads(budget_file.read_text()) == {"cap": 1, "count": 2}
    # broken workspace -> fail open
    assert _run_hook("budget_hook.py", ev, {"Q_WORKSPACE": str(workspace / "nope"), "PATH": "/usr/bin:/bin"}).stdout == ""
