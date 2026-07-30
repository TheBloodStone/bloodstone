# MFQ daemon packs — manifest schema v2

**Schema id:** `bloodstone/mfq-daemons/v2`  
**Status:** locked for Phase 1 transparency (2026-07-30)  
**Live portal file:** https://bloodstone.rocks/downloads/mfq-daemons/manifest.json  
**Supersedes:** `bloodstone/mfq-daemons/v1` (sha256-only packs)

## Purpose

Bind each Multi-Fork Qt daemon zip to:

1. **Integrity** — SHA256 of the published artifact  
2. **Provenance** — monorepo (or linked repo) path + commit + build command  
3. **Network identity** — AuxPoW chain id (children must not collide)

## Top-level object

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `schema` or `schema_version` | string | yes | Prefer both during transition: `schema` = `bloodstone/mfq-daemons/v2` |
| `last_updated` | string (ISO-8601 UTC) | yes | When this manifest was written |
| `updated` | string | optional | Legacy v1 date field; keep if useful |
| `notes` | string | optional | Human notes |
| `coins` | object | yes | Map ticker → coin entry |

## Coin entry

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `ticker` | string | recommended | e.g. `LRGK` |
| `name` | string | recommended | Display name |
| `version` | string | yes | Pack / node version label |
| `auxpow_chain_id` | integer | yes for sha256d merge children | STONE parent **1899**, LRGK **1900**, AZURE **1901**, next ≥ **1902** |
| `url` / `download_url` | string | yes | Prefer `url` (v1 clients); `download_url` accepted as alias |
| `sha256` | string | yes | Lowercase hex of zip |
| `sha256_url` | string | recommended | Sidecar URL |
| `daemon` | string | yes | e.g. `lrgkd.exe` |
| `cli` | string | yes | e.g. `lrgk-cli.exe` |
| `rpc_port` | int | yes | |
| `p2p_port` | int | yes | |
| `platform` | string | yes | e.g. `win64` |
| `identity` | string | recommended | Pack identity tag |
| `usable_for_wallets` | bool | recommended | |
| `public_peer` / `public_peers` | string / array | recommended | |
| `bech32_hrp` | string | when applicable | |
| `address_prefix_legacy` | string | when applicable | |
| **`provenance`** | object | **yes (v2)** | See below |

## `provenance` object (required in v2)

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `source_repo` | string URL | yes | e.g. `https://github.com/TheBloodStone/bloodstone` |
| `source_path` | string | yes | Monorepo subdir, e.g. `forks/lrgk` or `core` |
| `source_commit` | string | yes | Full or short git SHA, **or** `PENDING_<TICKER>_PUSH` only until tree lands |
| `build_script` | string | yes | Exact invocation, e.g. `ops/build-mfq-fork-daemons.sh --coin LRGK` |
| `built_utc` | string | yes | ISO-8601 UTC of pack build, or `PENDING` until rebuild under v2 |

### Placeholders allowed only temporarily

- `source_commit`: `PENDING_LRGK_PUSH`, `PENDING_AZURE_PUSH`, `PENDING_STONE_PIN`  
- `built_utc`: `PENDING`  

A pack rebuild that claims a real commit must replace placeholders. CI Phase 1 should fail publish if placeholders remain on a “release” tag (future gate).

## Example (LRGK)

```json
{
  "schema": "bloodstone/mfq-daemons/v2",
  "schema_version": "bloodstone/mfq-daemons/v2",
  "last_updated": "2026-07-30T00:00:00Z",
  "coins": {
    "LRGK": {
      "ticker": "LRGK",
      "version": "0.1.1",
      "auxpow_chain_id": 1900,
      "url": "https://bloodstone.rocks/downloads/mfq-daemons/LRGK-win64.zip",
      "download_url": "https://bloodstone.rocks/downloads/mfq-daemons/LRGK-win64.zip",
      "sha256": "7a5e27e903ad0dfd19ab1151cf594ea4ebe3e4f8280b1e391eafc5e254030f7b",
      "provenance": {
        "source_repo": "https://github.com/TheBloodStone/bloodstone",
        "source_path": "forks/lrgk",
        "source_commit": "PENDING_LRGK_PUSH",
        "build_script": "ops/build-mfq-fork-daemons.sh --coin LRGK",
        "built_utc": "PENDING"
      }
    }
  }
}
```

## Client compatibility

- **MFQ `daemon_manager.py` (v1):** continues to use `url` + `sha256` / `sha256_url`.  
- **v2 fields:** ignored by older clients; required for auditors and future CI.  
- Prefer keeping **both** `url` and `download_url` during transition.

## Related

- Chain id registry (operator): AuxPoW multi-merge children must not share ids  
- GitHub-first policy: `AUDITOR-MAP.md`  
- Transparency cards: `docs/Bloodstone-Ecosystem-Transparency-Roadmap.md`
