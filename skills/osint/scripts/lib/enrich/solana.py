"""Solana wallet: recent signatures + counterparty accounts via public JSON-RPC. Keyless, T1.

Ported from assafkip/kipi investigations/enrich/solana.py. The public RPC is heavily
throttled, so only a few transactions are sampled. Override with $OSINT_SOLANA_RPC_URL.
"""
from __future__ import annotations

import os
import re

from . import _common as c
from . import base
from .base import Adapter, EnrichmentError

_SOL_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_RPC = "https://api.mainnet-beta.solana.com"
_MAX_TXS = 8


def rpc(method: str, params: list, timeout: int):
    url = os.environ.get("OSINT_SOLANA_RPC_URL", "").strip() or _RPC
    body = base.http_json(url, data={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                          timeout=timeout)
    if not isinstance(body, dict) or "error" in body:
        raise EnrichmentError(f"Solana RPC error: {(body or {}).get('error')}")
    return body.get("result")


class SolanaAdapter(Adapter):
    slug = "solana"
    display_name = "Solana wallet (signatures + counterparties)"
    category = "crypto"
    tier = "T1"
    watched_types = ("wallet",)

    def run(self, query, mode=None, timeout=40):
        addr = (query or "").strip()
        if c.ETH_RE.match(addr) or (addr.startswith("T") and len(addr) == 34) or not _SOL_RE.match(addr):
            raise EnrichmentError(f"solana: {query!r} is not a Solana base58 address")
        sigs = rpc("getSignaturesForAddress", [addr, {"limit": 25}], timeout) or []
        sig_list = [s["signature"] for s in sigs if s.get("signature")]
        cps = []
        for sig in sig_list[:_MAX_TXS]:
            tx = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}], timeout)
            for acct in (((tx or {}).get("transaction") or {}).get("message") or {}).get("accountKeys") or []:
                a = acct if isinstance(acct, str) else (acct or {}).get("pubkey", "")
                if a and a != addr and a not in cps and _SOL_RE.match(a):
                    cps.append(a)
        warning = c.volume_warning(len(cps), "Solana counterparties")
        header = c.res(self, "record", f"Solana {addr}: {len(sig_list)} recent txs",
                       f"sampled {min(len(sig_list), _MAX_TXS)} txs; accounts touched: {len(cps)} "
                       "(includes program accounts)" + (f"\n{warning}" if warning else ""),
                       url=f"https://solscan.io/account/{addr}",
                       raw_json={"address": addr, "chain": "solana", "signatures": sig_list,
                                 "counterparties": cps}, confidence="high")
        if warning:
            return [header]
        return [header] + [c.res(self, "record", a, f"Account in a shared transaction with {addr}.",
                                 confidence="medium") for a in cps]
