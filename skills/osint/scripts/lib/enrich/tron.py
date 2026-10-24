"""Tron wallet: TRC-20 transfers (USDT rail) + counterparties via TronGrid. Keyless, T1.

Ported from assafkip/kipi investigations/enrich/tron.py. $TRONGRID_API_KEY is sent
when set (raises the public rate limit).
"""
from __future__ import annotations

import os
import re
import urllib.parse

from . import _common as c
from .base import Adapter, EnrichmentError

_TRON_RE = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")
_TRONGRID = "https://api.trongrid.io"


class TronAdapter(c.OptionalKeyMixin, Adapter):
    slug = "tron"
    display_name = "Tron wallet (TRC-20 transfers)"
    env_var = "TRONGRID_API_KEY"
    signup_url = "https://www.trongrid.io/register"
    category = "crypto"
    tier = "T1"
    watched_types = ("wallet",)

    def run(self, query, mode=None, timeout=40):
        addr = (query or "").strip()
        if not _TRON_RE.match(addr):
            raise EnrichmentError(f"tron: {query!r} is not a Tron T-address")
        key = os.environ.get(self.env_var, "").strip()
        body = c.get_json(f"{_TRONGRID}/v1/accounts/{urllib.parse.quote(addr)}/transactions/trc20?limit=50",
                          timeout=timeout, headers={"TRON-PRO-API-KEY": key} if key else None)
        if not isinstance(body, dict) or body.get("success") is False:
            raise EnrichmentError(f"TronGrid: {(body or {}).get('error') or 'request failed'}")
        rows = body.get("data") or []
        cps: dict[str, str] = {}
        for tx in rows:
            sym = ((tx.get("token_info") or {}).get("symbol") or "?")
            for side in ("from", "to"):
                a = (tx.get(side) or "").strip()
                if a and a != addr and _TRON_RE.match(a):
                    cps.setdefault(a, sym)
        warning = c.volume_warning(len(cps), "TRC-20 counterparties")
        symbols = sorted({(t.get("token_info") or {}).get("symbol") or "?" for t in rows})
        header = c.res(self, "record", f"Tron {addr}: {len(rows)} TRC-20 transfers",
                       f"tokens: {', '.join(symbols) or 'none'}; counterparties: {len(cps)}"
                       + (f"\n{warning}" if warning else ""),
                       url=f"https://tronscan.org/#/address/{addr}",
                       raw_json={"address": addr, "chain": "tron", "tokens": symbols,
                                 "counterparties": list(cps)}, confidence="high")
        if warning:
            return [header]
        return [header] + [c.res(self, "record", a, f"{sym} counterparty of {addr} (TRC-20).",
                                 confidence="medium") for a, sym in cps.items()]
