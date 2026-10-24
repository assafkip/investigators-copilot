"""OFAC sanctions: Chainalysis on-chain oracle for EVM wallets + SDN list name match. Keyless, T1.

Ported from assafkip/kipi investigations/enrich/ofac.py. Changes on port: the SDN
cache lives in $OSINT_CACHE_DIR (default ~/.cache/investigators-copilot-osint), not in the repo,
and keeps type + program per entry. A substring name match is a CANDIDATE: verify
the full SDN entry (DOB, addresses, IDs) before attribution.
Override the Ethereum RPC with $OSINT_ETH_RPC_URL (still keyless).
"""
from __future__ import annotations

import csv
import io
import json
import os
import time
from pathlib import Path

from . import _common as c
from . import base
from .base import Adapter, EnrichmentError

_ORACLE = "0x40C57923924B5c5c5455c48D93317139ADDaC8fb"
_SELECTOR = "0xdf592f7d"  # isSanctioned(address)
_DEFAULT_RPC = "https://ethereum-rpc.publicnode.com"
_SDN_CSV = "https://www.treasury.gov/ofac/downloads/sdn.csv"
_TTL = 24 * 3600


def _cache_path() -> Path:
    root = os.environ.get("OSINT_CACHE_DIR") or Path.home() / ".cache" / "investigators-copilot-osint"
    return Path(root) / "ofac_sdn.json"


def eth_sanctioned(address: str, timeout: int) -> bool:
    rpc = os.environ.get("OSINT_ETH_RPC_URL", "").strip() or _DEFAULT_RPC
    payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
               "params": [{"to": _ORACLE, "data": _SELECTOR + address[2:].lower().rjust(64, "0")}, "latest"]}
    body = base.http_json(rpc, data=payload, timeout=timeout)
    if not isinstance(body, dict) or "error" in body or "result" not in body:
        raise EnrichmentError(f"OFAC oracle RPC error: {(body or {}).get('error', 'no result')}")
    return int(body["result"] or "0x0", 16) != 0


def load_sdn(timeout: int) -> list[list[str]]:
    """[[name, type, program], ...] from the cached (24h) or freshly fetched SDN.CSV."""
    path = _cache_path()
    if path.exists() and time.time() - path.stat().st_mtime < _TTL:
        return json.loads(path.read_text())
    raw = base.http_get(_SDN_CSV, timeout=timeout).decode("latin-1")
    rows = [[r[1].strip(), r[2].strip(), r[3].strip()] for r in csv.reader(io.StringIO(raw))
            if len(r) > 3 and r[1] and r[1] != "-0-"]
    if len(rows) < 1000:
        raise EnrichmentError(f"OFAC SDN list looks truncated ({len(rows)} rows)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows))
    return rows


class OfacAdapter(Adapter):
    slug = "ofac"
    display_name = "OFAC SDN list + Chainalysis sanctions oracle"
    category = "sanctions"
    tier = "T1"
    watched_types = ("wallet", "person", "org")

    def run(self, query, mode=None, timeout=60):
        q = (query or "").strip()
        if not q:
            raise EnrichmentError("ofac: empty query")
        if c.ETH_RE.match(q):
            hit = eth_sanctioned(q, timeout)
            return [c.res(self, "record", f"OFAC oracle: {q} -- {'SANCTIONED' if hit else 'not sanctioned'}",
                          "Chainalysis sanctions oracle (on-chain contract read).",
                          url=f"https://etherscan.io/address/{q}",
                          raw_json={"address": q, "sanctioned": hit, "oracle": _ORACLE}, confidence="high")]
        # A name substring hit is a name match, which the tier rule counts as 0
        # crosslinks: T3 lead, never T1 (post-merge review, ASK-2613).
        needle = q.lower()
        matches = [r for r in load_sdn(timeout) if needle in r[0].lower()]
        return [c.res(self, "record", name, f"SDN entry ({etype or 'entity'}), program {program}. "
                      "Substring match: verify the full entry before attribution.",
                      url="https://sanctionssearch.ofac.treas.gov/",
                      raw_json={"name": name, "type": etype, "program": program, "query": q},
                      confidence="medium", tier="T3") for name, etype, program in matches[:50]]
