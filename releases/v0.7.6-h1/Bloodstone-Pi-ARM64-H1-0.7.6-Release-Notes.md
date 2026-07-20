# Bloodstone Raspberry Pi / Linux ARM64 — H1 packages

**Date:** 2026-07-20  
**Node version:** **0.7.6** (Phase H1 timewarp, activation height **H = 17000**)  
**Pi miner package:** **1.2.0**

## Downloads

### Full node (headless) — ARM64 / Pi 4–5 64-bit
- https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-0.7.6-linux-aarch64.tar.gz
- Latest alias: https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-linux-aarch64-latest.tar.gz
- SHA256: see `.sha256` sidecar

### Standalone Yespower STONE miner (Pi + Linux)
- https://bloodstonewallet.mytunnel.org/downloads/bloodstone-pi-stone-miner-1.2.0.tar.gz
- Latest: https://bloodstonewallet.mytunnel.org/downloads/bloodstone-pi-stone-miner-latest.tar.gz
- One-liner: `curl -fsSL https://bloodstonewallet.mytunnel.org/downloads/install-bloodstone-pi-miner.sh | sudo bash`

## Install node (Pi)

```bash
curl -fsSLO https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-0.7.6-linux-aarch64.tar.gz
tar -xzf bloodstone-node-0.7.6-linux-aarch64.tar.gz
cd bloodstone-node-0.7.6-linux-aarch64
./start-node.sh
./bin/bloodstone-cli -getinfo   # expect 0.7.6
```

Do **not** wipe `~/.bloodstone` when upgrading.

## Notes
- Binaries are native **Linux aarch64** (not Android).
- H1 applies to **full nodes** (headers ≥ 17000). Pool miners need a 0.7.6+ upstream node.
- Pi full-node **Qt GUI** ARM64 rebuild may follow; headless node is enough for consensus/mining backend.
