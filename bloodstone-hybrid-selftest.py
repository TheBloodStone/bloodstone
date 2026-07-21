#!/usr/bin/env python3
"""
Bloodstone Hybrid PQ — Phase D selftest (offline, no consensus / no hard fork).

Validates:
  - ECDSA + ML-DSA-65 dual-sign / dual-verify
  - Witness v2 scriptPubKey encoding (OP_2 <32-byte commit>)
  - Negative cases (broken classical or PQ arm)
  - Size envelope for mempool policy planning
  - Optional: re-verify a saved vectors JSON file

Exit 0 = all pass. Safe to run in CI.

  /root/bloodstone-wallet-web/venv/bin/python3 hybrid_selftest.py
  /root/bloodstone-wallet-web/venv/bin/python3 hybrid_selftest.py /path/to/vectors.json
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hybrid_mldsa import (  # noqa: E402
    PQ_ALG,
    WITNESS_VERSION,
    build_vectors,
    hybrid_address,
    hybrid_commitment,
    script_pubkey_v2,
    verify_script_witness,
)


# Expected envelope (FIPS 204 ML-DSA-65 + compressed ECDSA) — policy guidance only
SIZE_BOUNDS = {
    "classical_pk": (33, 33),
    "classical_sig": (64, 72),  # compact usually 64–70; allow slack
    "pq_pk": (1952, 1952),
    "pq_sig": (3293, 3309),  # dilithium_py often 3309
    "witness_total": (5000, 5600),
}


def _check_sizes(sizes: Dict[str, int]) -> List[str]:
    errs = []
    for k, (lo, hi) in SIZE_BOUNDS.items():
        v = sizes.get(k)
        if v is None:
            errs.append(f"missing size {k}")
        elif not (lo <= v <= hi):
            errs.append(f"size {k}={v} outside [{lo},{hi}]")
    return errs


def _check_spk(spk_hex: str, commit_hex: str) -> List[str]:
    errs = []
    try:
        spk = bytes.fromhex(spk_hex)
        commit = bytes.fromhex(commit_hex)
    except ValueError as exc:
        return [f"hex parse: {exc}"]
    if len(spk) != 34:
        errs.append(f"scriptPubKey len {len(spk)} != 34")
    if spk[:2] != b"\x52\x20":
        errs.append(f"scriptPubKey prefix {spk[:2].hex()} != 5220 (OP_2 PUSH32)")
    if spk[2:] != commit:
        errs.append("scriptPubKey program != commitment")
    if len(commit) != 32:
        errs.append(f"commitment len {len(commit)} != 32")
    return errs


def run_fresh() -> Tuple[bool, List[str], Dict[str, Any]]:
    notes: List[str] = []
    vec = build_vectors()
    ok = True

    if not vec["positive"]["ok"]:
        ok = False
        notes.append(f"FAIL positive: {vec['positive']}")
    else:
        notes.append(f"PASS positive: {vec['positive']['reason']}")

    if vec["negative"]["bad_ecdsa"]["ok"]:
        ok = False
        notes.append("FAIL expected ECDSA malleation to reject")
    else:
        notes.append(f"PASS bad ECDSA rejected: {vec['negative']['bad_ecdsa']['reason']}")

    if vec["negative"]["bad_mldsa"]["ok"]:
        ok = False
        notes.append("FAIL expected ML-DSA malleation to reject")
    else:
        notes.append(f"PASS bad ML-DSA rejected: {vec['negative']['bad_mldsa']['reason']}")

    for e in _check_spk(vec["scriptPubKey_hex"], vec["commitment"]):
        ok = False
        notes.append(f"FAIL spk: {e}")
    if not any(n.startswith("FAIL spk") for n in notes):
        notes.append("PASS scriptPubKey OP_2 <32-byte commit>")

    for e in _check_sizes(vec["sizes"]):
        ok = False
        notes.append(f"FAIL sizes: {e}")
    if not any(n.startswith("FAIL sizes") for n in notes):
        notes.append(f"PASS size envelope: {vec['sizes']}")

    addr = vec["address"]
    if not addr.startswith("bshybrid1"):
        ok = False
        notes.append(f"FAIL address prefix: {addr}")
    else:
        notes.append(f"PASS hybrid address: {addr[:24]}…")

    # Recompute commitment from witness keys
    wit = vec["witness_stack_hex"]
    cpk, qpk = bytes.fromhex(wit[1]), bytes.fromhex(wit[3])
    if hybrid_commitment(cpk, qpk).hex() != vec["commitment"]:
        ok = False
        notes.append("FAIL recomputed commitment mismatch")
    else:
        notes.append("PASS commitment(classical_pk, pq_pk)")

    if hybrid_address(bytes.fromhex(vec["commitment"])) != addr:
        ok = False
        notes.append("FAIL address != bech32(commit)")
    else:
        notes.append("PASS address encodes commitment")

    if vec.get("pq_alg") != PQ_ALG or vec.get("witness_version") != WITNESS_VERSION:
        ok = False
        notes.append("FAIL metadata pq_alg/witness_version")
    else:
        notes.append(f"PASS metadata {PQ_ALG} wit_v{WITNESS_VERSION}")

    dep = vec.get("deployment") or {}
    if dep.get("name") != "hybrid_pq_spends" or dep.get("bit") != 4:
        ok = False
        notes.append(f"FAIL deployment metadata: {dep}")
    else:
        notes.append("PASS deployment hybrid_pq_spends bit 4 (soft-fork slot; not activated)")

    return ok, notes, vec


def run_file(path: str) -> Tuple[bool, List[str]]:
    notes: List[str] = []
    with open(path, encoding="utf-8") as fh:
        vec = json.load(fh)
    ok_p, r_p = verify_script_witness(
        vec["scriptPubKey_hex"], vec["witness_stack_hex"], vec["message"]
    )
    if not ok_p:
        notes.append(f"FAIL file positive re-verify: {r_p}")
        return False, notes
    notes.append(f"PASS file positive re-verify: {r_p}")

    for e in _check_spk(vec["scriptPubKey_hex"], vec["commitment"]):
        notes.append(f"FAIL file spk: {e}")
        return False, notes
    notes.append("PASS file scriptPubKey")

    for e in _check_sizes(vec["sizes"]):
        notes.append(f"FAIL file sizes: {e}")
        return False, notes
    notes.append(f"PASS file sizes {vec['sizes']}")
    return True, notes


def main(argv: List[str]) -> int:
    print("=== Bloodstone Hybrid PQ selftest (Phase D offline) ===")
    print("Not a consensus change. Not a hard fork. Offline crypto only.\n")

    all_ok = True
    if len(argv) > 1 and argv[1] not in ("-", "fresh"):
        path = argv[1]
        ok, notes = run_file(path)
        for n in notes:
            print(n)
        all_ok = all_ok and ok
        print()

    ok, notes, vec = run_fresh()
    for n in notes:
        print(n)
    all_ok = all_ok and ok

    out = os.environ.get(
        "HYBRID_VECTORS_OUT",
        "/tmp/bloodstone-hybrid-mldsa-vectors-v2.json",
    )
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(vec, fh, indent=2)
        fh.write("\n")
    print(f"\nwrote vectors: {out}")
    print("RESULT:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
