# How do I become a Bloodstone witness? — FAQ

*July 2026 · Everyday users & Discord · downloads only (not chain-mesh anchored)*

---

## Short answer

**Install the Bloodstone miner app → set Local node mode to Consensus or Consensus witness → start the node → stay online.**

There is **no election**, **no stake vote**, and **no paid office**. A Bloodstone witness is a **node that verifies the chain and attests to the tip it sees** (for the network and QUASAR defense).

---

## What “witness” means on Bloodstone

| Term | Meaning |
|------|---------|
| **Consensus / Consensus witness** | App modes that validate the blockchain without hosting LAN mining for others |
| **Mesh witness capsule** | A signed “I saw this tip at this height” message used by QUASAR / exchanges |
| **Not Hive/Blurt witness** | Bloodstone is **not** DPoS — you do not get voted into a producer schedule |

Witnesses **observe and verify**. Miners **produce blocks**. Different roles.

---

## What you need

1. **Android phone** (or a desktop full node — see below)
2. **Wi‑Fi** for the first sync (cellular works but can be expensive)
3. **~550 MB free** for Consensus / Consensus witness (more for Full chain)
4. **Power** — plug in, disable battery saver for the miner app while syncing
5. A **STONE address** you control (payout / identity — not a “witness bond”)

---

## Phone steps (exact menu names)

1. **Download the app**  
   [https://bloodstonewallet.mytunnel.org/downloads/](https://bloodstonewallet.mytunnel.org/downloads/)  
   Install the latest **Bloodstone miner Android** APK.

2. **Open the miner** and set your **STONE payout address** (wallet you control).

3. Find **Local node mode** (dropdown `local-node-mode-select` on the miner screen).

4. Choose one of:
   - **`Consensus — validate chain + P2P witness (~550 MiB, no stratum)`**  
     Best everyday witness: validates blocks and peers; no LAN mining host.
   - **`Consensus witness — lightweight witness only (no stratum, no inbound P2P)`**  
     Lightest option for older / low-RAM phones: outbound sync only.
   - **`Full chain — host for household (needs ~2 GB free)`**  
     Strongest peer + can host household miners (bonus; not required just to witness).

5. Tap the start button — the label matches your mode:
   - **Start consensus node**
   - **Start witness node**
   - **Start full node**

6. **Wait for chain sync** (Wi‑Fi, plugged in, keep the app open / allow background when prompted).

7. **Stay online** when you can. Your node verifies blocks; full/pruned phones and the coordinator also emit **witness capsules** used by `/api/quasar/status`.

8. **Optional mining:** use **Pool mode** (or a household full node). Consensus modes do **not** offer LAN stratum for other devices.

---

## Mode cheat sheet

| Goal | Local node mode | Start button |
|------|-----------------|--------------|
| Help verify, low resources | **Consensus witness** | **Start witness node** |
| Help verify + P2P peer | **Consensus** | **Start consensus node** |
| Home hub + witness | **Full chain** | **Start full node** |
| Only mine, no local chain | **LAN client** | (no node start) |
| Light host for household | **Pruned** | **Start pruned node** |

---

## Desktop / VPS (stronger witness)

1. Download **bloodstone-qt** or a **node package** from Downloads.
2. Prefer the **full chain bootstrap** so you are not stuck mid-sync.
3. Run the node, open firewall **TCP 17333** (P2P), stay near tip.
4. Optionally run coordinator-style tooling that submits capsules to  
   `POST /api/quasar/witness/submit` (advanced operators).

---

## What you do *not* need

| Not required | Why |
|--------------|-----|
| Stake / bond | No DPoS witness deposit |
| Votes / “vote for me” posts | Not elected |
| Special admin key | Master Creator is VPS ops only — unrelated |
| Hosting miners for others | Consensus modes deliberately skip LAN stratum |
| Paying STONE for the title | Witness = run software that verifies |

---

## How the network uses witnesses

- **QUASAR L4** — mesh witness capsules (`bloodstone/witness-capsule/v1`) under `assets/witness/…`
- **Exchange policy** — when quorum is low or tips split, recommended deposit confirmations rise (or halt)
- **Status API** — [https://bloodstonewallet.mytunnel.org/api/quasar/status](https://bloodstonewallet.mytunnel.org/api/quasar/status)

More detail: [Bloodstone-QUASAR-Witness-Aware-Confirmation-Guide.md](Bloodstone-QUASAR-Witness-Aware-Confirmation-Guide.md) · portal [QUASAR](https://bloodstonewallet.mytunnel.org/quasar/)

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Sync stuck / low height | Stay on Wi‑Fi; plug in; update APK; try bootstrap on desktop Qt |
| App killed in background | Disable battery optimization for Bloodstone; keep screen on while first syncing |
| “No storage” | Free ~550 MB+ or use **LAN client** + someone else’s full node |
| Want to mine too | Mine **Pool** while Consensus/Witness node runs, or use a household **Full** node |
| Confused with Blurt witness | Different network model — Bloodstone has no witness election |

---

## Related links

| Resource | URL |
|----------|-----|
| Downloads | https://bloodstonewallet.mytunnel.org/downloads/ |
| How the network works | Bloodstone-How-The-Network-Works.md |
| QUASAR | https://bloodstonewallet.mytunnel.org/quasar/ |
| Discord paste (copy/paste) | Bloodstone-Become-A-Witness-Discord-Paste.txt |
| Data sales (STONE) | https://bloodstonewallet.mytunnel.org/data/ |

---

*Bloodstone · Become a Witness FAQ v1.0 · July 2026*
