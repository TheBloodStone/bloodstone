"""Build and complete atomic name trades (Bloodstone / SpaceXpanse model)."""

from __future__ import annotations

import io
import os
import sys
from decimal import Decimal

CORE_TEST_DIR = os.environ.get(
    "BLOODSTONE_TEST_DIR", "/root/bloodstone-core/test/functional"
)
if CORE_TEST_DIR not in sys.path:
    sys.path.insert(0, CORE_TEST_DIR)

from test_framework.messages import COIN, COutPoint, CTransaction, CTxIn, CTxOut  # noqa: E402
from test_framework.script import CScript, OP_2DROP, OP_DROP, OP_NAME_UPDATE  # noqa: E402
from test_framework.util import hex_str_to_bytes  # noqa: E402

import dex_rpc

sys.path.insert(0, os.environ.get("WALLET_WEB_DIR", "/root/bloodstone-wallet-web"))
import wallet_rpc  # noqa: E402

FEE = Decimal(os.environ.get("DEX_TX_FEE", "0.01"))


def _coin(amount):
    return int(Decimal(str(amount)) * COIN)


def _build_tx_out(wallet, address, amount):
    ensure_wallet(wallet)
    addr_data = wallet_rpc.rpc("validateaddress", [address], wallet=wallet)
    script = hex_str_to_bytes(addr_data["scriptPubKey"])
    return CTxOut(_coin(amount), script)


def _build_name_update(wallet, name, value, address, amount):
    addr_data = wallet_rpc.rpc("validateaddress", [address], wallet=wallet)
    addr_script = hex_str_to_bytes(addr_data["scriptPubKey"])
    name_script = CScript(
        [OP_NAME_UPDATE, name.encode("utf-8"), value.encode("utf-8"), OP_2DROP, OP_DROP]
    )
    return CTxOut(_coin(amount), bytes(name_script) + addr_script)


def _parse_hex_tx(tx_hex):
    tx = CTransaction()
    tx.deserialize(io.BytesIO(hex_str_to_bytes(tx_hex)))
    return tx


def _find_output(wallet, amount):
    ensure_wallet(wallet)
    for entry in wallet_rpc.rpc("listunspent", [], wallet=wallet):
        if Decimal(str(entry["amount"])) >= Decimal(str(amount)):
            return COutPoint(int(entry["txid"], 16), entry["vout"]), Decimal(
                str(entry["amount"])
            )
    raise RuntimeError(f"No UTXO with at least {amount} STONE")


def ensure_wallet(wallet):
    dex_rpc.ensure_wallet(wallet)


def verify_name_owned(wallet, name):
    data = dex_rpc.name_show(name, wallet)
    if not data.get("ismine"):
        raise RuntimeError(f"Wallet does not own name {name}")
    return data


def name_utxo_fresh(name_txid, name_vout):
    out = dex_rpc.gettxout(name_txid, name_vout)
    if out is None:
        raise RuntimeError("Name UTXO is spent or unavailable — listing is stale")
    return out


def build_name_sale(seller_wallet, name, buyer_wallet, buyer_address, price):
    """Atomic transfer of a name from seller to buyer for STONE."""
    seller_wallet = str(seller_wallet)
    buyer_wallet = str(buyer_wallet)
    price = Decimal(str(price))

    name_data = verify_name_owned(seller_wallet, name)
    name_txo = dex_rpc.gettxout(name_data["txid"], name_data["vout"])
    if name_txo is None:
        raise RuntimeError("Name output is no longer available")

    seller_addr = wallet_rpc.rpc("getnewaddress", ["dex-sale"], wallet=seller_wallet)
    name_amount = Decimal(str(name_txo["value"]))
    name_value = name_data.get("value", "{}")

    inp_coin, in_value = _find_output(buyer_wallet, price + FEE)
    change = in_value - price - FEE
    if change <= 0:
        raise RuntimeError("Buyer UTXO too small after fee")

    change_addr = wallet_rpc.rpc("getrawchangeaddress", [], wallet=buyer_wallet)

    tx = CTransaction()
    tx.vin.append(CTxIn(inp_coin))
    tx.vin.append(
        CTxIn(COutPoint(int(name_data["txid"], 16), name_data["vout"]))
    )
    tx.vout.append(_build_tx_out(seller_wallet, seller_addr, price))
    tx.vout.append(_build_tx_out(buyer_wallet, change_addr, change))
    tx.vout.append(
        _build_name_update(
            seller_wallet, name, name_value, buyer_address, name_amount
        )
    )

    raw = tx.serialize().hex()
    signed = wallet_rpc.rpc("signrawtransactionwithwallet", [raw], wallet=seller_wallet)
    if signed.get("complete"):
        raise RuntimeError("Unexpected fully signed seller transaction")

    signed = wallet_rpc.rpc(
        "signrawtransactionwithwallet", [signed["hex"]], wallet=buyer_wallet
    )
    if not signed.get("complete"):
        raise RuntimeError("Could not complete name sale signatures")
    return signed["hex"]


