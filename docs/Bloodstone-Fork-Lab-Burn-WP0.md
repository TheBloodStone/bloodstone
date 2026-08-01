# Bloodstone Fork Lab — Burn Address WP0 (verifier-first)

**Document version:** 1.0  
**Date:** 2026-08-01  
**Scheme:** `bloodstone/fork-lab/burn/v1-layout`  
**Status:** Production vectors under the **locked length-prefixed layout** only.

> The **verifier** is the credibility anchor. Anyone can mint an `S…` string.
> Trust is demonstrated when a third party, with no operator access, proves
> `payload == Hash160(material)` under the published layout.

---

## Downloads (same package)

| Artifact | URL |
|----------|-----|
| **Verifier + deriver (standalone)** | https://bloodstone.rocks/downloads/fork_lab_burn.py |
| **Official vectors (JSON)** | https://bloodstone.rocks/downloads/fork-lab-burn-vectors.json |
| **This doc** | https://bloodstone.rocks/downloads/Bloodstone-Fork-Lab-Burn-WP0.md |
| Latest alias | https://bloodstone.rocks/downloads/Bloodstone-Fork-Lab-Burn-WP0-latest.md |

```bash
# Self-test (must exit 0): regenerates under version 63, verifies, rejects naive smokes
curl -sS -O https://bloodstone.rocks/downloads/fork_lab_burn.py
python3 fork_lab_burn.py selftest

# Verify the canonical burn
python3 fork_lab_burn.py verify ShGX17JqtmvKaqTUdKufpS3hqmVsyp3mA3 --canonical

# Verify the sample draft vector
python3 fork_lab_burn.py verify SkQJDpZGhjJptscpCnGcMXnx1YP7JqPS7H \
  --draft-id wp0-acceptance-draft-001
```

---

## STONE constants

| Constant | Value |
|----------|--------|
| P2PKH version byte | **63 (0x3f)** → leading **`S`** |
| Checksum | Base58Check = double-SHA256, first 4 bytes |
| Bech32 | Enabled (`stone1…`); **canonical burn is legacy P2PKH** |
| Hash H | **Hash160** = RIPEMD160(SHA256(x)) → 20 bytes |

---

## Locked byte layout

```
DOMAIN_SEP = UTF-8 of exactly "bloodstone/fork-lab/burn/v1"

tag 0x01 = canonical global burn (no draft field)
tag 0x02 = per-draft burn

material =
    tag
    || u32be(len(DOMAIN_SEP)) || DOMAIN_SEP
    || [ if tag==0x02: u32be(len(draft_id_utf8)) || draft_id_utf8 ]

payload_20 = Hash160(material)
burn_addr  = Base58Check(version=63, payload_20)
```

Raw `DOMAIN_SEP || draft_id` is **underspecified** and rejected. Changing
DOMAIN_SEP or tag bytes = a new scheme version.

---

## Final vectors (locked layout only)

### Canonical (tag 0x01)

| Field | Value |
|-------|--------|
| **Address** | `ShGX17JqtmvKaqTUdKufpS3hqmVsyp3mA3` |
| material_hex | `010000001b626c6f6f6473746f6e652f666f726b2d6c61622f6275726e2f7631` |
| payload_hex | `db1ab3996828afaf2deda728b7ccee523aa92169` |

### Sample draft (tag 0x02, `draft_id = wp0-acceptance-draft-001`)

| Field | Value |
|-------|--------|
| **Address** | `SkQJDpZGhjJptscpCnGcMXnx1YP7JqPS7H` |
| material_hex | `020000001b626c6f6f6473746f6e652f666f726b2d6c61622f6275726e2f7631000000187770302d616363657074616e63652d64726166742d303031` |
| payload_hex | `fd7bbcd9a346e5607ed5841e4b8aa9209f592b9d` |

### Rejected (do not publish as burns)

| Address | Why |
|---------|-----|
| `ScTQ4vujNQNwDqHsU9ybQEBQ9ZDG1ZsZMk` | Naive concat smoke — **not** final |
| `SaVP5mNi5eGDbD7d83HDxCjAqmRb5ShvsG` | Naive concat smoke — **not** final |

`selftest` asserts naive samples **fail** `verify --canonical`.

---

## What the verifier prints (proof fields)

- version_byte (must be 63)
- leading_char (must be `S`)
- payload_hex / expected_payload_hex
- material_hex (locked encoding)
- Base58Check OK
- regenerated_address equals input (empirical re-encode under v63)
- payload_matches_hash160_material
- keyless_rationale
- ok true/false — process exit non-zero on failure

---

## Keyless argument

The 20-byte payload is **Hash160(published material)**, never `Hash160(pubkey)`.
No private key is generated or stored. Spending would require finding a preimage
for that Hash160 output — not feasible. The absence of a key is the burn.

---

## Guardrails

- Never derive payload from a public key.
- Never store a private key “for” a burn address.
- DOMAIN_SEP and layout stay fully public.
- Deriver and verifier must share one `material()` implementation.

---

*Bloodstone Fork Lab · WP0 · burn v1-layout · 2026-08-01*

---

## Independent verification (WP0 close gate)

Run on any clean machine with Python 3 — no Bloodstone infra required:

```bash
curl -sS -O https://bloodstone.rocks/downloads/fork_lab_burn.py
curl -sS -O https://bloodstone.rocks/downloads/fork-lab-burn-vectors.json
python3 fork_lab_burn.py selftest
python3 fork_lab_burn.py verify ShGX17JqtmvKaqTUdKufpS3hqmVsyp3mA3 --canonical
```

Hand-check: decode Base58Check → version **63**, payload **20 bytes** equals
`Hash160(material)` for tag `0x01` length-prefixed `DOMAIN_SEP`.

**Lab independent run (2026-08-01):** clean `/tmp` copy of published artifacts —
`selftest` exit 0; hand-decode payload match `db1ab399…2169`; naive smokes fail.
A second skeptic run outside this host still welcome for the paper trail.

## Skeptic run (easy)

See [Bloodstone-Fork-Lab-WP0-Skeptic-Run.md](Bloodstone-Fork-Lab-WP0-Skeptic-Run.md).
