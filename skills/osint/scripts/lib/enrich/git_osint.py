"""Git commit-author email mining. Keyless (system git), T3.

Ported from assafkip/kipi investigations/enrich/git_osint.py. Public repos leak
the commit-author emails of whoever pushed them. Query is a github/gitlab repo
URL, or a GitHub handle (its most recently pushed non-fork repos are mined).

GITHUB_TOKEN is optional: it only lifts the GitHub API rate limit (60 -> 5000/h)
for the handle -> repo lookup. A mined email is a LEAD: it corroborates an email
from another independent source, it never anchors an identity on its own.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import urllib.parse

from ._identity_common import SETUP_HINT, T3_NOTE, clean_handle, fetch, github_headers, lead
from .base import Adapter, EnrichmentError, NotConfiguredError

REPO_URL_RE = re.compile(r"^https?://(github\.com|gitlab\.com)/[\w.-]+/[\w.-]+?(\.git)?/?$", re.I)
MAX_REPOS = 3


def mine_repo(repo_url: str, timeout: int = 90) -> list[tuple[str, str]]:
    """(email, name) pairs from a bare, blobless clone's full history."""
    url = repo_url.rstrip("/")
    url = url if url.endswith(".git") else url + ".git"
    with tempfile.TemporaryDirectory() as tmp:
        try:
            subprocess.run(["git", "clone", "--quiet", "--bare", "--filter=blob:none", url, tmp],
                           capture_output=True, timeout=timeout, check=True, stdin=subprocess.DEVNULL,
                           env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
            log = subprocess.run(["git", "--git-dir", tmp, "log", "--all", "--format=%ae|%an"],
                                 capture_output=True, timeout=timeout, check=True)
        except FileNotFoundError as exc:
            raise NotConfiguredError("git_osint: git not installed (" + SETUP_HINT.format(name="git") + ")") from exc
        except subprocess.CalledProcessError as exc:
            raise EnrichmentError(f"git_osint: {url}: {exc.stderr.decode('utf-8', 'replace')[:200]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise EnrichmentError(f"git_osint: {url} timed out after {timeout}s") from exc
    return parse_log(log.stdout.decode("utf-8", "replace"))


def parse_log(text: str) -> list[tuple[str, str]]:
    seen, out = set(), []
    for line in text.splitlines():
        email, _, name = line.partition("|")
        email = email.strip().lower()
        if "@" in email and email not in seen and "noreply" not in email:
            seen.add(email)
            out.append((email, name.strip()))
    return out


def repos_for_handle(handle: str, timeout: int) -> list[str]:
    """Up to MAX_REPOS recently pushed non-fork clone URLs (forks only as fallback)."""
    url = f"https://api.github.com/users/{urllib.parse.quote(handle)}/repos?per_page=20&sort=pushed"
    status, body = fetch(url, timeout=timeout, headers=github_headers())
    if status == 404:
        return []
    if status != 200:
        raise EnrichmentError(f"git_osint: GitHub API HTTP {status} for {handle} (set GITHUB_TOKEN if 403)")
    try:
        repos = [r for r in json.loads(body) if isinstance(r, dict) and r.get("clone_url")]
    except (json.JSONDecodeError, TypeError) as exc:
        raise EnrichmentError("git_osint: unexpected GitHub API body") from exc
    own = [r["clone_url"] for r in repos if not r.get("fork")]
    return (own or [r["clone_url"] for r in repos])[:MAX_REPOS]


class GitOsintAdapter(Adapter):
    slug = "git_osint"
    display_name = "Git commit-author email mining"
    category = "identity"
    tier = "T3"
    requires_bin = ("git",)
    watched_types = ("handle", "url")

    def run(self, query, mode=None, timeout=90):
        q = (query or "").strip()
        if REPO_URL_RE.match(q):
            repos = [q]
        else:
            repos = repos_for_handle(clean_handle(q, self.slug), min(timeout, 30))
            if not repos:
                return [lead(f"git_osint: {q} -- no public GitHub repos", "Nothing to mine for this handle.",
                             rtype="document")]
        rows = []
        for repo in repos:
            rows += self._mine(repo, timeout)
        return rows

    def _mine(self, repo: str, timeout: int):
        pairs = mine_repo(repo, timeout)
        listing = "\n".join(f"- {e} ({n})" for e, n in pairs[:25])
        header = lead(f"git_osint: {repo} -- {len(pairs)} author email(s)",
                      f"Commit-author emails:\n{listing}\n{T3_NOTE}", url=repo.removesuffix(".git"),
                      raw={"repo": repo, "emails": [e for e, _ in pairs]}, rtype="document", confidence="medium")
        return [header] + [lead(email, f"Commit author '{name}' in {repo}. Corroborate before use.",
                                raw={"repo": repo, "author_name": name}, rtype="record") for email, name in pairs]
