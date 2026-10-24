"""Username presence sweep: a handle -> which platforms it exists on. Keyless, T3.

Ported from assafkip/kipi investigations/enrich/username.py, extended to the FULL
vendored WhatsMyName dataset (data/wmn-data.json, CC BY-SA 4.0, see data/NOTICE.md).

Sites:
  curated  kipi's hand-checked set (clean 404s or JSON lookups) + Reddit via the
           Arctic Shift mirror (our lib/reddit_arctic.user_history). Curated wins
           on a name clash with WhatsMyName.
  wmn      every WhatsMyName site, using its own detection contract:
           present  = status == e_code AND e_string in body
           absent   = status == m_code AND (m_string empty OR m_string in body)
           anything else = indeterminate (never guessed).

Modes: default (curated + WMN minus bot-protected sites), full (all WMN incl.
cloudflare/captcha-protected ones), curated (kipi set only).

Every hit is a T3 lead: a handle match is 0 crosslinks under
.claude/rules/q-investigation.md. Reddit is weaker still: it proves PUBLIC
ACTIVITY, not account existence (a lurker reads absent).

If every site comes back indeterminate the run raises EnrichmentError: that is a
dead network, not "the handle exists nowhere".
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ._identity_common import T3_NOTE, clean_handle, fetch, lead, reddit_arctic_module
from .base import Adapter, EnrichmentError

WMN_PATH = Path(__file__).resolve().parent / "data" / "wmn-data.json"
SITE_TIMEOUT = float(os.environ.get("OSINT_USERNAME_SITE_TIMEOUT", "8"))
MAX_WORKERS = int(os.environ.get("OSINT_USERNAME_WORKERS", "16"))

# (name, check_url, detector, public_url). detector kinds: status, contains,
# json_code, json_notnull, reddit.
CURATED = [
    ("GitHub", "https://github.com/{u}", ("status",), None),
    ("GitLab", "https://gitlab.com/{u}", ("status",), None),
    ("Reddit", "", ("reddit",), "https://www.reddit.com/user/{u}"),
    ("Keybase", "https://keybase.io/_/api/1.0/user/lookup.json?username={u}",
     ("json_code", "them"), "https://keybase.io/{u}"),
    ("HackerNews", "https://hacker-news.firebaseio.com/v0/user/{u}.json", ("json_notnull",),
     "https://news.ycombinator.com/user?id={u}"),
    ("DevTo", "https://dev.to/{u}", ("status",), None),
    ("Medium", "https://medium.com/@{u}", ("status",), None),
    ("YouTube", "https://www.youtube.com/@{u}", ("status",), None),
    ("Telegram", "https://t.me/{u}", ("contains", "tgme_page_title"), None),
    ("Gravatar", "https://gravatar.com/{u}", ("status",), None),
]


def load_wmn(path: Path = WMN_PATH, include_protected: bool = False) -> list[dict]:
    """WhatsMyName site entries usable for a GET/POST check."""
    try:
        sites = json.loads(path.read_text()).get("sites", [])
    except (OSError, json.JSONDecodeError) as exc:
        raise EnrichmentError(f"username: cannot read vendored WhatsMyName data {path}: {exc}") from exc
    usable = []
    for site in sites:
        if not site.get("name") or "{account}" not in str(site.get("uri_check", "")):
            continue
        if site.get("valid") is False or not site.get("e_string"):
            continue
        if site.get("protection") and not include_protected:
            continue
        usable.append(site)
    return usable


def _json_verdict(kind: str, status: int, body: str, key: str = ""):
    if status != 200:
        return False if status == 404 else None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if kind == "json_notnull":
        return data is not None
    return isinstance(data, dict) and data.get(key) is not None


def _curated_verdict(detector: tuple, status: int, body: str):
    kind = detector[0]
    if kind == "status":
        return True if status == 200 else (False if status == 404 else None)
    if kind == "contains":
        return status == 200 and detector[1] in body
    return _json_verdict(kind, status, body, detector[1] if len(detector) > 1 else "")


def _reddit_verdict(username: str):
    """Public activity in the Arctic Shift archive (falls back to PullPush, RSS)."""
    try:
        hist = reddit_arctic_module().user_history(username, max_items=5, timeout=int(SITE_TIMEOUT) + 4)
    except Exception:
        return None
    return bool(hist.get("posts") or hist.get("comments"))


def check_curated(entry: tuple, username: str) -> dict:
    name, check_url, detector, public = entry
    public_url = (public or check_url).format(u=username)
    if detector[0] == "reddit":
        return {"site": name, "present": _reddit_verdict(username), "url": public_url, "source": "curated"}
    try:
        status, body = fetch(check_url.format(u=username), timeout=SITE_TIMEOUT)
    except EnrichmentError:
        return {"site": name, "present": None, "url": public_url, "source": "curated"}
    return {"site": name, "present": _curated_verdict(detector, status, body),
            "url": public_url, "source": "curated"}


def wmn_verdict(site: dict, status: int, body: str):
    if status == site.get("e_code") and site.get("e_string", "") in body:
        return True
    m_string = site.get("m_string") or ""
    if status == site.get("m_code") and (not m_string or m_string in body):
        return False
    return None


def _account(site: dict, username: str) -> str:
    for char in site.get("strip_bad_char") or "":
        username = username.replace(char, "")
    return username


def check_wmn(site: dict, username: str) -> dict:
    account = _account(site, username)
    url = site["uri_check"].replace("{account}", account)
    public = (site.get("uri_pretty") or site["uri_check"]).replace("{account}", account)
    body_data = site["post_body"].replace("{account}", account).encode() if site.get("post_body") else None
    try:
        status, body = fetch(url, timeout=SITE_TIMEOUT, headers=site.get("headers"), data=body_data)
    except EnrichmentError:
        return {"site": site["name"], "present": None, "url": public, "source": "wmn"}
    return {"site": site["name"], "present": wmn_verdict(site, status, body),
            "url": public, "source": "wmn", "category": site.get("cat")}


def build_checks(mode: str) -> list[tuple]:
    """(callable, arg) pairs for the mode; curated names shadow WMN names."""
    checks = [(check_curated, entry) for entry in CURATED]
    if mode == "curated":
        return checks
    curated_names = {entry[0].lower() for entry in CURATED}
    for site in load_wmn(include_protected=(mode == "full")):
        if site["name"].lower() not in curated_names:
            checks.append((check_wmn, site))
    return checks


def run_checks(checks: list[tuple], username: str) -> list[dict]:
    workers = max(1, min(MAX_WORKERS, len(checks)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(func, arg, username) for func, arg in checks]
        return [f.result() for f in futures]


class UsernameAdapter(Adapter):
    slug = "username"
    display_name = "Username presence sweep (curated + WhatsMyName)"
    category = "identity"
    tier = "T3"
    watched_types = ("handle",)
    license_note = "WhatsMyName data CC BY-SA 4.0 (data/NOTICE.md)"

    def modes(self):
        return ["default", "full", "curated"]

    def run(self, query, mode=None, timeout=60):
        username = clean_handle(query, self.slug)
        mode = (mode or "default").lower()
        if mode not in self.modes():
            raise EnrichmentError(f"username: unknown mode {mode!r} (use {', '.join(self.modes())})")
        rows = run_checks(build_checks(mode), username)
        found = [r for r in rows if r["present"] is True]
        absent = [r for r in rows if r["present"] is False]
        indet = [r for r in rows if r["present"] is None]
        if not found and not absent:
            raise EnrichmentError(f"username: all {len(rows)} site checks indeterminate (network down or blocked)")
        return [self._header(username, mode, found, absent, indet, rows)] + [
            lead(f"{r['site']}: {username}", f"Handle '{username}' present on {r['site']} ({r['source']}). {T3_NOTE}",
                 url=r["url"], raw=r) for r in found]

    @staticmethod
    def _header(username, mode, found, absent, indet, rows):
        summary = (f"Checked {len(rows)} sites for '{username}' (mode {mode}).\n"
                   f"FOUND ({len(found)}): {', '.join(r['site'] for r in found) or 'none'}\n"
                   f"absent: {len(absent)}  indeterminate: {len(indet)}\n"
                   "Reddit = public activity only. " + T3_NOTE)
        return lead(f"Username sweep: {username} -- found on {len(found)}/{len(rows)}", summary,
                    raw={"username": username, "mode": mode, "found": [r["url"] for r in found],
                         "indeterminate": [r["site"] for r in indet]},
                    rtype="document", confidence="medium")
