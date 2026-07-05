# Master Creator Key — Scope of Control

*July 2026 · Admin operations reference (downloads only — not chain-mesh anchored)*

---

## Short answer

The **Master Creator key** unlocks **write access on your coordinator VPS admin panel** — stratum, faucet, pool settings, local node patches, and fleet metadata for devices registered **with your pool**.

It does **not** remotely update the **entire Bloodstone network’s fleet**. Other operators’ nodes are unaffected unless they independently choose to pull patches from your coordinator’s downloads manifest.

---

## What it is (and is not)

The Master Creator key is **not** a blockchain key, wallet key, or mesh publish token. It is a **second admin unlock code** for the Bloodstone **miner-web admin panel**, layered on top of the normal admin password.

| Concept | Master Creator? |
|---------|-----------------|
| Admin password | No — that only opens the panel (mostly read-only) |
| Master Creator code | Yes — enables infrastructure writes |
| STONE wallet / private keys | No |
| Mesh publish token | No |
| On-chain governance | No |

Think of it as: **admin password = enter the building** · **Master Creator code = permission to change live infrastructure on the coordinator you operate**.

---

## What it controls

### Your coordinator / VPS fleet — **yes**

With Master Creator active in your admin session, you can change live infrastructure on **that coordinator**:

- Stratum ports, share difficulty, public VPS IP
- Faucet and pool payout settings
- **Live node patches** on the coordinator (`bloodstoned` hot OTA via upkeep)
- Publish patch bundles to `/downloads/` for nodes that pull from your coordinator
- Time Capsule archive/prune on that host

This is the VPS stack **you deployed and operate** — not a global network console.

### Devices in your pool registry — **partial**

The **Device fleet** panel edits rows in `device_fleet` on **your pool database** — phones, browsers, and Android rigs that **registered with your coordinator** (mobile-contribution / fleet check-in).

You can edit labels, addresses, workers, `creator_role`, admin notes, and related metadata.

You **cannot** remotely drive arbitrary hardware worldwide. You are editing registry metadata for devices that reported to **your** pool.

### The entire network’s fleet — **no**

Master Creator does **not** grant:

- Control over other operators’ VPSes, stratum pools, or nodes
- A global push to every Bloodstone miner or node
- On-chain governance or consensus parameter changes
- Access to wallets, mesh publish tokens, or third-party infrastructure

Other coordinators, solo miners, and nodes that never use your pool are **outside this scope**.

---

## Node patches — scope in detail

| Action | Scope |
|--------|--------|
| **Apply patch** (admin button) | This coordinator VPS only |
| **Auto-apply** (upkeep, `UPKEEP_ROLE=main`) | This coordinator VPS only |
| **Publish patch** to `/downloads/` | Makes the bundle **available** to any node configured to watch your coordinator’s manifest |
| **Forced update of all network nodes** | **Not supported** |

Patches are **opt-in pull** from your downloads server (`/api/node-patch/update` manifest), not a mandatory network-wide update. Any independent node operator must configure their own upkeep or watcher to consume your published bundles.

---

## Scope summary

| Scope | Master Creator control? |
|-------|-------------------------|
| Coordinator VPS you operate (stratum, faucet, local `bloodstoned`) | **Full** |
| Devices registered in your pool `device_fleet` DB | **Metadata edits only** |
| Other operators’ VPS / pool / nodes | **None** |
| Entire Bloodstone network fleet | **None** |
| On-chain / consensus | **None** |

---

## Discord-ready reply

> Master Creator unlocks admin on **your coordinator VPS** — stratum, faucet, pool settings, local node patches, and fleet metadata for devices registered **with your pool**. It does **not** remotely update the entire Bloodstone network’s fleet; other operators’ nodes are unaffected unless they independently pull patches from your coordinator’s downloads manifest.

---

## Related documents

- [Bloodstone Master Creator Key FAQ](Bloodstone-Master-Creator-Key-FAQ.md) — full unlock list, login flow, security notes

---

*Document version: 1.0 · July 2026 · Downloads only (not chain-mesh anchored)*