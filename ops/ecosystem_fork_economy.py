"""Bloodstone ecosystem fork economy — additive mesh formula (product lock).

Discord / founder alignment (July 2026):
  When a coin is added to the ecosystem:
    1) Miners can merge-mine additional coins (forks MUST parent Bloodstone).
    2) Mesh providers earn a portion of that coin's mining rewards (in the NEW ticker).
    3) End users still pay for mesh resources in STONE (demand floor).
    4) Resellers may accept other coins from customers but settle bulk STONE for resources.
    5) Sister forks (incl. LRGK-style) must be *additive* — never replace STONE for mesh settlement.

This module is the single source of truth for the *formula* embedded in Fork Lab
manifests. On-chain/pool payout wiring may consume these fields later; the policy
is enforced in registry/docs/UI first so every new coin (Izal, LRGK expansion, etc.)
ships under the same rules.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# --- Tunables (env-overridable) -------------------------------------------------
# Mesh share of *each fork coin's* block subsidy (and/or pool-distributed reward)
# paid in that fork's ticker to mesh providers (not in STONE, not instead of STONE demand).
MESH_PROVIDER_REWARD_BPS = max(
    0,
    min(5000, int(os.environ.get("ECOSYSTEM_MESH_PROVIDER_REWARD_BPS", "1000"))),
)  # default 10%

# Optional founder / lab reserve from fork subsidy (bps of block reward).
FORK_LAB_RESERVE_BPS = max(
    0,
    min(2000, int(os.environ.get("ECOSYSTEM_FORK_LAB_RESERVE_BPS", "0"))),
)

# Miners get the residual after mesh (+ optional reserve).
def _miner_bps() -> int:
    return max(0, 10000 - MESH_PROVIDER_REWARD_BPS - FORK_LAB_RESERVE_BPS)


# Constitutional settlement: all *native Bloodstone protocol services* → STONE only.
# Keep this list descriptive, not exhaustive — new core capabilities inherit the rule
# without amending the economy formula (same discipline as Edge Presence Proof RFC).
RESOURCE_PAYMENT_TICKER = "STONE"
PROTOCOL_SERVICES = [
    "storage",
    "compute",
    "bandwidth",
    "mesh_networking",
    "content_cataloguing",
    "identity_services",
    "future_core_protocol_capabilities",
]
PROTOCOL_SERVICES_NOTE = (
    "All native Bloodstone protocol services are settled exclusively in STONE. "
    "That includes storage, compute, bandwidth, mesh networking, content cataloguing, "
    "identity services, and future core protocol capabilities. "
    "Fork coins do not reprice or replace protocol settlement."
)
RESOURCE_PAYMENT_NOTE = PROTOCOL_SERVICES_NOTE

# Reseller path: customer may pay in fork coin; reseller buys bulk protocol services in STONE.
RESELLER_NOTE = (
    "Resellers may accept fork coins (or USDT) from end customers, but bulk purchase of "
    "native Bloodstone protocol services always settles in STONE."
)

SCHEMA = "bloodstone/ecosystem-fork-economy/v1"


def bps_to_frac(bps: int) -> float:
    return max(0.0, float(bps) / 10000.0)


def split_block_reward(block_reward: float) -> Dict[str, Any]:
    """Apply the locked split to a numeric block reward."""
    try:
        br = float(block_reward or 0)
    except (TypeError, ValueError):
        br = 0.0
    mesh_bps = MESH_PROVIDER_REWARD_BPS
    reserve_bps = FORK_LAB_RESERVE_BPS
    miner_bps = _miner_bps()
    return {
        "block_reward": br,
        "miners": {
            "bps": miner_bps,
            "amount": br * bps_to_frac(miner_bps),
            "asset": "fork_ticker",
            "note": "PoW / pool share recipients on the fork chain",
        },
        "mesh_providers": {
            "bps": mesh_bps,
            "amount": br * bps_to_frac(mesh_bps),
            "asset": "fork_ticker",
            "note": (
                "Paid in the *new coin's* ticker to mesh providers (storage / bandwidth "
                "contributors), proportional to verified mesh work — additive income "
                "when this coin is merge-mined or its pool runs."
            ),
        },
        "lab_reserve": {
            "bps": reserve_bps,
            "amount": br * bps_to_frac(reserve_bps),
            "asset": "fork_ticker",
            "note": "Optional lab/treasury slice (default 0)",
        },
    }


def economy_for_fork(
    *,
    ticker: str,
    fork_id: str = "",
    block_reward: float = 100.0,
    name: str = "",
) -> Dict[str, Any]:
    """Full economy policy block for a single ecosystem fork (manifest field)."""
    t = str(ticker or "").strip().upper() or "FORK"
    split = split_block_reward(block_reward)
    return {
        "schema": SCHEMA,
        "role": "ecosystem_fork",
        "ticker": t,
        "fork_id": fork_id or None,
        "name": name or t,
        "principles": [
            "additive_to_bloodstone",
            "merge_mine_parent_mandatory",
            "mesh_providers_earn_fork_coin_from_hash",
            "protocol_services_settle_in_stone",
            "resellers_settle_bulk_protocol_services_in_stone",
        ],
        "merge_mine": {
            "parent": "STONE (Bloodstone) — mandatory for ecosystem forks",
            "sisters": "optional per-fork checkboxes (e.g. LRGK-style companions)",
            "bloodstone_enables_children": "optional per child (default off)",
            "cpu_lanes": "neoscrypt / yespower remain local per chain",
            "sha256d_aux": "ecosystem merge toggles apply here",
        },
        "block_reward_split": split,
        "mesh_providers": {
            "earn_from": "portion of this fork's mining rewards",
            "paid_in": t,
            "bps": MESH_PROVIDER_REWARD_BPS,
            "frac": bps_to_frac(MESH_PROVIDER_REWARD_BPS),
            "does_not_replace": "STONE earnings from mesh product sales / catalog",
            "formula_text": (
                f"On each {t} block (or pool payout epoch): "
                f"{MESH_PROVIDER_REWARD_BPS / 100:.2f}% of subsidy → mesh providers in {t}; "
                f"{_miner_bps() / 100:.2f}% → miners in {t}."
            ),
        },
        "resource_market": {
            "end_user_pays": RESOURCE_PAYMENT_TICKER,
            "bulk_settlement": RESOURCE_PAYMENT_TICKER,
            "note": RESOURCE_PAYMENT_NOTE,
            "reseller": {
                "may_accept": ["fork_coins", "USDT", "STONE"],
                "must_settle_bulk_resources_in": RESOURCE_PAYMENT_TICKER,
                "note": RESELLER_NOTE,
            },
        },
        "non_cannibalization": {
            "stone_demand": "mesh SKUs and bulk always STONE",
            "fork_demand": "mining + optional community media of trade of the fork coin",
            "lrgk_class_siblings": (
                "Companion chains expand merge-mine surface and mesh reward streams; "
                "they must not divert resource settlement off STONE."
            ),
        },
        "operator_summary": (
            f"{t}: merge-mine STONE (required). Mesh providers earn "
            f"{MESH_PROVIDER_REWARD_BPS / 100:.1f}% of {t} mining rewards in {t}. "
            f"Users still buy mesh resources with STONE."
        ),
    }


def bloodstone_parent_economy_view() -> Dict[str, Any]:
    """How Bloodstone itself sits relative to children."""
    return {
        "schema": SCHEMA,
        "role": "bloodstone_parent",
        "ticker": "STONE",
        "resource_settlement": RESOURCE_PAYMENT_TICKER,
        "child_forks": {
            "merge_mine_on_parent": "optional_per_child",
            "mesh_provider_reward_currency": "each_child_ticker",
            "note": (
                "Enabling a child on Bloodstone SHA256d does not move mesh SKU "
                "pricing off STONE; it adds an optional aux reward stream in the child coin."
            ),
        },
        "mesh_providers": {
            "from_stone_economy": "catalog / paid views / storage rates in STONE",
            "from_each_live_fork": (
                f"up to {MESH_PROVIDER_REWARD_BPS / 100:.1f}% of that fork's mining rewards "
                "in the fork ticker"
            ),
        },
    }


def public_formula() -> Dict[str, Any]:
    """Machine + human readable formula for APIs and Fork Lab UI."""
    return {
        "ok": True,
        "schema": SCHEMA,
        "title": "Ecosystem fork formula (additive mesh)",
        "when_a_coin_is_added": [
            "Miners can merge-mine the new coin alongside Bloodstone (parent mandatory on forks).",
            (
                f"Mesh providers earn {MESH_PROVIDER_REWARD_BPS / 100:.1f}% of the new coin's "
                "mining rewards paid in that coin's ticker."
            ),
            "End users still pay for mesh resources in STONE.",
            "Resellers may accept other coins from customers but buy bulk resources in STONE.",
        ],
        "block_reward_split_bps": {
            "miners": _miner_bps(),
            "mesh_providers": MESH_PROVIDER_REWARD_BPS,
            "lab_reserve": FORK_LAB_RESERVE_BPS,
            "basis": 10000,
        },
        "example_100_coin_block": split_block_reward(100.0),
        "bloodstone": bloodstone_parent_economy_view(),
        "docs": "/downloads/Bloodstone-Ecosystem-Fork-Economy.md",
        "env": {
            "ECOSYSTEM_MESH_PROVIDER_REWARD_BPS": MESH_PROVIDER_REWARD_BPS,
            "ECOSYSTEM_FORK_LAB_RESERVE_BPS": FORK_LAB_RESERVE_BPS,
        },
    }


def attach_to_fork_public(row_pub: Dict[str, Any]) -> Dict[str, Any]:
    """Enrich a public fork dict with economy + keep existing merge_mine if present."""
    out = dict(row_pub or {})
    ticker = str(out.get("ticker") or "").upper()
    fork_id = str(out.get("fork_id") or "")
    name = str(out.get("name") or ticker)
    try:
        br = float(out.get("block_reward") or 100)
    except (TypeError, ValueError):
        br = 100.0
    out["ecosystem_economy"] = economy_for_fork(
        ticker=ticker, fork_id=fork_id, block_reward=br, name=name
    )
    return out
