"""STONE-native payment credits for mesh data products (storage / bandwidth / compute).

Buyers send STONE to the published per-product treasury address. Credits are applied
to a beneficiary STONE address (usually the same wallet they control).

Three separate treasuries keep distribution accounting clean:
  storage  → DATA_SALES_TREASURY_STORAGE
  bandwidth → DATA_SALES_TREASURY_BANDWIDTH
  compute  → DATA_SALES_TREASURY_COMPUTE

Claim flow:
  POST /api/data-sales/claim
  { "txid": "...", "stone_address": "S...", "product": "storage|bandwidth|compute" }

The coordinator verifies the tx pays the product treasury and credits the ledger
using the same quota tables as the Blurt rails.
"""

from __future__ import annotations

from chain_mesh.security import public_error
import json
import os
import time
import urllib.request
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from chain_mesh import depin_credits as depin
from chain_mesh import storage_credits as storage

# Rates: whole STONE → credit units (matches former 1 BLURT packs at 1 STONE ≈ 1 BLURT bridge).
STONE_PER_GIB_STORAGE = Decimal(os.environ.get("DATA_SALES_STONE_PER_GIB", "1"))
STONE_PER_100MIB_BANDWIDTH = Decimal(os.environ.get("DATA_SALES_STONE_PER_100MIB", "1"))
STONE_PER_GFLOP_COMPUTE = Decimal(os.environ.get("DATA_SALES_STONE_PER_GFLOP", "1"))
# Monthly keep-alive for data still on the mesh (sustainability).
STONE_UPKEEP_PER_GIB_MONTH = Decimal(
    os.environ.get("DATA_SALES_UPKEEP_STONE_PER_GIB_MONTH", "0.1")
)
UPKEEP_GRACE_DAYS = int(os.environ.get("DATA_SALES_UPKEEP_GRACE_DAYS", "30"))

# Per-product treasuries (preferred). Legacy single treasury is fallback only.
_TREASURIES: Dict[str, str] = {
    "storage": (
        os.environ.get("DATA_SALES_TREASURY_STORAGE")
        or os.environ.get("DATA_SALES_TREASURY_ADDRESS_STORAGE")
        or ""
    ).strip(),
    "bandwidth": (
        os.environ.get("DATA_SALES_TREASURY_BANDWIDTH")
        or os.environ.get("DATA_SALES_TREASURY_ADDRESS_BANDWIDTH")
        or ""
    ).strip(),
    "compute": (
        os.environ.get("DATA_SALES_TREASURY_COMPUTE")
        or os.environ.get("DATA_SALES_TREASURY_ADDRESS_COMPUTE")
        or ""
    ).strip(),
}

# Legacy single address — used only if a product treasury is unset.
LEGACY_TREASURY = (
    os.environ.get("DATA_SALES_TREASURY_ADDRESS")
    or os.environ.get("BLOODSTONE_DATA_SALES_ADDRESS")
    or ""
).strip()

_LABELS = {
    "storage": "data-sales-storage",
    "bandwidth": "data-sales-bandwidth",
    "compute": "data-sales-compute",
}

BYTES_PER_GIB = 1024 * 1024 * 1024
BYTES_PER_100MIB = 100 * 1024 * 1024
FLOPS_PER_GFLOP = 1_000_000_000

RPC_URL = os.environ.get(
    "BLOODSTONE_RPC_URL",
    "http://bloodstone:a250b99cd8798d396087d0cbd87ab1721cb6f9ba53f6ba06adf77074e6886aff@127.0.0.1:18332/",
)
RPC_WALLET = os.environ.get("DATA_SALES_RPC_WALLET", "mine")


def _rpc(method: str, params=None, wallet: Optional[str] = None) -> Any:
    params = params if params is not None else []
    url = RPC_URL
    if wallet:
        base = RPC_URL.rstrip("/")
        if "/wallet/" not in base:
            if "://" in base:
                scheme, rest = base.split("://", 1)
                if "@" in rest:
                    auth, host = rest.split("@", 1)
                    url = f"{scheme}://{auth}@{host.rstrip('/')}/wallet/{wallet}"
                else:
                    url = f"{scheme}://{rest.rstrip('/')}/wallet/{wallet}"
            else:
                url = f"{base}/wallet/{wallet}"
        else:
            url = base
    payload = json.dumps(
        {"jsonrpc": "1.0", "id": "data-sales", "method": method, "params": params}
    ).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "text/plain"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
    if body.get("error"):
        raise RuntimeError(body["error"])
    return body.get("result")


def _normalize_product(product: str) -> str:
    p = (product or "").strip().lower()
    if p in ("bandwidth", "data", "transfer"):
        return "bandwidth"
    if p in ("upkeep", "storage-upkeep", "storage_upkeep", "retention"):
        return "upkeep"
    if p in ("storage", "compute"):
        return p
    raise ValueError("product must be storage, bandwidth, compute, or upkeep")


def treasury_address(product: str = "") -> str:
    """Return treasury for a product, or the legacy single treasury if product empty."""
    if not product:
        # Prefer storage as the “primary” published address for backward compat,
        # else legacy single address.
        return (
            treasury_for("storage")
            or LEGACY_TREASURY
            or treasury_for("bandwidth")
            or treasury_for("compute")
        )
    return treasury_for(_normalize_product(product))


