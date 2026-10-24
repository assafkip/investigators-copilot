"""On-chain adapters: wallet (BTC/ETH), tron, solana, ens, blockstream, blockscout. Offline."""
import pytest
from _enrich_net import install

from enrich import registry
from enrich.base import EnrichmentError, NotConfiguredError

ETH = "0x" + "ab" * 20
BTC = "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"
TRON = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"


def run(slug, query, mode=None):
    return registry.get_adapter(slug).run(query, mode=mode)


def test_wallet_btc_counterparties(monkeypatch):
    install(monkeypatch, {
        f"/address/{BTC}/txs": [{"vin": [{"prevout": {"scriptpubkey_address": "1Src"}}],
                                 "vout": [{"scriptpubkey_address": BTC}, {"scriptpubkey_address": "3Dst"}]}],
        f"/address/{BTC}": {"chain_stats": {"funded_txo_sum": 300000000, "spent_txo_sum": 100000000,
                                            "tx_count": 2}}})
    rows = run("wallet", BTC.upper())
    assert "2.00000000 BTC" in rows[0].title and [r.title for r in rows[1:]] == ["1Src", "3Dst"]
    assert all(r.tier == "T1" for r in rows)


def test_wallet_eth_needs_key(monkeypatch):
    monkeypatch.delenv("ETHERSCAN_API_KEY", raising=False)
    with pytest.raises(NotConfiguredError):
        run("wallet", ETH)


def test_wallet_eth_error_string_raises(monkeypatch):
    monkeypatch.setenv("ETHERSCAN_API_KEY", "k")
    install(monkeypatch, {"etherscan": {"status": "0", "message": "NOTOK", "result": "Invalid API Key"}})
    with pytest.raises(EnrichmentError, match="NOTOK"):
        run("wallet", ETH)


def test_wallet_eth_no_transactions_is_empty_history(monkeypatch):
    monkeypatch.setenv("ETHERSCAN_API_KEY", "k")
    calls = install(monkeypatch, {"action=balance": {"status": "1", "message": "OK", "result": "1000000000000000000"},
                                  "action=txlist": {"status": "0", "message": "No transactions found", "result": []}})
    [row] = run("wallet", ETH)
    assert "1.000000 ETH" in row.title and "chainid=1" in calls[0][0]


def test_wallet_counterparty_volume_is_capped(monkeypatch):
    monkeypatch.setenv("ETHERSCAN_API_KEY", "k")
    txs = [{"from": ETH, "to": "0x" + f"{i:040x}"} for i in range(80)]
    install(monkeypatch, {"action=balance": {"status": "1", "result": "0"},
                          "action=txlist": {"status": "1", "result": txs}})
    rows = run("wallet", ETH)
    assert len(rows) == 1 and len(rows[0].raw_json["counterparties"]) == 80


def test_tron_counterparties(monkeypatch):
    other = "TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE"
    install(monkeypatch, {"trongrid": {"success": True, "data": [
        {"from": TRON, "to": other, "token_info": {"symbol": "USDT"}}]}})
    rows = run("tron", TRON)
    assert rows[1].title == other and "USDT" in rows[1].summary


def test_tron_rejects_non_tron():
    with pytest.raises(EnrichmentError):
        run("tron", ETH)


def test_solana_rpc_error_raises(monkeypatch):
    install(monkeypatch, {"solana.com": {"error": {"code": 429, "message": "Too many requests"}}})
    with pytest.raises(EnrichmentError, match="Solana RPC"):
        run("solana", "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM")


def test_ens_forward_and_unresolved(monkeypatch):
    install(monkeypatch, {"ensideas": {"address": ETH, "name": "vitalik.eth"}})
    [row] = run("ens", "vitalik.eth")
    assert row.raw_json["address"] == ETH and row.tier == "T3"
    install(monkeypatch, {"ensideas": {"address": None, "name": None}})
    assert run("ens", "nobody.eth") == []


def test_blockstream_address_mismatch_raises(monkeypatch):
    install(monkeypatch, {"blockstream.info": {"address": "other", "chain_stats": {}}})
    with pytest.raises(EnrichmentError, match="does not match"):
        run("blockstream", BTC)


def test_blockscout_marks_asserted_labels(monkeypatch):
    install(monkeypatch, {"blockscout": {"hash": ETH, "coin_balance": "2000000000000000000", "is_contract": False,
                                         "is_scam": True, "public_tags": [{"display_name": "Exploiter"}]}})
    [row] = run("blockscout", ETH)
    assert "2.000000 ETH" in row.title and "Blockscout-asserted" in row.summary and "Exploiter" in row.summary
