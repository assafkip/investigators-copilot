"""ENS name <-> address resolution. On-chain record, T1.

Ported from assafkip/kipi investigations/enrich/ens.py. Uses the keyless ENSIdeas
resolver (computing the namehash needs Keccak-256, absent from the stdlib).
Override with $OSINT_ENS_RESOLVER.
"""
from __future__ import annotations

import os
import re
import urllib.parse

from . import _common as c
from .base import Adapter, EnrichmentError

_NAME_RE = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)*\.eth$", re.IGNORECASE)
_DEFAULT = "https://api.ensideas.com/ens/resolve"


class EnsAdapter(Adapter):
    slug = "ens"
    display_name = "ENS forward/reverse resolution"
    category = "crypto"
    tier = "T3"  # third-party resolver API (api.ensideas.com), not a chain read
    watched_types = ("wallet",)  # not "handle": non-.eth handles always error in sweeps

    def run(self, query, mode=None, timeout=30):
        q = (query or "").strip()
        if not (c.ETH_RE.match(q) or _NAME_RE.match(q)):
            raise EnrichmentError(f"ens: {q!r} is neither a 0x address nor a *.eth name")
        base_url = os.environ.get("OSINT_ENS_RESOLVER", "").strip() or _DEFAULT
        data = c.get_json(f"{base_url}/{urllib.parse.quote(q)}", timeout=timeout)
        if not isinstance(data, dict):
            raise EnrichmentError("ens: unexpected resolver response")
        address = (data.get("address") or "").strip()
        name = (data.get("name") or "").strip()
        if c.ETH_RE.match(q) and not name:
            return []  # no reverse (primary) name set
        if _NAME_RE.match(q) and not c.ETH_RE.match(address):
            return []  # name does not resolve
        return [c.res(self, "record", f"{name} <-> {address}",
                      f"ENS: {name} resolves to {address} (on-chain registry).",
                      url=f"https://app.ens.domains/{name}",
                      raw_json={"name": name, "address": address, "avatar": data.get("avatar")},
                      confidence="high")]
