"""Faucet settings readable/writable by the mining admin UI."""

from __future__ import annotations

import os

from settings_store import read_kv, write_kv

FAUCET_SECRETS = os.environ.get(
    "FAUCET_SECRETS", "/root/bloodstone-faucet/secrets.conf"
)

DEFAULTS = {
    "claim_amount": "25",
    "claim_cooldown_min_hours": "3",
    "claim_cooldown_max_hours": "6",
    "min_faucet_balance": "0.5",
}


def _cooldown_bounds(raw: dict) -> tuple[int, int]:
    if "claim_cooldown_min_hours" in raw or "claim_cooldown_max_hours" in raw:
        lo = int(float(raw.get("claim_cooldown_min_hours", DEFAULTS["claim_cooldown_min_hours"])))
        hi = int(float(raw.get("claim_cooldown_max_hours", DEFAULTS["claim_cooldown_max_hours"])))
    elif "claim_cooldown_hours" in raw:
        legacy = int(float(raw["claim_cooldown_hours"]))
        lo = hi = legacy
    else:
        lo = int(DEFAULTS["claim_cooldown_min_hours"])
        hi = int(DEFAULTS["claim_cooldown_max_hours"])
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi


def load_faucet_settings() -> dict:
    raw = read_kv(FAUCET_SECRETS, DEFAULTS)
    lo, hi = _cooldown_bounds(raw)
    return {
        "claim_amount": float(raw.get("claim_amount", DEFAULTS["claim_amount"])),
        "claim_cooldown_min_hours": lo,
        "claim_cooldown_max_hours": hi,
        "min_faucet_balance": float(
            raw.get("min_faucet_balance", DEFAULTS["min_faucet_balance"])
        ),
    }


def save_faucet_settings(
    claim_amount: float,
    claim_cooldown_min_hours: int,
    claim_cooldown_max_hours: int,
    min_faucet_balance: float,
) -> None:
    lo = int(claim_cooldown_min_hours)
    hi = int(claim_cooldown_max_hours)
    if lo > hi:
        lo, hi = hi, lo
    write_kv(
        FAUCET_SECRETS,
        {
            "claim_amount": f"{claim_amount:g}",
            "claim_cooldown_min_hours": str(lo),
            "claim_cooldown_max_hours": str(hi),
            "min_faucet_balance": f"{min_faucet_balance:g}",
        },
        preserve_keys=["secret_key"],
        header="# Bloodstone faucet configuration",
    )