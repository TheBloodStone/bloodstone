"""Shared helpers for Bloodstone stratum servers."""

import binascii
import os
import re
from decimal import Decimal
from typing import Callable, Optional, Tuple

LEGACY_ADDR = re.compile(r"^S[1-9A-HJ-NP-Za-km-z]{25,34}$")
BECH32_ADDR = re.compile(r"^stone1[0-9a-z]{20,}$", re.I)

DEFAULT_PAYOUT_ADDRESS = os.environ.get(
    "BLOODSTONE_DEFAULT_PAYOUT_ADDRESS",
    "SZGS2DNJ29FX9rZVNf2Q5UdEiThyyh6q2v",
)

DIFF1_TARGET = 0x00000000FFFF0000000000000000000000000000000000000000000000000000


def share_target_int(
    block_target_int: int,
    share_difficulty: float,
    solo: bool = False,
    floor_to_block: bool = True,
) -> int:
    """Pool share target using integer math (float division loses precision)."""
    if solo or share_difficulty <= 0:
        return block_target_int
    pool_target = int(Decimal(DIFF1_TARGET) / Decimal(str(share_difficulty)))
    if floor_to_block:
        return max(block_target_int, pool_target)
    return pool_target


def resolve_share_header(
    build_fake_header: Callable,
    hash_fn: Callable,
    job,
    extranonce2: str,
    ntime_hex: str,
    nonce_hex: str,
    share_target_hex: str,
    expected_hash: Optional[str] = None,
    preferred_nonce_be: bool = True,
) -> Optional[Tuple[bytes, str]]:
    """Find the header variant whose PoW hash meets the pool share target."""
    expected = (
        str(expected_hash).strip().lower().replace("0x", "")
        if expected_hash
        else None
    )
    variants = []
    for merkle_flip32 in (False, True):
        for nonce_be in (preferred_nonce_be, not preferred_nonce_be):
            if (merkle_flip32, nonce_be) not in variants:
                variants.append((merkle_flip32, nonce_be))

    for merkle_flip32, nonce_be in variants:
        try:
            fake_header = build_fake_header(
                job,
                extranonce2,
                str(ntime_hex),
                str(nonce_hex),
                nonce_big_endian=nonce_be,
                merkle_flip32=merkle_flip32,
            )
            hash_hex = hash_fn(fake_header).strip().lower()
        except (ValueError, binascii.Error):
            continue
        if expected and hash_hex != expected:
            continue
        if int(hash_hex, 16) <= int(share_target_hex, 16):
            return fake_header, hash_hex
    return None


async def block_job_is_stale(rpc, job_height: int) -> bool:
    """True when the chain tip has advanced past this template (avoids node UAF on submit)."""
    tip = int(await rpc.call("getblockcount"))
    return tip >= int(job_height)


def extranonce_bytes(hex_str: str, size: int = 2) -> bytes:
    raw = binascii.unhexlify(str(hex_str).zfill(size * 2))
    if len(raw) < size:
        raw = b"\x00" * (size - len(raw)) + raw
    return raw[-size:]


def stratum_word_from_hex(hex_str: str) -> int:
    """Match cpuminer-opt / Bitcoin stratum: hex2bin then le32dec."""
    raw = binascii.unhexlify(str(hex_str).zfill(8))
    return int.from_bytes(raw[:4], "little")


def address_from_worker(user: str):
    """Return (payout_address, used_fallback)."""
    raw = (user or "").strip()
    explicit = raw.split(".")[0].strip() if raw else ""
    if explicit and (LEGACY_ADDR.match(explicit) or BECH32_ADDR.match(explicit)):
        return explicit, False
    return DEFAULT_PAYOUT_ADDRESS, True