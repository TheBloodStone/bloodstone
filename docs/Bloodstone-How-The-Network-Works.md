# How the Bloodstone Network Works

*A plain-language guide for everyday users · July 2026 · Downloads only (not chain-mesh anchored)*

---

## The one-minute version

Bloodstone is a **shared digital ledger** (the blockchain). People who do math work called **mining** help add new pages to that ledger and can earn **STONE** coins. Separate computers and phones called **nodes** download the ledger and **check that every page is real** before trusting it.

Most people only need the **miner app** and a **payout address**. You tap Start, your phone does work for the **pool**, and rewards show up over time. You do **not** need to understand servers, ports, or blockchain engineering to mine.

Running a **node** on your phone is optional. It helps the network stay honest and can let your household mine through your own Wi‑Fi instead of a far-away server.

---

## Three kinds of participants

Think of the network like a town library and a gold-panning creek:

| Role | Plain English | Do you need this? |
|------|---------------|-------------------|
| **Miner** | Does math puzzles to help secure the network and earn coins | **Yes**, if you want to mine |
| **Node** | Keeps a copy of the ledger and checks new pages are valid | **Optional** — helpful, not required for basic mining |
| **Pool** | Groups many miners together, tracks work fairly, pays out rewards | **Yes** for phone mining today (the app connects you automatically) |

You can be a miner only, a node only, or both on the same phone.

---

## How mining works on your phone

1. You install the **Bloodstone miner** app (Android).
2. You paste your **STONE payout address** (where rewards should go).
3. You tap **Start mining**.
4. The app connects to the **pool** over the internet.
5. The pool sends **jobs** (small math tasks). Your phone runs them in the background.
6. When your phone finds a valid result (**share**), the pool records it.
7. Over time, accumulated shares translate into payouts according to pool rules.

You do **not** need to download the full blockchain just to mine in **pool mode**. The pool and network nodes elsewhere already know the current chain state.

**Solo mining** (harder, advanced) means your phone mines directly against your **own** synced node. The app will tell you to wait until chain download finishes — most beginners should stay on **pool mode**.

---

## What a “node” is (and why it matters)

A **node** is a copy of the Bloodstone program (`bloodstoned`) that:

- Downloads chain data (some or all of it, depending on mode)
- **Verifies** that blocks follow the rules
- Can **relay** information to other devices on your Wi‑Fi

Nodes are the network’s **fact-checkers**. If a server or app lied about balances or block height, a real node on your phone would catch it.

You choose how much storage and responsibility you want. The miner app calls this **Local node mode**.

---

## Local node modes — pick what fits your phone

| Mode | What it does | Storage (rough) | Best for |
|------|----------------|-----------------|----------|
| **LAN client** | No chain download on this phone. Mines through a **full node on your Wi‑Fi**. | Almost none | Extra phones in the house that just want to mine |
| **Pruned** | Small chain copy (~550 MB). Can **host** mining for other devices on your Wi‑Fi. | ~550 MB+ free | One phone helping the household without a huge download |
| **Full chain** | Complete blockchain. Strongest household host; peers to the wider network. | ~2 GB+ free | One plugged-in phone as the “home server” |
| **Consensus** | Validates the chain and participates as a **network peer**. **No mining hosting** for others. | ~550 MB+ free | Users who want to help secure the network without running a mining hub |
| **Consensus witness** | Lightest verifier — syncs and witnesses via outbound connections only. **No stratum, no inbound peers.** | ~550 MB+ free | Old or low-RAM phones that still want to help verify |
| **Mesh federation** | Pruned tip plus optional block backups across phones (disaster recovery helper). | ~550 MB+ plus backup space | Advanced users helping store redundant copies |

**Default for many phones:** start as **LAN client** or **pruned**. Upgrade to **full** on one dedicated home device if you want the whole family on local Wi‑Fi without relying on a distant VPS.

---

## A simple household setup

