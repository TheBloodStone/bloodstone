# Bloodstone v0.7.6 — Phase H1 release assets

**Flag-day activation height:** `H = 17000`  
**Consensus version:** bloodstoned / Qt **0.7.6**  
**Portal downloads:** https://bloodstonewallet.mytunnel.org/downloads/

## Binaries in this folder

| Asset | Platform | Role |
|-------|----------|------|
| `bloodstone-node-0.7.6-h1-timewarp-linux-x86_64.tar.gz` | Linux x86_64 | Headless node + CLI (exchanges / VPS) |
| `bloodstone-node-0.7.6-linux-aarch64.tar.gz` | Linux ARM64 / Raspberry Pi | Headless node + CLI |
| `bloodstone-qt-0.7.6-win64.exe` | Windows x64 | Core Qt wallet (GUI full node) |
| `bloodstone-wallet-0.7.6-win64.zip` | Windows x64 | Qt + bloodstoned + cli + wallet tool |
| `bloodstone-miner-android-1.3.94.apk` | Android arm64 + armv7 | Miner app with embedded full node 0.7.6 |
| `bloodstone-pi-stone-miner-1.2.0.tar.gz` | Pi / Linux | Standalone yespower STONE miner |

Each binary has a matching `.sha256` sidecar.

## Docs

- `Phase-H1-Who-Must-Upgrade.md`
- `Phase-H1-Grandfathering-Activation-Height.md`
- `Phase-H1-Cexius-Good-To-Go.md`
- Platform release notes in this folder

## Source

Core H1 consensus tree is under `/core` in this repository (`nH1TimewarpActivationHeight = 17000`).

## Verify

```bash
sha256sum -c bloodstone-node-0.7.6-h1-timewarp-linux-x86_64.tar.gz.sha256
```
