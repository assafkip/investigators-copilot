"""holehe wrapper: which sites an email is registered on. GPL-3.0, subprocess only, T3.

Runs `holehe <email> --only-used --no-color --no-clear` and parses the `[+] site`
lines. Account enumeration is a HYPOTHESIS lead, never a crosslink.
Install: pipx install holehe.
"""
from __future__ import annotations

import re

from ._identity_common import T3_NOTE, BinAdapter, clean_email, lead

USED_LINE = re.compile(r"^\[\+\]\s+(\S+)")


def parse_output(text: str) -> list[str]:
    sites = []
    for line in text.splitlines():
        line = line.strip()
        if "Email used" in line:
            continue
        match = USED_LINE.match(line)
        if match and match.group(1) not in sites:
            sites.append(match.group(1))
    return sites


class HoleheAdapter(BinAdapter):
    slug = "holehe"
    display_name = "holehe email account enumeration (subprocess)"
    requires_bin = ("holehe",)
    watched_types = ("email",)
    license_note = "GPL-3.0: subprocess only, never imported"

    def run(self, query, mode=None, timeout=300):
        email = clean_email(query, self.slug)
        proc = self.exec_tool(["holehe", email, "--only-used", "--no-color", "--no-clear"],
                              timeout=max(timeout, 120))
        if proc.returncode != 0 or "[+]" not in (proc.stdout or ""):
            raise self.fail(proc, "no holehe result block in output")
        sites = parse_output(proc.stdout)
        header = lead(f"holehe: {email} -- registered on {len(sites)} site(s)",
                      "\n".join(f"- {s}" for s in sites[:60]) + f"\n{T3_NOTE}",
                      raw={"email": email, "sites": sites}, rtype="document")
        return [header] + [lead(f"{site} ({email})", f"holehe: {email} has an account on {site}. {T3_NOTE}",
                                raw={"site": site}, rtype="record") for site in sites]
