"""On-chain BSM1 anchors for chain mesh asset manifests."""

import os
import sys
from typing import Any, Dict, Optional

from chain_mesh.merkle import asset_id_for_key

ANCHOR_MAGIC = b"BSM1"
DEFAULT_WALLET = os.environ.get("CHAIN_MESH_ANCHOR_WALLET", "mine")


def _wallet_rpc():
    sys.path.insert(0, "/root/bloodstone-wallet-web")
    import wallet_rpc  # noqa: E402

    return wallet_rpc


def build_anchor_payload(*, asset_key: str, merkle_root: str) -> bytes:
    """52-byte BSM1 payload: magic(4) + asset_id_prefix(16) + merkle_root(32)."""
    aid = bytes.fromhex(asset_id_for_key(asset_key))
    root = (merkle_root or "").strip().lower()
    if len(root) != 64:
        raise ValueError("merkle_root must be 64 hex chars")
    return ANCHOR_MAGIC + aid[:16] + bytes.fromhex(root)


def anchor_asset_on_chain(
    *,
    asset_key: str,
    merkle_root: str,
    wallet: Optional[str] = None,
) -> Dict[str, Any]:
    """Broadcast OP_RETURN anchor tx; returns txid and block height when confirmed."""
    wallet_rpc = _wallet_rpc()
    wname = (wallet or DEFAULT_WALLET).strip()
    wallet_rpc.ensure_wallet_loaded(wname)

    payload = build_anchor_payload(asset_key=asset_key, merkle_root=merkle_root)
    data_hex = payload.hex()

    raw = wallet_rpc.rpc(
        "createrawtransaction",
        [[], {"data": data_hex}],
        wallet=wname,
    )
    funded = wallet_rpc.rpc("fundrawtransaction", [raw], wallet=wname)
    signed = wallet_rpc.rpc(
        "signrawtransactionwithwallet",
        [funded["hex"]],
        wallet=wname,
    )
    if not signed.get("complete"):
        raise RuntimeError(f"anchor tx signing incomplete: {signed!r}")
    txid = wallet_rpc.rpc("sendrawtransaction", [signed["hex"]])
    height = 0
    confirmations = 0
    try:
        tx = wallet_rpc.rpc("gettransaction", [txid], wallet=wname)
        confirmations = int(tx.get("confirmations") or 0)
        if confirmations > 0 and tx.get("blockhash"):
            header = wallet_rpc.rpc("getblockheader", [tx["blockhash"]])
            height = int(header.get("height") or 0)
    except RuntimeError:
        pass
    return {
        "ok": True,
        "txid": txid,
        "anchor_height": height,
        "confirmations": confirmations,
        "payload_hex": data_hex,
        "wallet": wname,
    }


def parse_anchor_payload(data: bytes) -> Optional[Dict[str, Any]]:
    if len(data) < 52 or data[:4] != ANCHOR_MAGIC:
        return None
    return {
        "magic": "BSM1",
        "asset_id_prefix": data[4:20].hex(),
        "merkle_root": data[20:52].hex(),
    }