def build_ask(seller_wallet, name, value, price):
    """Partially signed ANU ask (SINGLE|ANYONECANPAY)."""
    seller_wallet = str(seller_wallet)
    price = Decimal(str(price))

    name_data = verify_name_owned(seller_wallet, name)
    name_txo = dex_rpc.gettxout(name_data["txid"], name_data["vout"])
    if name_txo is None:
        raise RuntimeError("Name output is no longer available")

    name_value = Decimal(str(name_txo["value"]))
    name_addr = wallet_rpc.rpc("getnewaddress", ["dex-ask"], wallet=seller_wallet)

    tx = CTransaction()
    tx.vin.append(
        CTxIn(COutPoint(int(name_data["txid"], 16), name_data["vout"]))
    )
    tx.vout.append(
        _build_name_update(
            seller_wallet, name, value, name_addr, name_value + price
        )
    )

    raw = tx.serialize().hex()
    signed = wallet_rpc.rpc(
        "signrawtransactionwithwallet",
        [raw, [], "SINGLE|ANYONECANPAY"],
        wallet=seller_wallet,
    )
    if not signed.get("complete"):
        raise RuntimeError("Ask transaction signing failed")
    return {
        "hex": signed["hex"],
        "name_txid": name_data["txid"],
        "name_vout": int(name_data["vout"]),
    }


def complete_ask(buyer_wallet, partial_hex, price):
    """Buyer funds and signs an ask listing."""
    buyer_wallet = str(buyer_wallet)
    price = Decimal(str(price))

    tx = _parse_hex_tx(partial_hex)
    inp, in_value = _find_output(buyer_wallet, price + FEE)
    tx.vin.append(CTxIn(inp))

    change = in_value - price - FEE
    if change <= 0:
        raise RuntimeError("Insufficient STONE to cover price and fee")

    change_addr = wallet_rpc.rpc("getrawchangeaddress", [], wallet=buyer_wallet)
    tx.vout.append(_build_tx_out(buyer_wallet, change_addr, change))

    raw = tx.serialize().hex()
    signed = wallet_rpc.rpc("signrawtransactionwithwallet", [raw], wallet=buyer_wallet)
    if not signed.get("complete"):
        raise RuntimeError("Could not complete ask transaction")
    return signed["hex"]


def build_bid(buyer_wallet, name, value, price):
    """Partially signed ANU bid (buyer funds, seller signs name input)."""
    buyer_wallet = str(buyer_wallet)
    price = Decimal(str(price))

    name_data = dex_rpc.name_show(name, buyer_wallet)
    addr = name_data["address"]
    name_txo = dex_rpc.gettxout(name_data["txid"], name_data["vout"])
    if name_txo is None:
        raise RuntimeError("Name output is no longer available")

    name_value = Decimal(str(name_txo["value"]))

    tx = CTransaction()
    tx.vin.append(
        CTxIn(COutPoint(int(name_data["txid"], 16), name_data["vout"]))
    )
    tx.vout.append(_build_name_update(buyer_wallet, name, value, addr, name_value))
    tx.vout.append(_build_tx_out(buyer_wallet, addr, price))

    inp, in_value = _find_output(buyer_wallet, price + FEE)
    tx.vin.append(CTxIn(inp))

    change = in_value - price - FEE
    if change <= 0:
        raise RuntimeError("Insufficient STONE for bid and fee")

    change_addr = wallet_rpc.rpc("getrawchangeaddress", [], wallet=buyer_wallet)
    tx.vout.append(_build_tx_out(buyer_wallet, change_addr, change))

    raw = tx.serialize().hex()
    signed = wallet_rpc.rpc("signrawtransactionwithwallet", [raw], wallet=buyer_wallet)
    if signed.get("complete"):
        raise RuntimeError("Bid should be partially signed only")
    return {
        "hex": signed["hex"],
        "name_txid": name_data["txid"],
        "name_vout": int(name_data["vout"]),
    }


def accept_bid(seller_wallet, partial_hex, name):
    """Seller signs the name input on a bid and returns complete tx hex."""
    seller_wallet = str(seller_wallet)
    verify_name_owned(seller_wallet, name)

    signed = wallet_rpc.rpc(
        "signrawtransactionwithwallet", [partial_hex], wallet=seller_wallet
    )
    if not signed.get("complete"):
        raise RuntimeError("Bid acceptance signing failed")
    return signed["hex"]


def broadcast(tx_hex, wallet=None):
    return dex_rpc.sendrawtransaction(tx_hex, wallet=wallet)