"""Scam Sniffer public blocklists: is this wallet or domain flagged? Keyless, T3.

Ported from assafkip/kipi investigations/enrich/crypto_abuse.py. A blocklist hit is
an automated feed flag (T3 lead), never a finding by itself.
"""
from __future__ import annotations

from . import _common as c
from .base import Adapter, EnrichmentError

_FEEDS = "https://raw.githubusercontent.com/scamsniffer/scam-database/main/blacklist/"


class CryptoAbuseAdapter(Adapter):
    slug = "crypto_abuse"
    display_name = "Crypto scam blocklists (Scam Sniffer)"
    category = "crypto"
    tier = "T3"
    watched_types = ("wallet", "domain")

    def run(self, query, mode=None, timeout=60):
        q = (query or "").strip()
        if not q:
            raise EnrichmentError("crypto_abuse: empty query")
        is_wallet = "." not in q and "/" not in q
        kind = "wallet" if is_wallet else "domain"
        needle = q.lower() if is_wallet else c.bare_host(q)
        feed = c.get_json(_FEEDS + ("address.json" if is_wallet else "domains.json"), timeout=timeout)
        if not isinstance(feed, list):
            raise EnrichmentError("crypto_abuse: feed is not a JSON list (moved?)")
        hit = any(isinstance(x, str) and x.lower() == needle for x in feed)
        summary = (f"FLAGGED on the Scam Sniffer {kind} blocklist ({len(feed)} entries). T3 lead; corroborate."
                   if hit else f"Not on the Scam Sniffer {kind} blocklist ({len(feed)} entries checked).")
        return [c.res(self, "document", f"crypto_abuse: {q} [{'HIT' if hit else 'CLEAN'}]", summary,
                      url="https://github.com/scamsniffer/scam-database",
                      raw_json={"query": q, "kind": kind, "hit": hit, "feed_size": len(feed)},
                      confidence="medium" if hit else "low")]
