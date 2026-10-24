"""gitrecon wrapper (GONZOsint/gitrecon): GitHub/GitLab profile, leaked commit
emails, SSH keys. GPL-3.0, subprocess only, T3.

Runs `gitrecon -s github <user>` then `-s gitlab`, parsing the `[+] Key: value`
lines (rich strips colour when not on a TTY). gitrecon is a script, not a pip
package: setup-tools.sh --only gitrecon clones it and puts a `gitrecon` shim on
PATH.
"""
from __future__ import annotations

import re

from ._identity_common import EMAIL_RE, T3_NOTE, BinAdapter, clean_handle, lead
from .base import EnrichmentError

KV_LINE = re.compile(r"\[\+\]\s*([^:]+):\s*(.*)$")


def parse_output(text: str) -> dict:
    fields, emails, keys = {}, [], []
    for line in text.splitlines():
        match = KV_LINE.search(line.strip())
        if not match:
            continue
        key, value = match.group(1).strip().lower(), match.group(2).strip()
        if key == "leaked email" and EMAIL_RE.match(value) and value.lower() not in emails:
            emails.append(value.lower())
        elif key == "key":
            keys.append(value)
        elif value and value != "None":
            fields.setdefault(key, value)
    return {"fields": fields, "emails": emails, "ssh_keys": keys}


class GitreconAdapter(BinAdapter):
    slug = "gitrecon"
    display_name = "gitrecon GitHub/GitLab recon (subprocess)"
    requires_bin = ("gitrecon",)
    watched_types = ("handle",)
    license_note = "GPL-3.0: subprocess only, never imported"

    def run(self, query, mode=None, timeout=180):
        user = clean_handle(query, self.slug)
        sites = [mode] if mode in ("github", "gitlab") else ["github", "gitlab"]
        rows, errors = [], []
        for site in sites:
            proc = self.exec_tool(["gitrecon", "-s", site, user], timeout=timeout)
            parsed = parse_output(proc.stdout or "")
            if not parsed["fields"]:
                errors.append(f"{site}: exit {proc.returncode} {(proc.stderr or proc.stdout or '').strip()[-160:]}")
                continue
            rows += self._rows(user, site, parsed)
        if not rows:
            raise EnrichmentError(f"gitrecon: no profile parsed ({'; '.join(errors)})")
        return rows

    def modes(self):
        return ["both", "github", "gitlab"]

    @staticmethod
    def _rows(user: str, site: str, parsed: dict):
        summary = "\n".join(f"{k}: {v}" for k, v in parsed["fields"].items())
        header = lead(f"gitrecon {site}: {user} -- {len(parsed['emails'])} leaked email(s), "
                      f"{len(parsed['ssh_keys'])} SSH key(s)", f"{summary}\n{T3_NOTE}",
                      url=f"https://{site}.com/{user}", raw={"site": site, **parsed}, rtype="profile",
                      confidence="medium")
        return [header] + [lead(e, f"Commit email leaked in {user}'s {site} activity (gitrecon).",
                                rtype="record") for e in parsed["emails"]]
