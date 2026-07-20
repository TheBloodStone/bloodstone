# Phase H1 — Who must upgrade? (Qt wallets, web, exchanges)

**Flag-day activation height *H* = 17000**  
**Package:** Bloodstone Core **v0.7.6** (or later)  
**Not a relaunch** — same chain, balances, and deposit addresses. Do **not** wipe `blocks/` / `chainstate/`.

H1 only changes **how full nodes validate new headers** at and after height 17000 (DGW window-min reject + 30‑minute future stamp). History below 17000 is grandfathered.

---

## Quick answer

| You are… | Need upgrade before **17000**? |
|----------|--------------------------------|
| **Exchange / pool / self-hosted full node** (`bloodstoned`) | **Yes** — required |
| **Core Qt wallet that runs a local full node** (ships `bloodstoned` + `bloodstone-qt`) | **Yes** — upgrade the full package so the embedded node matches consensus |
| **Wallet & Node GUI / Node GUI** that downloads and runs `bloodstoned` | **Yes** — get a current node binary (auto-download or install v0.7.6+) |
| **Android miner / Pi full node** validating mainnet | **Yes** if the on-device/on-Pi daemon is a full node (update when a matching H1 package/APK ships) |
| **Web wallet only** (`bloodstonewallet.mytunnel.org/wallet`) | **No** — operators upgrade the server node; you keep using the site |
| **Watch-only / keys only / RPC to someone else’s upgraded node** | **No special wallet migration** — rely on that upgraded node |
| **Cexius / listing deposit nodes** | **Yes** — public package, upgrade before *H* |

---

## Setup detail (operators and full-node wallets)

### 1. Full node (`bloodstoned` / exchange package)

1. Install **v0.7.6** (or later) `bloodstoned` + `bloodstone-cli`.  
2. Restart the node.  
3. Confirm version **0.7.6** (or later) and tip advances.  
4. **Do not** delete datadir (not a relaunch).  
5. Confirm **NTP / clock sync** (post-*H* future bound is 1800s).  

**Linux package:**  
https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-0.7.6-h1-timewarp-linux-x86_64.tar.gz  

**SHA256:** `48c1c394d9c4bc239a535079a40bbde8fdfea98fadb9d72511be421c334e746f`  

### 2. Core Qt (full-node wallet)

Bloodstone **Core Qt** packages typically include **daemon + Qt**. If you mine, validate, or keep a local chain with Qt:

- Prefer a **matching H1-era node** (v0.7.6+) before height 17000.  
- If your installed Qt is older but still points at a **local** `bloodstoned`, upgrade that daemon (or the whole package).  
- If your Qt only talks to a **remote** upgraded RPC, urgency is lower, but matching versions still avoid surprises.

Downloads index: [Core Qt wallet section](https://bloodstonewallet.mytunnel.org/downloads/#core-qt) · [node package](https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-0.7.6-h1-timewarp-linux-x86_64.tar.gz)

### 3. Web wallet users

No Qt install required. Sign up / receive / send via the web wallet as usual. Server operators already run the upgraded chain software.

### 4. What changes at height 17000 (full nodes only)

| Rule | Before *H* | At/after *H* |
|------|------------|--------------|
| Same-algo DGW window min | off | reject `timewarp-dgw-window` |
| Future stamp vs network time | 7200 s | 1800 s |

### 5. What does **not** change

- Genesis / chain identity  
- Deposit addresses and balances  
- No forced rebrand or new ticker  
- Vault bit-5 is **not** in this release  

---

## Links

- Cexius good-to-go: [Phase-H1-Cexius-Good-To-Go.md](Phase-H1-Cexius-Good-To-Go.md)  
- Activation height: [Phase-H1-Grandfathering-Activation-Height.md](Phase-H1-Grandfathering-Activation-Height.md)  
- Freeze confirm: [Phase-H1-Freeze-Confirm.md](Phase-H1-Freeze-Confirm.md)  
