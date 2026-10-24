"""Web technology fingerprint (CMS, frameworks, analytics, CDN) via a local CLI. T3.

New adapter. wappalyzergo (projectdiscovery) is a Go library with no CLI of its own,
so this wraps whichever is installed, in order:
  1. a `wappalyzer` CLI that prints Wappalyzer JSON ({"technologies": [...]})
  2. projectdiscovery httpx (`httpx -tech-detect -json`), which embeds wappalyzergo.
     Set $PD_HTTPX_BIN if the Python `httpx` CLI shadows it on PATH.
NotConfiguredError otherwise. ACTIVE: this fetches the target site from this machine.
"""
from __future__ import annotations

import json
import os
import subprocess

from . import _common as c
from . import base
from .base import Adapter, EnrichmentError, NotConfiguredError


def _pd_httpx() -> str | None:
    """Path to projectdiscovery httpx, or None (the Python httpx CLI is rejected)."""
    path = os.environ.get("PD_HTTPX_BIN") or c.which("httpx")
    if not path:
        return None
    try:
        proc = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    banner = (proc.stdout + proc.stderr).lower()
    return path if "projectdiscovery" in banner or "current version" in banner else None


def _url(target: str) -> str:
    t = (target or "").strip()
    return t if "://" in t else f"https://{t}"


def parse_wappalyzer(out: str) -> list[dict]:
    data = json.loads(out or "{}")
    techs = data.get("technologies") if isinstance(data, dict) else None
    return [{"name": t.get("name"), "version": t.get("version") or "",
             "categories": [x.get("name") for x in t.get("categories") or []]} for t in techs or []]


def parse_httpx(out: str) -> tuple[list[dict], dict]:
    for line in (out or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            row = json.loads(line)
            techs = [{"name": t.split(":")[0], "version": t.split(":", 1)[1] if ":" in t else "",
                      "categories": []} for t in row.get("tech") or []]
            return techs, row
    return [], {}


class WappalyzerAdapter(Adapter):
    slug = "wappalyzer"
    display_name = "Tech fingerprint (wappalyzer CLI or projectdiscovery httpx)"
    signup_url = "go install github.com/projectdiscovery/httpx/cmd/httpx@latest"
    category = "infra"
    tier = "T3"
    watched_types = ("domain", "url")
    license_note = "httpx/wappalyzergo: MIT; subprocess"

    def missing(self):
        return [] if c.which("wappalyzer") or _pd_httpx() else ["bin:wappalyzer or projectdiscovery httpx"]

    def run(self, query, mode=None, timeout=120):
        url = _url(query)
        try:
            if c.which("wappalyzer"):
                techs, meta = parse_wappalyzer(base.run_bin(["wappalyzer", url], timeout=timeout)), {}
            elif (httpx := _pd_httpx()):
                techs, meta = parse_httpx(base.run_bin(
                    [httpx, "-u", url, "-tech-detect", "-json", "-silent", "-title", "-web-server",
                     "-status-code", "-ip", "-cdn"], timeout=timeout))
                if not meta:
                    raise EnrichmentError(f"httpx: no response from {url}")
            else:
                raise NotConfiguredError("wappalyzer: install projectdiscovery httpx "
                                         "(go install github.com/projectdiscovery/httpx/cmd/httpx@latest)")
        except json.JSONDecodeError as exc:
            raise EnrichmentError(f"wappalyzer: unparseable tool output ({exc})") from exc
        header = c.res(self, "document", f"tech: {url} -- {len(techs)} technologies",
                       ", ".join(f"{t['name']} {t['version']}".strip() for t in techs) or "(none detected)",
                       url=url, raw_json={"technologies": techs, **{k: meta.get(k) for k in
                                          ("title", "webserver", "status_code", "host", "a", "cdn_name") if k in meta}},
                       confidence="medium")
        return [header]
