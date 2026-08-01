# Bloodstone Fork Registry

**Separate public registry** for Fork Lab coins (forked chains), mirroring chainbase identity for listings and exchange review.

> Closed source is not the vibe. Each live fork should have a **visible** GitHub/GitLab tree (or monorepo path) plus this registry row.

## Layout

```
coins/<TICKER>/
  identity.json     # network ports, salt, magic, fork_id, seeds
  genesis.json      # genesis / premine metadata (public)
  conf.example      # operator conf template
  README.md         # human summary + source links
```

## Live coins

| Ticker | Name | Fork ID | Source (public) | Seed |
|--------|------|---------|-----------------|------|
| **LRGK** | Lil Raghnok Goblin Coin | `e9d304f3379e96859acd131f` | [forks/lrgk](https://github.com/Bloodstone-Team/bloodstone/tree/main/forks/lrgk) · [source tarball](https://bloodstone.rocks/downloads/lrgk/lrgk-core-source-latest.tar.gz) | `64.188.22.190:33685` |
| **AZURE** | Azure Guardian Coin | `7e177be306a616364771bf4c` | [forks/azure](https://github.com/Bloodstone-Team/bloodstone/tree/main/forks/azure) · [source tarball](https://bloodstone.rocks/downloads/azure/azure-core-source-latest.tar.gz) | `64.188.22.190:29825` |

Parent STONE monorepo: https://github.com/Bloodstone-Team/bloodstone

## Target (roadmap)

When org PATs allow **separate** repos (preferred SoT):

- `https://github.com/TheBloodStone/lrgk`
- `https://github.com/TheBloodStone/azure`
- `https://github.com/TheBloodStone/bloodstone-fork-registry`

Until then, monorepo paths under `forks/` + this registry are the **public** source of truth.

## License

Registry metadata: MIT. Coin source trees carry their own `COPYING`.

Doc version: 1.0.0 · 20260801T0810Z UTC
