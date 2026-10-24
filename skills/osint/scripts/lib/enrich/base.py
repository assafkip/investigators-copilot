"""Adapter contract for Investigators Copilot enrichment providers.

Every adapter subclasses `Adapter`, sets class attributes, and implements
`run(query, mode)` returning a list of `EnrichmentResult`.

Evidence tier (`tier`) follows .claude/rules/q-investigation.md:
  T1 -- non-fakeable record (registry, WHOIS/RDAP, DNS, CT log, court record,
        on-chain transaction, government record)
  T3 -- automated tool output (scrapes, reputation feeds, username hits, search)
Adapters never emit T2: T2 is a human crosslink decision, not a tool output.

Keys: environment variables only (kipi's SQLite key store was dropped on port).
A missing key raises NotConfiguredError with the variable name and signup URL.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field

USER_AGENT = os.environ.get("OSINT_UA", "investigators-copilot-osint/1.0 (investigation tooling)")


class EnrichmentError(RuntimeError):
    """A provider call failed. Never swallowed into an empty result."""


class NotConfiguredError(EnrichmentError):
    """The adapter needs a key or a local tool that is not present."""


class HTTPStatusError(EnrichmentError):
    """An HTTP error status from a provider. `.status` lets an adapter treat a
    documented status (e.g. 404 = "not indexed") as an answer, not a failure."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


@dataclass
class EnrichmentResult:
    """One normalized result item."""
    result_type: str              # 'record' | 'url' | 'profile' | 'ioc' | 'answer' | 'document'
    title: str
    summary: str
    url: str | None = None
    raw_json: dict | None = None
    confidence: str = "medium"    # 'high' | 'medium' | 'low'
    tier: str = "T3"              # 'T1' | 'T3' (see module docstring)
    source: str = ""              # adapter slug, filled by the runner

    def to_dict(self) -> dict:
        return asdict(self)


class Adapter:
    """Base adapter. Subclasses set the class attributes and implement run()."""

    slug: str = ""
    display_name: str = ""
    env_var: str | None = None          # required key, if any
    signup_url: str = ""                # where to get the key
    requires_bin: tuple = ()            # external CLIs needed (subprocess wrappers)
    category: str = "search"            # infra | records | sanctions | crypto | identity | reputation | image | reddit | search
    tier: str = "T3"                    # default tier for this adapter's results
    keyless: bool = True
    license_note: str = ""              # e.g. "GPL-3.0: subprocess only"
    watched_types: tuple = ()           # domain | ip | email | phone | handle | person | org | wallet | url | file | text

    # -- configuration ------------------------------------------------------
    def missing(self) -> list[str]:
        """What is missing to run this adapter (empty list = ready)."""
        import shutil
        gaps = []
        if self.env_var and not os.environ.get(self.env_var, "").strip():
            gaps.append(f"${self.env_var}")
        gaps += [f"bin:{b}" for b in self.requires_bin if not shutil.which(b)]
        return gaps

    def is_configured(self) -> bool:
        return not self.missing()

    def get_key(self) -> str:
        key = os.environ.get(self.env_var or "", "").strip()
        if self.env_var and not key:
            hint = f" ({self.signup_url})" if self.signup_url else ""
            raise NotConfiguredError(f"{self.display_name}: set ${self.env_var}{hint}")
        return key

    # -- contract -------------------------------------------------------------
    def run(self, query: str, mode: str | None = None, timeout: int = 60) -> list[EnrichmentResult]:
        raise NotImplementedError(f"{self.slug}: run() not implemented")

    def modes(self) -> list[str]:
        return ["default"]

    def describe(self) -> dict:
        return {"slug": self.slug, "name": self.display_name, "category": self.category,
                "tier": self.tier, "env_var": self.env_var, "requires_bin": list(self.requires_bin),
                "modes": self.modes(), "watched_types": list(self.watched_types),
                "missing": self.missing(), "license_note": self.license_note}


# -- small shared HTTP helpers (stdlib only) ----------------------------------

def http_get(url: str, *, headers: dict | None = None, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise HTTPStatusError(f"HTTP {exc.code} from {urllib.parse.urlsplit(url).netloc}", exc.code) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise EnrichmentError(f"{type(exc).__name__} reaching {urllib.parse.urlsplit(url).netloc}: {exc}") from exc


def http_json(url: str, *, headers: dict | None = None, timeout: int = 30, data: dict | None = None):
    if data is None:
        body = http_get(url, headers={"Accept": "application/json", **(headers or {})}, timeout=timeout)
    else:
        req = urllib.request.Request(url, data=json.dumps(data).encode(), method="POST",
                                     headers={"User-Agent": USER_AGENT, "Content-Type": "application/json",
                                              "Accept": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            raise HTTPStatusError(f"HTTP {exc.code} from {urllib.parse.urlsplit(url).netloc}", exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise EnrichmentError(f"{type(exc).__name__}: {exc}") from exc
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise EnrichmentError(f"non-JSON body from {urllib.parse.urlsplit(url).netloc}") from exc


def run_bin(cmd: list[str], *, timeout: int = 300) -> str:
    """Run an external tool (used for GPL tools: subprocess boundary only)."""
    import subprocess
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise NotConfiguredError(f"{cmd[0]} not installed (run setup-tools.sh --only {cmd[0]})") from exc
    except subprocess.TimeoutExpired as exc:
        raise EnrichmentError(f"{cmd[0]} timed out after {timeout}s") from exc
    if proc.returncode != 0 and not proc.stdout.strip():
        raise EnrichmentError(f"{cmd[0]} exit {proc.returncode}: {proc.stderr.strip()[:400]}")
    return proc.stdout
