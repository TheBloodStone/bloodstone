# AZURE — Azure Guardian Coin (independent chain)

**Open source.** Public source of truth for the AZURE full-node consensus tree.

| Field | Value |
|-------|--------|
| Ticker | **AZURE** |
| Name | Azure Guardian Coin |
| Fork ID | `7e177be306a616364771bf4c` |
| Network salt | `91efe9226b8fd785f7c7c69d807b1d50` |
| Magic | `a3d2463e` |
| P2P | **29825** |
| RPC | **49825** (localhost only on public seed) |
| Datadir | `.azure` |
| Binaries | `azured`, `azure-cli` |
| Public seed | `64.188.22.190:29825` |
| Premine | 5,000,000 AZURE (spendable) · `AHn1Kf6kkYGua1cETaqtug2ukEd4iqURHM` |
| Parent template | Bloodstone core (independent consensus — **not** STONE, **not** LRGK) |

## Source of truth

- **This repository / tree** is the public codebase for AZURE.
- Registry entry: [fork-registry/coins/AZURE](../fork-registry/coins/AZURE/).

## Build (Linux)

```bash
./autogen.sh
./configure --disable-tests --without-gui --disable-bench
make -j"$(nproc)"
```

Ops builder (when present):

```bash
/root/azure-chain/build-azure-daemon.sh
```

## Run

```bash
mkdir -p ~/.azure
cp azure.conf.example ~/.azure/azure.conf
# set rpcpassword; add: addnode=64.188.22.190:29825
./src/azured -datadir="$HOME/.azure" -conf="$HOME/.azure/azure.conf"
```

## Downloads & docs

- Peer doc: https://bloodstone.rocks/downloads/AZURE-Public-Peer.md
- Node packages: https://bloodstone.rocks/downloads/azure/
- Source tarball: https://bloodstone.rocks/downloads/azure/azure-core-source-latest.tar.gz
- Fork Lab: https://bloodstone.rocks/fork-lab/
- Parent monorepo: https://github.com/Bloodstone-Team/bloodstone

## License

MIT / Bitcoin Core heritage — see `COPYING`.

Doc version: 1.0.0 · Prepared: 20260801T0810Z UTC