```text
┌─────────────────────────────────────────────────────────┐
│  Your home Wi‑Fi                                         │
│                                                          │
│   📱 Phone A (Full node)  ── hosts chain + LAN mining   │
│        ▲                                                 │
│        │  same Wi‑Fi                                     │
│   📱 Phone B (LAN client) ── mines through Phone A       │
│   📱 Phone C (LAN client) ── mines through Phone A       │
│                                                          │
└─────────────────────────────────────────────────────────┘
          │
          │  internet
          ▼
   🌐 Bloodstone pool  ──  tracks shares, pays rewards
```

**How to set this up:**

1. On **one** phone: set mode to **Full chain**, tap **Start full node**, wait for sync (keep app open, Wi‑Fi, plugged in).
2. On other phones: set mode to **LAN client**, start mining — they find Phone A automatically.
3. Everyone can still fall back to the **online pool** if the home node is busy or still syncing.

---

## What the central server (VPS) does today

Bloodstone still uses a **coordinator server** on the internet for practical jobs:

- **Pool** — connects miners, tracks shares, runs payouts
- **Chain sync helper** — when your phone has not finished downloading the chain, mining can use the pool while sync continues
- **Downloads & app updates** — miner APK, web UI updates, guides like this one
- **LAN registry** — helps phones on the same public IP find each other’s home nodes (optional)

As more people run **full nodes** and **consensus nodes** around the world, the network depends less on any single central machine. Your home full node is part of that decentralization path.

---

## Consensus-only nodes (witnessing without hosting miners)

**Consensus** and **Consensus witness** modes are for people who want to **help validate the network** without turning their phone into a mining server for the household.

- They **do** download and verify chain data.
- They **do not** offer LAN stratum (the mining port other rigs use).
- To mine on the same phone, use **pool mode** or point at another **full node** on your Wi‑Fi.

Think of it as volunteering as a **juror** who reads the evidence, not as a **workshop** that supplies tools to other miners.

---

## Staying safe and getting good results

- **Use a real payout address** you control. The app never needs your private keys for pool mining.
- **Stay on Wi‑Fi** for chain download and big updates; cellular data can be expensive.
- **Plug in and disable battery saver** for the miner app while syncing a node — downloads take time and Android may kill background work.
- **Free storage:** full node needs more space; pruned and consensus modes need less but still need hundreds of MB free.
- **Updates:** the miner screen can refresh over Wi‑Fi without reinstalling the APK; install new APK versions from **Downloads** when offered for native fixes.

---

## Words you might see (translated)

| Term | What it means in everyday language |
|------|-------------------------------------|
| **Blockchain / chain** | The shared ledger of all confirmed transactions and blocks |
| **Block** | One page of the ledger, added on a schedule |
| **Sync / chain download** | Your node catching up with the latest pages |
| **Pool** | A service that combines many miners and splits rewards fairly |
| **Stratum** | The mining “job line” your app connects to (local or on the pool) |
| **LAN** | Your home Wi‑Fi network |
| **Pruned** | A shortened chain copy — enough to validate recent history, less disk space |
| **Full node** | A complete chain copy and network peer |
| **Witness / consensus** | Checking that blocks are valid without hosting others’ mining |
| **VPS** | A computer on the internet that runs the public pool and helpers today |
| **OTA update** | New miner screens downloaded inside the app without a full reinstall |

---

## Quick choices — “what should I use?”

| Your goal | Suggested setting |
|-----------|-------------------|
| I just want to mine on one phone | Pool mode · **LAN client** or **pruned** · tap Start |
| I want my family to mine on home Wi‑Fi | **Full node** on one plugged-in phone · **LAN client** on the rest |
| I want to help the network, not host miners | **Consensus** or **Consensus witness** |
| I have very little storage | **LAN client** (no local chain) or mine pool-only without starting a node |
| I want backups if a server goes offline | **Mesh federation** (advanced) |

---

## Where to get the app and more help

- **Downloads:** [bloodstonewallet.mytunnel.org/downloads/](https://bloodstonewallet.mytunnel.org/downloads/)
- **Miner (online):** [bloodstonewallet.mytunnel.org/mining/mine](https://bloodstonewallet.mytunnel.org/mining/mine)
- **Related guides on Downloads:** Master Creator FAQ, chain mesh capacity FAQ (for advanced storage topics)

---

*Document version: 1.0 · July 2026 · For everyday users — not engineering spec · Downloads only (not chain-mesh anchored)*