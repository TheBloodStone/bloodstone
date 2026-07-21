# MANIFEST — Linux node installer surface

Use this when auditing the **installer**, not the whole monorepo.

## Section A — Installer scripts (must review)

```
packages/linux-node/start-node.sh
packages/linux-node/install-chain-bootstrap.sh
packages/linux-node/install-from-source.sh    # clone GitHub monorepo + compile
packages/linux-node/verify-release.sh         # SHA-256 (+ optional PGP)
packages/linux-node/bloodstone.conf.example
packages/linux-node/README.md
packages/linux-node/MANIFEST.md
```

## Section B — Packagers (how A is assembled)

```
build-bloodstone-node-arm64-package.sh      # VPS root (copied into monorepo ops/ when published)
build-bloodstone-node-distribution.sh      # x86_64
```

On the open-source monorepo these may appear under `ops/` if mirrored; the **runtime** scripts that land on a Pi are only Section A.

## Section C — Node binary source (consensus daemon, not shell installer)

```
core/                    # bloodstoned / bloodstone-cli build tree
```

Review C only for consensus/RPC security — not for `start-node.sh` bootstrap logic.

## Section D — Bootstrap artifact (data, not code)

```
downloads/bloodstone-chain-bootstrap-latest.tar.gz   # tip snapshot served over HTTPS
```

Installer verifies SHA-256 of this file before extract.

## Explicitly out of scope for “node installer” audits

| Path | Why |
|------|-----|
| `ops/bloodstone-stratum*.py` | Pool mining, not node install |
| `ops/bloodstone-pi-fleet/` | Separate Pi fleet convergence installer |
| `miner-android/` | Android APK |
| `portal/` | Public website |
| `release-downloads` git branch | Flat binary mirror for GitHub downloads |
