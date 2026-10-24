"""Deterministic investigation-scope gate ("leads first"), for the Investigators Copilot workspace stack.

Ported 2026-10-10 from kipi investigations/agent/scope.py. Same contract: a tool call
that INVESTIGATES a target already in the case roster is allowed; a target the agent
just surfaced (not in the roster) is DENIED and becomes a LEAD for the founder to
promote by adding it to canonical/scope.md (via /q-scope). Network-enumeration tools
(reverse-WHOIS, DNS history, reverse-IP, recursive recon frameworks) are always a
lead, even on an in-roster entity, because their output IS the network expansion.

Roster source: the active case's canonical/scope.md "## Targets" section (table
first column and bullets; domains, emails, handles and IPs found inside each cell are
added too), plus an optional extra file named by $Q_SCOPE_EXTRA (one entity per line).

Pure + stdlib-only so the hook subprocess can import it cheaply.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

# MCP tools (any server) that investigate one specific entity. Matched on the
# tool-name suffix after mcp__<server>__.
_TARGETED_MCP = {
    "whois_lookup", "whois", "rdap", "dns_lookup", "dns", "dig", "reverse_dns",
    "virustotal", "vt_lookup", "crtsh", "crtsh_subdomains", "crt_lookup", "urlhaus",
    "threatfox", "abusech", "shodan_host", "censys_host", "breach_intel", "social_scrape",
    "browser_navigate", "jina_read", "wayback", "wayback_lookup", "reddit_user_history",
}
_ENUMERATION_MCP = {"reverse_whois", "dns_history", "reverse_ip", "subdomain_enum"}
_SEARCH_MCP = {"web_search", "tavily_search", "exa_search", "perplexity_ask", "perplexity_search",
               "perplexity_research", "brave_search", "search"}

# osint-tool.py slugs that expand the network from one seed (always a lead).
_ENUMERATION_SLUGS = {"reverse_ip", "reverse-ip", "bbot", "spiderfoot", "theharvester", "typosquat"}
# Search scripts: allowed unless the query NAMES an out-of-scope domain/IP.
_SEARCH_SCRIPTS = ("perplexity.sh", "exa.sh", "tavily.sh", "first-volley.sh", "perplexity-playbook.sh",
                   "parallel.sh")
# Entity commands: first positional argument is the target.
_ENTITY_COMMANDS = {"whois", "dig", "nslookup", "host"}

_DOMAIN_RE = re.compile(r"\b([a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9-]+)*\.[a-z]{2,})\b", re.I)
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_HANDLE_RE = re.compile(r"(?<![\w.])@[A-Za-z0-9_.]{2,}")
_SCRIPT_EXT = re.compile(r"\.(sh|py|js|md|json|txt|csv|tsv|html)$", re.I)


def _norm(value: str) -> str:
    """Lowercase, strip scheme, leading www., path, query and port."""
    v = (value or "").strip().strip("\"'").lower()
    if "@" in v and not v.startswith("@") and _EMAIL_RE.fullmatch(v):
        return v
    v = re.sub(r"^[a-z][a-z0-9+.-]*://", "", v)
    v = v.split("/")[0].split("?")[0].split("#")[0]
    if not v.startswith("["):
        v = v.split(":")[0]
    if v.startswith("www."):
        v = v[4:]
    return v.strip()


def normalize_roster(names) -> set[str]:
    out = set()
    for n in names or []:
        n = str(n).strip()
        if n:
            out.add(_norm(n))
            if n.startswith("@"):
                out.add(n[1:].lower())
    out.discard("")
    return out


# ---------- roster from scope.md ----------

def _section(text: str, heading: str) -> str:
    m = re.search(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S | re.I)
    return m.group(1) if m else ""


def _entities_in(cell: str) -> list[str]:
    cell = re.sub(r"[`*]", "", cell)
    found = _EMAIL_RE.findall(cell)
    rest = _EMAIL_RE.sub(" ", cell)
    found += [m.group(0) for m in re.finditer(r"https?://\S+", rest)]
    found += _DOMAIN_RE.findall(rest)
    found += _IPV4_RE.findall(rest)
    found += _HANDLE_RE.findall(rest)
    found += re.findall(r"(?:t\.me|telegram\.me)/[A-Za-z0-9_+/-]+", rest)
    return found


def roster_from_scope_text(text: str) -> set[str]:
    names: list[str] = []
    body = _section(text, "Targets")
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not cells or re.match(r"^:?-{2,}:?$", cells[0]) or cells[0].lower() in ("target", ""):
                continue
            first = cells[0]
            names.append(re.sub(r"[`*]", "", first))
            names += _entities_in(" ".join(cells[:2]))
        elif re.match(r"^[-*+]\s+", s):
            item = re.sub(r"^[-*+]\s+", "", s)
            names.append(re.split(r"\s+[-(:]", re.sub(r"[`*]", "", item))[0])
            names += _entities_in(item)
    return normalize_roster(n for n in names if n and not re.fullmatch(r"[_\-\s]*", n))


def load_roster(case_dir: Path, extra_file: str = "") -> set[str]:
    roster: set[str] = set()
    scope = case_dir / "canonical" / "scope.md"
    if scope.is_file():
        roster |= roster_from_scope_text(scope.read_text(encoding="utf-8", errors="replace"))
    if extra_file and Path(extra_file).is_file():
        roster |= normalize_roster(Path(extra_file).read_text(encoding="utf-8").splitlines())
    return roster


# ---------- target extraction ----------

def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(command, comments=False)
    except ValueError:
        return command.split()


def _positional_after(tokens: list[str], idx: int) -> list[str]:
    out, skip = [], False
    for t in tokens[idx + 1:]:
        if t in ("|", "&&", ";", "||", ">", ">>"):
            break
        if skip:
            skip = False
            continue
        if t.startswith("-"):
            skip = t in ("--mode", "--case", "--depth", "--max-pages", "--out", "--timeout", "-t", "--type")
            continue
        out.append(t)
    return out


def bash_call(command: str) -> tuple[str, str | None, str | None]:
    """Classify a Bash command -> (kind, target, query).

    kind: 'enumeration' | 'entity' | 'search' | 'other'."""
    toks = _tokens(command)
    for i, t in enumerate(toks):
        base = t.rsplit("/", 1)[-1]
        if base == "osint-tool.py":
            pos = _positional_after(toks, i)
            if not pos:
                return "other", None, None
            slug = pos[0].lower()
            target = pos[1] if len(pos) > 1 else None
            if slug in _ENUMERATION_SLUGS:
                return "enumeration", target, None
            return "entity", target, None
        if base in _SEARCH_SCRIPTS:
            pos = _positional_after(toks, i)
            return "search", None, " ".join(pos)
        if base == "crawl.sh":
            pos = _positional_after(toks, i)
            if len(pos) >= 2:
                return "entity", pos[1], None
        if base in _ENTITY_COMMANDS:
            pos = [p for p in _positional_after(toks, i) if not p.startswith("@") and not p.isupper()]
            if pos:
                return "entity", pos[-1] if base == "dig" else pos[0], None
    return "other", None, None


def _mcp_name(tool_name: str) -> str:
    return (tool_name or "").rsplit("__", 1)[-1].lower()


def _mcp_target(ti: dict) -> str | None:
    for key in ("target", "url", "domain", "indicator", "ip", "ip_address", "host", "hostname",
                "registrant", "email", "username", "handle", "query"):
        v = ti.get(key)
        if v:
            return str(v)
    return None


def in_scope(target: str, roster: set[str]) -> bool:
    if not target:
        return True
    t = _norm(target)
    if t in roster or t.lstrip("@") in roster:
        return True
    return any(t.endswith("." + r) for r in roster if "." in r)


def _outside(text: str, roster: set[str]) -> list[str]:
    cands = [_norm(m) for m in _DOMAIN_RE.findall(text or "") if not _SCRIPT_EXT.search(m)]
    cands += [_norm(m) for m in _IPV4_RE.findall(text or "")]
    return [c for c in cands if c and not in_scope(c, roster)]


def _deny(target: str, verb: str = "investigate") -> str:
    return (f"out of scope: '{target}' is not a target in canonical/scope.md. Do not {verb} it; "
            "record it as a LEAD in your findings and ask the founder to add it via /q-scope.")


def _deny_enum(target: str) -> str:
    return (f"network enumeration on '{target}' expands the case to other infrastructure. "
            "Do not run it; surface the pivot as a LEAD. The founder decides whether to expand scope.")


def gate(tool_name: str, tool_input: dict, roster: set[str]) -> tuple[bool, str]:
    """Deterministic (allow, reason)."""
    ti = tool_input or {}
    name = _mcp_name(tool_name)
    if name == "bash":
        kind, target, query = bash_call(str(ti.get("command", "")))
        if kind == "enumeration":
            return False, _deny_enum(target or "this entity")
        if kind == "entity" and target:
            return (True, "") if in_scope(target, roster) else (False, _deny(_norm(target)))
        if kind == "search" and query:
            out = _outside(query, roster)
            return (False, _deny(out[0], "search for")) if out else (True, "")
        return True, ""
    if (tool_name or "").startswith("mcp__"):
        if name in _ENUMERATION_MCP:
            return False, _deny_enum(_mcp_target(ti) or "this entity")
        if name in _TARGETED_MCP:
            target = _mcp_target(ti)
            if target and not in_scope(target, roster):
                return False, _deny(_norm(target))
            return True, ""
        if name in _SEARCH_MCP or "search" in name:
            q = str(ti.get("query") or ti.get("q") or "")
            out = _outside(q, roster)
            return (False, _deny(out[0], "search for")) if out else (True, "")
    if name in ("webfetch",):
        target = str(ti.get("url", ""))
        if target and not in_scope(target, roster):
            return False, _deny(_norm(target), "fetch")
    return True, ""
