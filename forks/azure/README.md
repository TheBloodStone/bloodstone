# AZURE (Azure Guardian Coin) — monorepo path

**Ticker:** AZURE  
**Fork Lab id:** `7e177be306a616364771bf4c`  
**AuxPoW chain id:** **1901** (must not collide with STONE 1899 or LRGK 1900)  
**Status:** **Structure stub only** (2026-07-30)

## Why this directory exists before the full tree

Same as LRGK: lock monorepo path + identity + MFQ provenance **before** bulk source import, so the audit surface stays intentional.

- Canonical `source_path` for v2 → `forks/azure`
- Build entry: `ops/build-mfq-fork-daemons.sh --coin AZURE`

## What is not here yet

Full consensus source is **not** in this stub. Production `azured` is built from the operator tree and published as packs/binaries. Full monorepo landing is roadmap card **“Publish AZURE source tree into monorepo”**.

## Network identity (public)

| Field | Value |
|-------|--------|
| P2P | 29825 |
| RPC | 49825 (localhost on seeds) |
| bech32 HRP | `azure` |
| Legacy P2PKH prefix | `A` |
| Public seed | `64.188.22.190:29825` |
| Genesis (mainnet) | `f5e7c12a9a232c07a30835c7934db52ce7372dae41fbe62eedcb36aa5bed87e0` |
| Downloads | https://bloodstone.rocks/downloads/AZURE-Downloads.md |
| Identity JSON | https://bloodstone.rocks/downloads/AZURE_IDENTITY.json |

## MFQ pack (current binary integrity)

| Field | Value |
|-------|--------|
| Pack | https://bloodstone.rocks/downloads/mfq-daemons/AZURE-win64.zip |
| SHA256 | `7fc95b1f754b9c8b542a8da39c4b30ef9f491cdd40d23c5624f74a1e9be616c0` |
| Provenance commit | `PENDING_AZURE_PUSH` until full tree lands |

## See also

- [AUDITOR-MAP.md](../../AUDITOR-MAP.md) §2b, §2c, GitHub-first policy  
- [MFQ manifest v2](../../docs/mfq-daemons-manifest-v2.md)  
- [Transparency roadmap](../../docs/Bloodstone-Ecosystem-Transparency-Roadmap.md)  
