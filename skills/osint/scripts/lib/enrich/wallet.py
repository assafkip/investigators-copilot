"""Crypto wallet: balance + transaction counterparties. On-chain record, T1.

Ported from assafkip/kipi investigations/enrich/wallet.py.
  - BTC (bc1.. / 1.. / 3..) -> mempool.space (keyless)
  - ETH (0x + 40 hex)       -> Etherscan API v2 (needs $ETHERSCAN_API_KEY; free tier)
  - mode erc20              -> Etherscan token transfers (USDT/USDC flow)
Changes on port: ETH without a key raises NotConfiguredError instead of returning a
"[needs key]" row; Etherscan moved from the retired v1 endpoint to v2 (chainid=1).
Counterparties above $OSINT_MATERIALIZE_THRESHOLD stay in raw_json only.
"""
from __future__ import annotations

import os
import re
import urllib.parse

from . import _common as c
from .base import Adapter, EnrichmentError, NotConfiguredError

_BTC_BECH32 = re.compile(r"^bc1[ac-hj-np-z02-9]{6,87}$", re.IGNORECASE)
_BTC_BASE58 = re.compile(r"^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$")
_MEMPOOL = "https://mempool.space/api"
_ETHERSCAN = "https://api.etherscan.io/v2/api"


def detect_chain(addr: str) -> str | None:
    a = addr.strip()
    if c.ETH_RE.match(a):
        return "eth"
    if _BTC_BASE58.match(a) or _BTC_BECH32.match(a):
        return "btc"
    return None


def _counterparty_rows(adapter, addrs, chain, src, warning, label=""):
    if warning:
        return []
    return [c.res(adapter, "record", a, f"{label or chain.upper()} counterparty of {src}.",
                  confidence="medium") for a in addrs]


class WalletAdapter(c.OptionalKeyMixin, Adapter):
    slug = "wallet"
    display_name = "Crypto wallet (BTC keyless via mempool.space; ETH via Etherscan)"
    env_var = "ETHERSCAN_API_KEY"
    signup_url = "https://etherscan.io/apis"
    category = "crypto"
    tier = "T1"
    watched_types = ("wallet",)

    def modes(self):
        return ["auto", "btc", "eth", "erc20"]

    def run(self, query, mode=None, timeout=40):
        addr = (query or "").strip()
        if not addr:
            raise EnrichmentError("wallet: empty address")
        m = (mode or "auto").lower()
        chain = m if m in ("btc", "eth", "erc20") else detect_chain(addr)
        if chain == "btc":
            return self._btc(addr.lower() if addr.lower().startswith("bc1") else addr, timeout)
        if chain in ("eth", "erc20"):
            return self._eth(addr, chain == "erc20", timeout)
        raise EnrichmentError(f"wallet: {addr!r} is not a recognized BTC or ETH address "
                              "(Tron: use `tron`, Solana: `solana`)")

    def _btc(self, addr, timeout):
        q = urllib.parse.quote(addr)
        info = c.get_json(f"{_MEMPOOL}/address/{q}", timeout=timeout)
        if not isinstance(info, dict) or "chain_stats" not in info:
            raise EnrichmentError("mempool.space: unexpected response (not an address object)")
        txs = c.get_json(f"{_MEMPOOL}/address/{q}/txs", timeout=timeout)
        cps = []
        for tx in txs if isinstance(txs, list) else []:
            sides = [(v.get("prevout") or {}) for v in tx.get("vin") or []] + list(tx.get("vout") or [])
            for side in sides:
                a = (side.get("scriptpubkey_address") or "").strip()
                if a and a != addr and a not in cps:
                    cps.append(a)
        cs = info["chain_stats"]
        funded, spent = cs.get("funded_txo_sum", 0), cs.get("spent_txo_sum", 0)
        warning = c.volume_warning(len(cps), "counterparties")
        header = c.res(self, "record", f"BTC {addr}: {(funded - spent) / 1e8:.8f} BTC, {cs.get('tx_count', 0)} txs",
                       f"received {funded / 1e8:.8f} BTC; sent {spent / 1e8:.8f} BTC; "
                       f"counterparties in recent txs: {len(cps)}" + (f"\n{warning}" if warning else ""),
                       url=f"https://mempool.space/address/{addr}",
                       raw_json={"address": addr, "chain": "btc", "chain_stats": cs, "counterparties": cps},
                       confidence="high")
        return [header] + _counterparty_rows(self, cps, "btc", addr, warning)

    def _etherscan(self, params, timeout):
        key = os.environ.get(self.env_var, "").strip()
        if not key:
            raise NotConfiguredError(f"wallet ETH needs ${self.env_var} ({self.signup_url}); BTC is keyless")
        body = c.get_json(f"{_ETHERSCAN}?{c.qs({'chainid': 1, **params, 'apikey': key})}", timeout=timeout)
        body = body if isinstance(body, dict) else {}
        message = str(body.get("message", ""))
        if str(body.get("status")) == "0" and "no transactions" not in message.lower():
            raise EnrichmentError(f"Etherscan: {message}: {body.get('result')}")
        result = body.get("result")
        return result

    def _eth(self, addr, tokens, timeout):
        base_q = {"module": "account", "address": addr}
        bal = self._etherscan({**base_q, "action": "balance", "tag": "latest"}, timeout)
        action = "tokentx" if tokens else "txlist"
        txs = self._etherscan({**base_q, "action": action, "page": 1, "offset": 100, "sort": "desc"}, timeout) or []
        cps, symbols = [], set()
        for tx in txs:
            symbols.add(tx.get("tokenSymbol") or "ETH")
            for side in ("from", "to"):
                a = (tx.get(side) or "").strip()
                if a and a.lower() != addr.lower() and a.lower() not in {x.lower() for x in cps}:
                    cps.append(a)
        warning = c.volume_warning(len(cps), "counterparties")
        what = "ERC-20 transfers" if tokens else "txs"
        header = c.res(self, "record", f"ETH {addr}: {int(bal or 0) / 1e18:.6f} ETH, {len(txs)} recent {what}",
                       f"tokens: {', '.join(sorted(symbols)) or 'none'}; counterparties: {len(cps)}"
                       + (f"\n{warning}" if warning else ""),
                       url=f"https://etherscan.io/address/{addr}",
                       raw_json={"address": addr, "chain": "eth", "mode": action, "balance_wei": bal,
                                 "tokens": sorted(symbols), "counterparties": cps}, confidence="high")
        return [header] + _counterparty_rows(self, cps, "eth", addr, warning, "ERC-20" if tokens else "")
