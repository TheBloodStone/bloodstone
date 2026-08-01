#!/usr/bin/env python3
"""Fork Lab burn addresses — WP0 derive + verify (keyless P2PKH).

Standalone. No portal, no DB, no network.

Locked layout (RFQ v1.4 §3a) — deriver and verifier share material():

  DOMAIN_SEP = UTF-8 of exactly "bloodstone/fork-lab/burn/v1"

  tag 0x01 = canonical global burn (no draft)
  tag 0x02 = per-draft burn

  material =
      tag
      || u32be(len(DOMAIN_SEP)) || DOMAIN_SEP
      || [ if tag==0x02: u32be(len(draft_id_utf8)) || draft_id_utf8 ]

  payload_20 = Hash160(material)   # RIPEMD160(SHA256(material))
  burn_addr  = Base58Check(version=63, payload_20)   # STONE mainnet P2PKH → 'S'

Naive DOMAIN_SEP||draft_id concatenation is REJECTED (collision-prone).
Smoke samples ScTQ4vuj… / SaVP5mNi… used that path and are NOT final vectors.

Usage:
  python3 fork_lab_burn.py derive
  python3 fork_lab_burn.py derive --draft-id <id>
  python3 fork_lab_burn.py verify <address> [--draft-id <id>|--canonical]
  python3 fork_lab_burn.py vectors
  python3 fork_lab_burn.py selftest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from typing import Any, Dict, Optional, Tuple

# ── Locked constants (STONE mainnet) ─────────────────────────────────────

DOMAIN_SEP = b"bloodstone/fork-lab/burn/v1"
TAG_CANONICAL = 0x01
TAG_DRAFT = 0x02
VERSION_P2PKH = 63  # 0x3f → leading 'S'
SCHEME = "bloodstone/fork-lab/burn/v1-layout"

B58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


# ── Crypto primitives ────────────────────────────────────────────────────


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def hash160(data: bytes) -> bytes:
    """RIPEMD160(SHA256(data)) — 20 bytes. Same as Bitcoin/STONE Hash160."""
    return hashlib.new("ripemd160", sha256(data)).digest()


def b58encode(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    res = bytearray()
    while n > 0:
        n, r = divmod(n, 58)
        res.append(B58_ALPHABET[r])
    pad = 0
    for c in raw:
        if c == 0:
            pad += 1
        else:
            break
    return (B58_ALPHABET[0:1] * pad + res[::-1]).decode("ascii")


def b58decode(s: str) -> bytes:
    n = 0
    for ch in s.encode("ascii"):
        n = n * 58 + B58_ALPHABET.index(ch)
    pad = 0
    for ch in s:
        if ch == "1":
            pad += 1
        else:
            break
    h = n.to_bytes((n.bit_length() + 7) // 8 or 1, "big")
    return b"\x00" * pad + h


def base58check_encode(version: int, payload20: bytes) -> str:
    if len(payload20) != 20:
        raise ValueError(f"payload must be 20 bytes, got {len(payload20)}")
    if not (0 <= version <= 255):
        raise ValueError("version byte out of range")
    body = bytes([version]) + payload20
    checksum = sha256(sha256(body))[:4]
    return b58encode(body + checksum)


def base58check_decode(addr: str) -> Tuple[int, bytes]:
    raw = b58decode(addr)
    if len(raw) != 25:
        raise ValueError(f"decoded length {len(raw)} != 25 (not a P2PKH-sized address)")
    body, chk = raw[:-4], raw[-4:]
    expect = sha256(sha256(body))[:4]
    if chk != expect:
        raise ValueError("Base58Check checksum mismatch")
    return body[0], body[1:]


# ── Locked material encoding ─────────────────────────────────────────────


def material(*, draft_id: Optional[str] = None, canonical: bool = False) -> bytes:
    """Build commitment preimage under the locked length-prefixed layout.

    Exactly one of:
      - canonical=True  → tag 0x01 (no draft field)
      - draft_id=str    → tag 0x02 + length-prefixed UTF-8 draft_id
    """
    if canonical and draft_id is not None:
        raise ValueError("pass either canonical=True or draft_id, not both")
    if not canonical and draft_id is None:
        raise ValueError("pass draft_id=... or canonical=True")
    if canonical:
        return (
            bytes([TAG_CANONICAL])
            + struct.pack(">I", len(DOMAIN_SEP))
            + DOMAIN_SEP
        )
    did = draft_id.encode("utf-8")
    if not did:
        raise ValueError("draft_id must be non-empty UTF-8")
    return (
        bytes([TAG_DRAFT])
        + struct.pack(">I", len(DOMAIN_SEP))
        + DOMAIN_SEP
        + struct.pack(">I", len(did))
        + did
    )


def derive_burn_address(
    *, draft_id: Optional[str] = None, canonical: bool = False
) -> Dict[str, Any]:
    """Derive a STONE P2PKH burn address (convenience; anyone can run this)."""
    mat = material(draft_id=draft_id, canonical=canonical)
    payload = hash160(mat)
    addr = base58check_encode(VERSION_P2PKH, payload)
    return {
        "ok": True,
        "scheme": SCHEME,
        "canonical": bool(canonical),
        "draft_id": None if canonical else draft_id,
        "domain_sep": DOMAIN_SEP.decode("utf-8"),
        "tag": TAG_CANONICAL if canonical else TAG_DRAFT,
        "material_hex": mat.hex(),
        "payload_hex": payload.hex(),
        "version_byte": VERSION_P2PKH,
        "address": addr,
        "leading_char": addr[0] if addr else "",
        "keyless": True,
        "note": (
            "Payload is Hash160(material), never Hash160(pubkey). "
            "No private key was generated; spend requires a Hash160 preimage."
        ),
    }


def verify_burn_address(
    address: str,
    *,
    draft_id: Optional[str] = None,
    canonical: bool = False,
) -> Dict[str, Any]:
    """Load-bearing verifier: prove address is keyless under locked layout.

    Third parties run this with no access to operator infrastructure.
    Exit semantics for CLI: ok=False → non-zero process exit.
    """
    proof: Dict[str, Any] = {
        "ok": False,
        "scheme": SCHEME,
        "address": address,
        "canonical": bool(canonical),
        "draft_id": None if canonical else draft_id,
        "domain_sep": DOMAIN_SEP.decode("utf-8"),
        "expected_version_byte": VERSION_P2PKH,
        "checks": {},
        "keyless_rationale": (
            "If payload equals Hash160(locked material) and material is built "
            "only from published DOMAIN_SEP (+ draft_id), the 20-byte payload is "
            "a hash commitment — not Hash160(pubkey). Finding a spend key requires "
            "inverting Hash160. No private key is used in construction."
        ),
    }
    try:
        ver, payload = base58check_decode(address)
    except Exception as exc:
        proof["error"] = f"decode_failed: {exc}"
        proof["checks"]["base58check"] = False
        return proof

    proof["version_byte"] = ver
    proof["payload_hex"] = payload.hex()
    proof["leading_char"] = address[0] if address else ""
    proof["checks"]["base58check"] = True
    proof["checks"]["starts_with_S"] = address[:1] == "S"
    proof["checks"]["version_is_63"] = ver == VERSION_P2PKH
    proof["checks"]["payload_len_20"] = len(payload) == 20

    try:
        mat = material(draft_id=draft_id, canonical=canonical)
    except Exception as exc:
        proof["error"] = f"material_failed: {exc}"
        return proof

    expect = hash160(mat)
    proof["material_hex"] = mat.hex()
    proof["expected_payload_hex"] = expect.hex()
    proof["tag"] = mat[0]
    proof["checks"]["payload_matches_hash160_material"] = payload == expect

    # Empirical: re-encode and require exact address match (regenerate under v63)
    try:
        regen = base58check_encode(VERSION_P2PKH, expect)
        proof["regenerated_address"] = regen
        proof["checks"]["regenerated_equals_input"] = regen == address
        proof["checks"]["regenerated_starts_with_S"] = regen[:1] == "S"
    except Exception as exc:
        proof["error"] = f"regenerate_failed: {exc}"
        proof["checks"]["regenerated_equals_input"] = False

    proof["ok"] = all(
        [
            proof["checks"].get("base58check"),
            proof["checks"].get("starts_with_S"),
            proof["checks"].get("version_is_63"),
            proof["checks"].get("payload_len_20"),
            proof["checks"].get("payload_matches_hash160_material"),
            proof["checks"].get("regenerated_equals_input"),
            proof["checks"].get("regenerated_starts_with_S"),
        ]
    )
    if not proof["ok"] and "error" not in proof:
        failed = [k for k, v in proof["checks"].items() if not v]
        proof["error"] = "verify_failed: " + ", ".join(failed)
    return proof


def official_vectors() -> Dict[str, Any]:
    """Final vectors under locked layout only (not naive-concat smokes)."""
    canonical = derive_burn_address(canonical=True)
    sample_draft = "wp0-acceptance-draft-001"
    draft = derive_burn_address(draft_id=sample_draft)
    # Prove verifier agrees
    v_c = verify_burn_address(canonical["address"], canonical=True)
    v_d = verify_burn_address(draft["address"], draft_id=sample_draft)
    return {
        "schema": "bloodstone/fork-lab-burn-vectors/v1",
        "scheme": SCHEME,
        "domain_sep": DOMAIN_SEP.decode("utf-8"),
        "version_byte": VERSION_P2PKH,
        "hash": "Hash160 = RIPEMD160(SHA256(x))",
        "checksum": "Base58Check double-SHA256 first 4 bytes",
        "rejected_naive_smoke_samples": [
            {
                "address": "ScTQ4vujNQNwDqHsU9ybQEBQ9ZDG1ZsZMk",
                "reason": "naive DOMAIN_SEP||empty concat — NOT final; do not publish as burn",
            },
            {
                "address": "SaVP5mNi5eGDbD7d83HDxCjAqmRb5ShvsG",
                "reason": "naive DOMAIN_SEP||draft_id concat — NOT final; do not publish as burn",
            },
        ],
        "canonical": {
            "tag": TAG_CANONICAL,
            "address": canonical["address"],
            "material_hex": canonical["material_hex"],
            "payload_hex": canonical["payload_hex"],
            "verify_ok": v_c["ok"],
        },
        "sample_draft": {
            "tag": TAG_DRAFT,
            "draft_id": sample_draft,
            "address": draft["address"],
            "material_hex": draft["material_hex"],
            "payload_hex": draft["payload_hex"],
            "verify_ok": v_d["ok"],
        },
    }


def selftest() -> int:
    """Exit 0 only if derive↔verify round-trip and S-prefix hold."""
    failures = []
    vec = official_vectors()
    if not vec["canonical"]["verify_ok"]:
        failures.append("canonical verify failed")
    if not vec["sample_draft"]["verify_ok"]:
        failures.append("sample draft verify failed")
    for key in ("canonical", "sample_draft"):
        addr = vec[key]["address"]
        if not addr.startswith("S"):
            failures.append(f"{key} does not start with S: {addr}")
        # decode version
        ver, _ = base58check_decode(addr)
        if ver != 63:
            failures.append(f"{key} version {ver} != 63")
    # Collision-style: length prefix must distinguish structured fields
    # (document-level; with fixed DOMAIN_SEP still enforce different drafts differ)
    a = derive_burn_address(draft_id="23")["address"]
    b = derive_burn_address(draft_id="3")["address"]
    if a == b:
        failures.append("draft_id 23 and 3 collided")
    # Reject empty draft
    try:
        material(draft_id="")
        failures.append("empty draft_id should raise")
    except ValueError:
        pass
    # Naive samples must NOT verify under locked layout
    naive = "ScTQ4vujNQNwDqHsU9ybQEBQ9ZDG1ZsZMk"
    if verify_burn_address(naive, canonical=True)["ok"]:
        failures.append("naive smoke must not verify as locked canonical")

    if failures:
        print("SELFTEST FAIL:", "; ".join(failures), file=sys.stderr)
        print(json.dumps(vec, indent=2))
        return 1
    print("SELFTEST OK")
    print(json.dumps(vec, indent=2))
    return 0


def _cli(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description="Fork Lab keyless burn address derive/verify (WP0)")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("derive", help="Derive burn address")
    g = d.add_mutually_exclusive_group(required=True)
    g.add_argument("--canonical", action="store_true")
    g.add_argument("--draft-id", type=str)

    v = sub.add_parser("verify", help="Verify address is keyless under locked layout")
    v.add_argument("address")
    vg = v.add_mutually_exclusive_group(required=True)
    vg.add_argument("--canonical", action="store_true")
    vg.add_argument("--draft-id", type=str)

    sub.add_parser("vectors", help="Print official final vectors (JSON)")
    sub.add_parser("selftest", help="Regenerate + verify; exit non-zero on failure")

    args = p.parse_args(argv)
    if args.cmd == "derive":
        out = derive_burn_address(
            canonical=bool(getattr(args, "canonical", False)),
            draft_id=getattr(args, "draft_id", None),
        )
        print(json.dumps(out, indent=2))
        return 0 if out.get("ok") else 1
    if args.cmd == "verify":
        out = verify_burn_address(
            args.address,
            canonical=bool(getattr(args, "canonical", False)),
            draft_id=getattr(args, "draft_id", None),
        )
        print(json.dumps(out, indent=2))
        return 0 if out.get("ok") else 1
    if args.cmd == "vectors":
        print(json.dumps(official_vectors(), indent=2))
        return 0
    if args.cmd == "selftest":
        return selftest()
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