def treasury_for(product: str) -> str:
    """Resolve (and cache) the STONE treasury address for a product type."""
    product = _normalize_product(product)
    # Upkeep settles into the storage treasury (same provider pot).
    if product == "upkeep":
        product = "storage"
    addr = (_TREASURIES.get(product) or "").strip()
    if addr:
        return addr
    if LEGACY_TREASURY:
        _TREASURIES[product] = LEGACY_TREASURY
        return LEGACY_TREASURY
    try:
        label = _LABELS[product]
        addr = str(_rpc("getnewaddress", [label], wallet=RPC_WALLET) or "").strip()
        if addr:
            _TREASURIES[product] = addr
            return addr
    except Exception:
        pass
    return ""


def treasuries() -> Dict[str, str]:
    """All three product treasuries."""
    return {
        "storage": treasury_for("storage"),
        "bandwidth": treasury_for("bandwidth"),
        "compute": treasury_for("compute"),
    }


def rates_payload() -> Dict[str, Any]:
    t = treasuries()
    return {
        "currency": "STONE",
        "treasury_addresses": t,
        # Backward-compatible alias (storage treasury).
        "treasury_address": t.get("storage") or LEGACY_TREASURY or "",
        "payment_method": (
            "send STONE to the product treasury_address for storage, bandwidth, or compute"
        ),
        "storage": {
            "stone_per_unit": float(STONE_PER_GIB_STORAGE),
            "unit": "1 GiB",
            "treasury_address": t["storage"],
            "bytes_per_stone": int(
                BYTES_PER_GIB / max(float(STONE_PER_GIB_STORAGE), 1e-12)
            ),
            "display": f"{STONE_PER_GIB_STORAGE} STONE / GiB",
            "upkeep_stone_per_gib_month": float(STONE_UPKEEP_PER_GIB_MONTH),
            "upkeep_display": f"{STONE_UPKEEP_PER_GIB_MONTH:g} STONE / GiB · month",
            "upkeep_grace_days": UPKEEP_GRACE_DAYS,
        },
        "bandwidth": {
            "stone_per_unit": float(STONE_PER_100MIB_BANDWIDTH),
            "unit": "100 MiB",
            "treasury_address": t["bandwidth"],
            "bytes_per_stone": int(
                BYTES_PER_100MIB / max(float(STONE_PER_100MIB_BANDWIDTH), 1e-12)
            ),
            "display": f"{STONE_PER_100MIB_BANDWIDTH} STONE / 100 MiB",
        },
        "compute": {
            "stone_per_unit": float(STONE_PER_GFLOP_COMPUTE),
            "unit": "1 GFLOP",
            "treasury_address": t["compute"],
            "flops_per_stone": int(
                FLOPS_PER_GFLOP / max(float(STONE_PER_GFLOP_COMPUTE), 1e-12)
            ),
            "display": f"{STONE_PER_GFLOP_COMPUTE} STONE / GFLOP",
        },
        "upkeep": {
            "stone_per_gib_month": float(STONE_UPKEEP_PER_GIB_MONTH),
            "unit": "1 GiB · month",
            "display": f"{STONE_UPKEEP_PER_GIB_MONTH:g} STONE / GiB · month",
            "display_tib": f"{float(STONE_UPKEEP_PER_GIB_MONTH) * 1024:g} STONE / TiB · month",
            "grace_days": UPKEEP_GRACE_DAYS,
            "treasury_address": t["storage"],
            "assessed_on": "bytes currently stored (old/retained data)",
            "claim_product": "upkeep",
        },
        "claim_api": "/api/data-sales/claim",
        "note": (
            "Primary settlement is STONE on Bloodstone mainnet. "
            "Use a separate treasury per product so storage / bandwidth / compute "
            "receipts stay isolated for distribution accounting. "
            "Storage also has a monthly UPKEEP fee on retained data so long-lived "
            "archives stay sustainable for providers. "
            "Blurt memo rails remain an optional alternate for Blurt-native users."
        ),
    }


def _amount_to_credits(product: str, amount_stone: Decimal) -> Dict[str, Any]:
    product = _normalize_product(product)
    if amount_stone <= 0:
        raise ValueError("payment amount must be positive")
    if product == "storage":
        units = amount_stone / STONE_PER_GIB_STORAGE
        bytes_credit = int(units * BYTES_PER_GIB)
        return {"product": "storage", "bytes": bytes_credit, "units": float(units)}
    if product == "bandwidth":
        units = amount_stone / STONE_PER_100MIB_BANDWIDTH
        bytes_credit = int(units * BYTES_PER_100MIB)
        return {"product": "bandwidth", "bytes": bytes_credit, "units": float(units)}
    if product == "upkeep":
        # STONE → GiB-months of retention at published upkeep rate
        units = amount_stone / STONE_UPKEEP_PER_GIB_MONTH
        return {
            "product": "upkeep",
            "gib_months": float(units),
            "units": float(units),
            "stone_per_gib_month": float(STONE_UPKEEP_PER_GIB_MONTH),
        }
    # compute
    units = amount_stone / STONE_PER_GFLOP_COMPUTE
    flops = int(units * FLOPS_PER_GFLOP)
    return {"product": "compute", "flops": flops, "units": float(units)}


