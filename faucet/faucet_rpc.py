"""RPC helpers for the dedicated faucet wallet."""

import os
import sys

sys.path.insert(0, "/root/bloodstone-wallet-web")
import wallet_rpc  # noqa: E402

WALLET_NAME = os.environ.get("FAUCET_WALLET", "faucet")


def ensure_faucet_wallet():
    if not wallet_rpc.wallet_exists(WALLET_NAME):
        wallet_rpc.create_legacy_wallet(WALLET_NAME, load_on_startup=True)
    wallet_rpc.ensure_wallet_loaded(WALLET_NAME)


def faucet_address():
    ensure_faucet_wallet()
    return wallet_rpc.rpc(
        "getnewaddress", ["faucet-receive"], wallet=WALLET_NAME
    )


def primary_address():
    """Stable donation address (reuses labeled 'faucet' address)."""
    ensure_faucet_wallet()
    try:
        addrs = wallet_rpc.rpc("getaddressesbylabel", ["faucet"], wallet=WALLET_NAME)
        if addrs:
            return next(iter(addrs.keys()))
    except RuntimeError:
        pass
    return wallet_rpc.rpc("getnewaddress", ["faucet"], wallet=WALLET_NAME)


def wallet_info():
    ensure_faucet_wallet()
    info = wallet_rpc.rpc("getwalletinfo", wallet=WALLET_NAME)
    balances = wallet_rpc.rpc("getbalances", wallet=WALLET_NAME)
    spendable = balances.get("mine", {}).get("trusted", info.get("balance", 0))
    return {
        "balance": float(info.get("balance", 0)),
        "spendable": float(spendable),
        "txcount": int(info.get("txcount", 0)),
    }


def _txid_from_send_result(result):
    if isinstance(result, dict):
        txid = result.get("txid")
        if txid:
            return str(txid)
        raise RuntimeError(f"sendtoaddress returned no txid: {result!r}")
    if result is None:
        raise RuntimeError("sendtoaddress returned empty result")
    return str(result)


def send_to_address(address, amount):
    ensure_faucet_wallet()
    return wallet_rpc.send_to_address_broadcast(
        address,
        amount,
        wallet=WALLET_NAME,
        comment="faucet claim",
    )


def sync_donations():
    """Record incoming transfers to the faucet wallet."""
    ensure_faucet_wallet()
    txs = wallet_rpc.rpc(
        "listtransactions", ["*", 50, 0, True], wallet=WALLET_NAME
    )
    import faucet_db

    for tx in txs:
        if tx.get("category") != "receive" or tx.get("amount", 0) <= 0:
            continue
        faucet_db.record_donation(
            tx.get("txid", ""),
            tx.get("address", ""),
            float(tx["amount"]),
        )