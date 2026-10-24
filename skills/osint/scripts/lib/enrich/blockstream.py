"""Blockstream Esplora: BTC address stats (second source next to `wallet`). Keyless, T1.

Ported from hydra src/osint/blockstream.ts. Independent infrastructure from
mempool.space, so it cross-checks the `wallet` BTC figures.
"""
from __future__ import annotations

import urllib.parse

from . import _common as c
from .base import Adapter, EnrichmentError

_URL = "https://blockstream.info/api/address/"


class BlockstreamAdapter(Adapter):
    slug = "blockstream"
    display_name = "Blockstream Esplora (BTC address)"
    category = "crypto"
    tier = "T1"
    watched_types = ("wallet",)

    def run(self, query, mode=None, timeout=30):
        addr = (query or "").strip()
        if not addr:
            raise EnrichmentError("blockstream: empty address")
        body = c.get_json(_URL + urllib.parse.quote(addr), timeout=timeout)
        if not isinstance(body, dict) or "chain_stats" not in body:
            raise EnrichmentError("blockstream: unexpected response shape")
        if str(body.get("address", "")).lower() != addr.lower():
            raise EnrichmentError("blockstream: response address does not match the query")
        cs, ms = body.get("chain_stats") or {}, body.get("mempool_stats") or {}
        recv = cs.get("funded_txo_sum", 0) + ms.get("funded_txo_sum", 0)
        spent = cs.get("spent_txo_sum", 0) + ms.get("spent_txo_sum", 0)
        txs = cs.get("tx_count", 0) + ms.get("tx_count", 0)
        return [c.res(self, "record", f"BTC {addr}: {(recv - spent) / 1e8:.8f} BTC",
                      f"{txs} txs; received {recv / 1e8:.8f} BTC; spent {spent / 1e8:.8f} BTC",
                      url=f"https://blockstream.info/address/{addr}", raw_json=body, confidence="high")]
