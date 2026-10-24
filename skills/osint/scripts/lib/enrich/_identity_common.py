"""Shared helpers for the people / identity adapters (Phase 3).

Underscore-prefixed so registry.py skips it as a module; the classes defined
here have an empty slug, so they are never registered as adapters either.

Every identity result is T3 (.claude/rules/q-investigation.md): a username hit,
a self-asserted profile field, or a tool's account-enumeration answer is a
hypothesis lead. Attribution needs 2 independent T1/T2 crosslinks.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .base import USER_AGENT, Adapter, EnrichmentError, EnrichmentResult, NotConfiguredError

HANDLE_RE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
T3_NOTE = "T3 lead: corroborate with 2 independent T1/T2 crosslinks before attribution."
SETUP_HINT = "run skills/osint/scripts/setup-tools.sh --only {name}"


def clean_handle(query: str, slug: str) -> str:
    handle = (query or "").strip().lstrip("@")
    if not HANDLE_RE.match(handle):
        raise EnrichmentError(f"{slug}: pass a bare handle (letters/digits/._-, max 40), got {query!r}")
    return handle


def clean_email(query: str, slug: str) -> str:
    email = (query or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise EnrichmentError(f"{slug}: pass an email address, got {query!r}")
    return email


def lead(title: str, summary: str, url: str | None = None, raw: dict | None = None,
         rtype: str = "url", confidence: str = "low") -> EnrichmentResult:
    """One T3 identity result."""
    return EnrichmentResult(rtype, title, summary, url=url, raw_json=raw,
                            confidence=confidence, tier="T3")


def http_url_or_none(value) -> str | None:
    """Scheme-check a provider-controlled URL before it becomes a pivot."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    parts = urllib.parse.urlsplit(value)
    return value if parts.scheme in ("http", "https") and parts.netloc else None


def fetch(url: str, *, timeout: float, headers: dict | None = None,
          data: bytes | None = None, max_bytes: int = 300_000) -> tuple[int, str]:
    """GET/POST -> (status, body). HTTP errors return their code; network errors raise."""
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(max_bytes).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(max_bytes).decode("utf-8", "replace")
        except Exception:
            body = ""
        return exc.code, body
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise EnrichmentError(f"{type(exc).__name__} reaching {urllib.parse.urlsplit(url).netloc}: {exc}") from exc


def github_headers() -> dict:
    """GitHub API headers; GITHUB_TOKEN is optional and only lifts the rate limit."""
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def reddit_arctic_module():
    """Import the shared scripts/lib/reddit_arctic.py (sibling of enrich/)."""
    try:
        import reddit_arctic  # noqa: PLC0415
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import reddit_arctic  # noqa: PLC0415
    return reddit_arctic


class BinAdapter(Adapter):
    """Base for subprocess wrappers (GPL/AGPL tools stay behind this boundary)."""

    category = "identity"
    tier = "T3"
    install_name: str = ""

    def check_ready(self) -> None:
        gaps = [b for b in self.requires_bin if not shutil.which(b)]
        if gaps:
            hint = SETUP_HINT.format(name=self.install_name or self.slug)
            raise NotConfiguredError(f"{self.slug}: {', '.join(gaps)} not installed ({hint})")

    def exec_tool(self, cmd: list[str], *, timeout: int, cwd: str | None = None,
                  env: dict | None = None) -> subprocess.CompletedProcess:
        """Run the tool with stdin closed so an interactive prompt fails instead of hanging."""
        self.check_ready()
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                                  stdin=subprocess.DEVNULL, cwd=cwd,
                                  env={**os.environ, **(env or {})})
        except FileNotFoundError as exc:
            hint = SETUP_HINT.format(name=self.install_name or self.slug)
            raise NotConfiguredError(f"{self.slug}: {cmd[0]} not installed ({hint})") from exc
        except subprocess.TimeoutExpired as exc:
            raise EnrichmentError(f"{self.slug}: {cmd[0]} timed out after {timeout}s") from exc

    def fail(self, proc: subprocess.CompletedProcess, what: str) -> EnrichmentError:
        tail = (proc.stderr or proc.stdout or "").strip()[-400:]
        return EnrichmentError(f"{self.slug}: {what} (exit {proc.returncode}): {tail}")
