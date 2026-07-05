"""RPC helpers for DEX atomic trades via user wallets."""

import os
import sys

sys.path.insert(0, os.environ.get("WALLET_WEB_DIR", "/root/bloodstone-wallet-web"))
import wallet_rpc  # noqa: E402


def ensure_wallet(wallet_name):
    wallet_rpc.ensure_wallet_loaded(wallet_name)


def name_show(name, wallet):
    ensure_wallet(wallet)
    return wallet_rpc.rpc("name_show", [name], wallet=wallet)


def name_list(wallet, pattern="*"):
    ensure_wallet(wallet)
    return wallet_rpc.rpc("name_list", [pattern], wallet=wallet)


def decoderawtransaction(tx_hex, wallet=None):
    return wallet_rpc.rpc("decoderawtransaction", [tx_hex], wallet=wallet)


def sendrawtransaction(tx_hex, wallet=None):
    return wallet_rpc.rpc("sendrawtransaction", [tx_hex], wallet=wallet)


def gettxout(txid, vout):
    return wallet_rpc.rpc("gettxout", [txid, vout])


def estimate_fee():
    return float(os.environ.get("DEX_TX_FEE", "0.01"))