# LRGK (Lil Raghnok Coin) — monorepo path

**Ticker:** LRGK  
**Fork Lab id:** `e9d304f3379e96859acd131f`  
**AuxPoW chain id:** **1900** (must not collide with STONE 1899 or AZURE 1901)  
**Status:** **Structure stub only** (2026-07-30)

## Why this directory exists before the full tree

Auditors asked for monorepo paths and MFQ provenance **before** dumping operator VPS source. This directory locks:

- Canonical `source_path` for `bloodstone/mfq-daemons/v2` → `forks/lrgk`
- Chain identity pointers
- Build entry expectation: `ops/build-mfq-fork-daemons.sh --coin LRGK`

## What is not here yet

Full consensus source (`src/`, depends, etc.) is **not** published in this stub. Operator build trees still exist on the build host for production seeds/packs. Landing the full tree is roadmap card **“Publish LRGK source tree into monorepo”**.

## Network identity (public)

| Field | Value |
|-------|--------|
| P2P | 33685 |
| RPC | 53685 (localhost on seeds) |
| bech32 HRP | `lrgk` |
| Public seed | `64.188.22.190:33685` |
| Downloads | https://bloodstone.rocks/downloads/LRGK-Downloads.md |

## MFQ pack (current binary integrity)

| Field | Value |
|-------|--------|
| Pack | https://bloodstone.rocks/downloads/mfq-daemons/LRGK-win64.zip |
| SHA256 | `7a5e27e903ad0dfd19ab1151cf594ea4ebe3e4f8280b1e391eafc5e254030f7b` |
| Provenance commit | `PENDING_LRGK_PUSH` until full tree lands |

## See also

- [AUDITOR-MAP.md](../../AUDITOR-MAP.md) §2b, §2c, GitHub-first policy  
- [MFQ manifest v2](../../docs/mfq-daemons-manifest-v2.md)  
- [Transparency roadmap](../../docs/Bloodstone-Ecosystem-Transparency-Roadmap.md)  
