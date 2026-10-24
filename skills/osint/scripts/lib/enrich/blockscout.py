"""Blockscout: ETH address balance, contract flag, ENS, public tags. Keyless.

Ported from hydra src/osint/blockscout.ts. Balance / contract flag are on-chain (T1).
Blockscout's own labels (name, public tags, is_scam) are ASSERTED by Blockscout, not
on-chain; they ride in the summary marked as such. Override with $OSINT_BLOCKSCOUT_URL
(other EVM chains run Blockscout too).
"""
from __future__ import annotations

import os
import urllib.parse

from . import _common as c
from .base import Adapter, EnrichmentError

_DEFAULT = "https://eth.blockscout.com/api/v2/addresses/"


class BlockscoutAdapter(Adapter):
    slug = "blockscout"
    display_name = "Blockscout (ETH address)"
    category = "crypto"
    tier = "T1"
    watched_types = ("wallet",)

    def run(self, query, mode=None, timeout=30):
        addr = (query or "").strip()
        if not c.ETH_RE.match(addr):
            raise EnrichmentError(f"blockscout: {query!r} is not a 0x address")
        base_url = os.environ.get("OSINT_BLOCKSCOUT_URL", "").strip() or _DEFAULT
        body = c.get_json(base_url + urllib.parse.quote(addr), timeout=timeout, empty_on=(404,))
        if body is None:
            return []
        if not isinstance(body, dict) or str(body.get("hash", "")).lower() != addr.lower():
            raise EnrichmentError("blockscout: unexpected response or hash mismatch")
        wei = int(body.get("coin_balance") or 0)
        tags = [t.get("display_name") for t in body.get("public_tags") or [] if isinstance(t, dict)]
        asserted = ", ".join(x for x in (body.get("name") and f"name {body['name']}",
                                         body.get("ens_domain_name") and f"ENS {body['ens_domain_name']}",
                                         tags and f"tags {', '.join(tags)}",
                                         body.get("is_scam") and "flagged is_scam") if x)
        return [c.res(self, "record", f"ETH {addr}: {wei / 1e18:.6f} ETH",
                      f"{'contract' if body.get('is_contract') else 'EOA'}"
                      + (f"\nBlockscout-asserted (not on-chain): {asserted}" if asserted else ""),
                      url=f"https://eth.blockscout.com/address/{addr}", raw_json=body, confidence="high")]
