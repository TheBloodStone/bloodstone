# LRGK — Lil Raghnok Goblin Coin (independent chain)

**Open source.** Public source of truth for the LRGK full-node consensus tree.

| Field | Value |
|-------|--------|
| Ticker | **LRGK** |
| Name | Lil Raghnok Goblin Coin |
| Fork ID | `e9d304f3379e96859acd131f` |
| Network salt | `cc7779f7600b0402083c7e8e8a2fcb89` |
| Magic | `cab95753` |
| P2P | **33685** |
| RPC | **53685** (localhost only on public seed) |
| Datadir | `.lrgk` |
| Binaries | `lrgkd`, `lrgk-cli` |
| bech32 HRP | `lrgk` |
| Public seed | `64.188.22.190:33685` |
| Parent template | Bloodstone core (independent consensus — **not** STONE) |

## Source of truth

- **This repository / tree** is the public codebase for LRGK.
- Ops host may pull builds from here; VPS-only closed source is **not** the product direction.
- Registry entry: [fork-registry/coins/LRGK](../fork-registry/coins/LRGK/) (monorepo layout) or sibling `bloodstone-fork-registry`.

## Build (Linux)

```bash
./autogen.sh
./configure --disable-tests --without-gui --disable-bench
make -j"$(nproc)"
# binaries: src/lrgkd src/lrgk-cli  (names may still follow template until rebrand pass)
```

Or use the packaged builder on the ops host:

```bash
/root/lrgk-chain/build-lrgk-daemon.sh
```

## Run

```bash
mkdir -p ~/.lrgk
cp lrgk.conf.example ~/.lrgk/lrgk.conf
# set rpcpassword; add: addnode=64.188.22.190:33685
./src/lrgkd -datadir="$HOME/.lrgk" -conf="$HOME/.lrgk/lrgk.conf"
```

## Downloads & docs

- Peer doc: https://bloodstone.rocks/downloads/LRGK-Public-Peer.md
- Node packages: https://bloodstone.rocks/downloads/lrgk/
- Source tarball: https://bloodstone.rocks/downloads/lrgk/lrgk-core-source-latest.tar.gz
- Fork Lab store: https://bloodstone.rocks/fork-lab/store/
- Parent monorepo: https://github.com/Bloodstone-Team/bloodstone

## License

MIT / Bitcoin Core heritage — see `COPYING`.

Doc version: 1.0.0 · Prepared: 20260801T0810Z UTC
