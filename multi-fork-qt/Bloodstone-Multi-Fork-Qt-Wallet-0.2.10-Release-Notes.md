# Bloodstone Multi-Fork Qt Wallet 0.2.10

**Released:** 2026-07-29

## Fix: use **all** seed peers (not a single “manual” peer)

### What was going wrong
Local daemons started by Multi-Fork Qt only wrote **one** `addnode=` line (the tip host `64.188.22.190`), and wrote it twice. In `getpeerinfo` that connection is labeled **`manual`** — that is Bitcoin Core’s name for addnode peers, not a separate network.

STONE has **two** official seeds (same list as bloodstone-qt / ops conf):

| Seed | Role |
|------|------|
| `64.188.22.190:17333` | Tip / always-on relay |
| `192.119.82.145:17333` | Second seed |

Wallets were not keeping both.

### Fix in 0.2.10
1. Catalog carries a **`public_peers`** list per coin (env: `STONE_PUBLIC_PEERS`, `AZURE_PUBLIC_PEERS`, …).
2. `ensure_conf` writes **one `addnode=` per seed** (no exclusive `connect=`).
3. STONE defaults to both seeds above; AZURE/LRGK keep their public seed on the correct P2P port.
4. STONE conf also sets `dnsseed=1` and `discover=1` so fixed-seed discovery can run alongside addnodes.
5. Overview / tooltips list **all** seeds, not only the first.

### After upgrade
1. Install **0.2.10**.
2. For each coin: **Stop daemon** once (or delete the managed conf under the MFQ datadir), then **Download & start daemon** / select the coin so conf is rewritten.
3. In the RPC console: `getpeerinfo` — expect seed addresses with `"connection_type": "manual"` for each addnode that is connected (plus any inbound/outbound peers learned from the network).

### Downloads
- https://bloodstone.rocks/downloads/bloodstone-multi-fork-qt-0.2.10-win64-setup.exe  
- https://bloodstone.rocks/downloads/bloodstone-multi-fork-qt-0.2.10-win64-portable.zip  
- https://bloodstone.rocks/downloads/bloodstone-multi-fork-qt-0.2.10-win64.exe  
- https://bloodstone.rocks/downloads/bloodstone-multi-fork-qt-0.2.10.tar.gz  
- https://bloodstone.rocks/downloads/Bloodstone-Multi-Fork-Qt-Wallet-0.2.10-Release-Notes.md  

### Also still in 0.2.9 lineage
- Daemons stay running when MFQ closes  
- Soft auto-restart + pid/RPC reattach  
- P2P / RPC port fallback on Windows  