def _tx_amount_to_address(tx: dict, addr: str) -> Decimal:
    """Sum STONE received by addr in a gettransaction / getrawtransaction result."""
    if not addr:
        return Decimal("0")
    total = Decimal("0")
    for d in tx.get("details") or []:
        if d.get("category") == "receive" and d.get("address") == addr:
            total += Decimal(str(d.get("amount") or 0))
    if total > 0:
        return total
    for vout in tx.get("vout") or []:
        spk = vout.get("scriptPubKey") or {}
        addrs = list(spk.get("addresses") or [])
        if spk.get("address"):
            addrs.append(spk["address"])
        if addr in addrs:
            total += Decimal(str(vout.get("value") or 0))
    return total


def _load_tx(txid: str) -> dict:
    try:
        return _rpc("gettransaction", [txid], wallet=RPC_WALLET) or {}
    except Exception:
        return _rpc("getrawtransaction", [txid, True]) or {}


def _tx_paid_to_product_treasury(txid: str, product: str) -> Tuple[Decimal, str]:
    """Return (amount, treasury_address) for payment to the product treasury."""
    product = _normalize_product(product)
    addr = treasury_for(product)
    if not addr:
        raise RuntimeError(
            f"DATA_SALES_TREASURY_{product.upper()} not configured"
        )
    tx = _load_tx(txid)
    amount = _tx_amount_to_address(tx, addr)
    return amount, addr


def claim_payment(
    *,
    txid: str,
    stone_address: str,
    product: str,
    job_id: str = "",
    referral_code: str = "",
) -> Dict[str, Any]:
    """Verify STONE payment to the product treasury and credit the beneficiary.

    Team/founder/referral splits use the **same percentages** as the USDT rail.
    """
    txid = (txid or "").strip()
    stone_address = (stone_address or "").strip()
    product = _normalize_product(product)
    if len(txid) < 64:
        raise ValueError("txid required")
    if len(stone_address) < 25:
        raise ValueError("stone_address required")

    # Upkeep pays the storage treasury.
    pay_product = "storage" if product == "upkeep" else product
    amount, treasury = _tx_paid_to_product_treasury(txid, pay_product)
    if amount <= 0:
        raise ValueError(
            f"transaction does not pay the {pay_product} data-sales treasury ({treasury})"
        )

    # Guard against accidental double-claim across products if someone paid the
    # wrong treasury: only the matching product address counts.
    credits = _amount_to_credits(product, amount)
    synthetic = f"stone:{txid}:{product}"

    # Book revenue split (same % as USDT commercial path)
    revenue_split = None
    try:
        from chain_mesh import usdt_monetization as mon

        revenue_split = mon.record_stone_payment(
            product=credits["product"],
            amount_stone=str(amount),
            txid=txid,
            stone_address=stone_address,
            referral_code=referral_code or "",
            payment_ref=synthetic,
        )
    except Exception as exc:
        revenue_split = {"ok": False, "error": public_error(exc)}

    if credits["product"] == "storage":
        result = storage.credit_from_blurt_transfer(
            stone_address=stone_address,
            bytes_credited=int(credits["bytes"]),
            blurt_txid=synthetic,
            blurt_from="stone-mainnet",
            blurt_amount=str(amount),
            memo=f"stone-pay storage {amount} → {treasury}",
        )
    elif credits["product"] == "bandwidth":
        result = depin.credit_bandwidth(
            stone_address=stone_address,
            bytes_credited=int(credits["bytes"]),
            blurt_txid=synthetic,
            blurt_from="stone-mainnet",
            blurt_amount=str(amount),
            memo=f"stone-pay bandwidth {amount} → {treasury}",
        )
    elif credits["product"] == "upkeep":
        from chain_mesh import storage_upkeep as upkeep

        result = upkeep.record_upkeep_payment(
            stone_address=stone_address,
            stone_amount=str(amount),
            payment_ref=synthetic,
            memo=f"stone-pay upkeep {amount} → {treasury}",
            source="stone-mainnet",
        )
    else:
        jid = (job_id or "prepaid").strip() or "prepaid"
        result = depin.credit_compute(
            stone_address=stone_address,
            job_id=jid,
            flops_credited=int(credits["flops"]),
            blurt_txid=synthetic,
            blurt_from="stone-mainnet",
            blurt_amount=str(amount),
            memo=f"stone-pay compute {amount} → {treasury}",
        )

    return {
        "ok": True,
        "txid": txid,
        "stone_address": stone_address,
        "product": credits["product"],
        "treasury_address": treasury,
        "amount_stone": str(amount),
        "credits": credits,
        "ledger": result,
        "revenue_split": revenue_split,
        "split_note": (
            "Team/founder/referral percentages match the USDT commercial rail "
            "(MONETIZE_TEAM_SPLIT + founder trail/active + referral)."
        ),
        "claimed_at": int(time.time()),
    }
