# Bloodstone Node 0.7.6 — Security Audit Remediation

**Doc version:** 1.0 · 2026-07-21  
**Package:** `bloodstone-node-0.7.6-linux-aarch64.tar.gz`  
**Public:** https://bloodstone.rocks/downloads/Bloodstone-Node-0.7.6-Security-Audit-Remediation.md  

This maps the merged audit findings to the **implemented** fixes in the packaging scripts.

---

## Status vs merged audit

| # | Finding | Severity | Status | Implementation |
|---|---------|----------|--------|----------------|
| **3** | RPC password file world-readable | **High** | **Fixed** | `umask 077`; `chmod 600` on conf after create/edit; `chmod 700` on datadir; also tightens existing conf |
| **8** | Unsafe tar (symlinks / ownership) | **High** | **Fixed** | Reject `l`/`h` members via `tar -tvzf`; extract with `--no-same-owner --no-same-permissions` (+ `--no-overwrite-dir` when GNU tar supports it); path traversal checks retained |
| **4** | Hardcoded seeds / eclipse risk | **Medium** | **Mitigated** | Defaults unchanged for bootstrap; override via `BLOODSTONE_SEEDS` or `BLOODSTONE_SEED_NODES` (space-separated `host:port`) |
| **5** | curl protocol downgrade | **Medium** | **Fixed** | `curl --proto '=https' --tlsv1.2` (optional `--cert-status` with fallback); `wget --https-only` |
| **1** | Shebang `/usr/bin/env bash` | Low | **Hardened** | Scripts use `#!/bin/bash` (audit agreed env shebang was acceptable; fixed shebang is stricter) |
| **2** | IFS control | Low | **Hardened** | `IFS=$'\n\t'` set early |
| **6** | Logging | Low | **No change needed** | stdout `[node-bootstrap]` kept (systemd journal); optional `logger` also used |
| **7** | sha256 stderr | Low | **No change needed** | Still `exit 1` on mismatch; `die()` also logs via `logger` / best-effort `/dev/kmsg` |

---

## Source of truth (builders)

| Script | Path |
|--------|------|
| Node start | `/root/ops/bloodstone-node-start.sh` → packaged as `start-node.sh` |
| Bootstrap | `/root/ops/bloodstone-node-install-bootstrap.sh` → packaged as `install-chain-bootstrap.sh` |
| ARM64 packager | `/root/build-bloodstone-node-arm64-package.sh` (copies ops scripts) |
| x86_64 packager | `/root/build-bloodstone-node-distribution.sh` (same) |

---

## Operator env overrides

```bash
# Custom seed peers (do not rely only on the two default IPs)
export BLOODSTONE_SEEDS="seed.example.org:17333 64.188.22.190:17333"
./start-node.sh

# Bootstrap URL / public root
export BLOODSTONE_PUBLIC_ROOT=https://bloodstone.rocks
export BLOODSTONE_CHAIN_BOOTSTRAP_URL=https://bloodstone.rocks/downloads/bloodstone-chain-bootstrap-latest.tar.gz

# Skip or force tip snapshot
export BLOODSTONE_SKIP_BOOTSTRAP=1
export BLOODSTONE_FORCE_BOOTSTRAP=1

# Custom datadir (e.g. USB SSD on Pi)
export BLOODSTONE_DATADIR=/mnt/ssd/bloodstone
```

---

## Verification (local)

```bash
# Conf must be mode 600 after first start
stat -c '%a %n' ~/.bloodstone/bloodstone.conf   # expect 600

# Package scripts include hardening
tar -xOf bloodstone-node-0.7.6-linux-aarch64.tar.gz \
  bloodstone-node-0.7.6-linux-aarch64/start-node.sh | grep 'chmod 600'
tar -xOf bloodstone-node-0.7.6-linux-aarch64.tar.gz \
  bloodstone-node-0.7.6-linux-aarch64/install-chain-bootstrap.sh | grep 'no-same-owner'
```

---

## Downloads

| Artifact | URL |
|----------|-----|
| ARM64 node 0.7.6 | https://bloodstone.rocks/downloads/bloodstone-node-0.7.6-linux-aarch64.tar.gz |
| Latest ARM64 alias | https://bloodstone.rocks/downloads/bloodstone-node-linux-aarch64-latest.tar.gz |
| GitHub raw | https://github.com/TheBloodStone/bloodstone/raw/release-downloads/bloodstone-node-0.7.6-linux-aarch64.tar.gz |

---

*Remediation implemented against the merged assessment (RPC conf mode 600, tar symlink/owner hardening, HTTPS curl, seed overrides). Low items accepted as-is or lightly hardened.*
