# Bloodstone Master Creator Key — FAQ

*July 2026 · Admin panel reference (downloads only — not chain-mesh anchored)*

---

## What is it?

The **Master Creator key** is **not** a blockchain key, wallet key, or mesh publish token. It is a **second admin unlock code** for the Bloodstone **miner-web admin panel** — layered on top of the normal admin password.

Think of it as: **admin password = enter the building** · **Master Creator code = permission to change live infrastructure**.

---

## Two-step admin access

| Step | What you enter | What you get |
|------|----------------|--------------|
| **1. Admin password** | Standard admin login | Access to the admin panel (mostly **read-only**) |
| **2. Master Creator code** | Separate access code | **Write access** to fleet and infrastructure settings |

You can enter the Master Creator code at login, or unlock it later from the **Master Creator** panel on the admin page.

---

## What Master Creator unlocks

When **Master Creator is active** in your session, you can:

### 1. Edit device fleet

Registered miners in `device_fleet` (pool database):

- STONE address, worker name, algo
- Model, miner kind (browser / android / ios), transport
- Display name, creator role, admin notes

### 2. Save fleet admin overrides

Panel field overrides stored in the pool DB (separate from the main settings form).

### 3. Save all service settings

Including:

- **Faucet** — claim amount, cooldown min/max, minimum faucet balance
- **Pool payout** — payout chunk limits
- **Stratum** — VPS IP, ports (neoscrypt, yespower, sha256d)
- **Share difficulty** — per-algo floors, GPU vardiff ceilings
- **ROD merge block difficulty** mode for SHA256d
- **Restart stratum** on save when ports or difficulty change

Without Master Creator, these fields are **disabled** and **Save all settings** does not apply changes.

### 4. Live node patches (hot OTA)

- Apply patch bundles without stopping `bloodstoned`
- Publish patches to `/downloads/` for fleet auto-update
- Trigger check-and-apply for published patches

### 5. Time Capsule controls

Archive-to-mesh and optional local prune UI (shown only when Master Creator is active).

---

## What it does *not* do

| Not this | Why |
|----------|-----|
| STONE wallet / private keys | Unrelated — admin web session only |
| Mesh publish token | Separate credential (`CHAIN_MESH_PUBLISH_TOKEN`) |
| On-chain governance | No consensus or coin-parameter control |
| Chain Mesh file access | Does not grant mesh upload by itself |

Master Creator is **VPS operations control**: pool, faucet, stratum, fleet, and node patch management.

---

## Without Master Creator

- You can still **log in as admin** and **view** settings, fleet devices, pool status, and generators.
- Faucet, stratum, and payout fields appear **read-only** (greyed out).
- Fleet device edit forms and save buttons are hidden or blocked.
- Node patch and Time Capsule write actions are unavailable.

---

## Where the code is stored

- Hashed with **scrypt** in `bloodstone-miner-web/secrets.conf` as `master_creator_code_hash`
- Never stored in plaintext on disk after initial setup
- Optional env preset: `MASTER_CREATOR_CODE` on first boot
- If unset, system auto-generates e.g. `MASTER-CREATOR-A1B2C3D4` once and flashes it in the admin UI (**save it immediately**)

---

## How to unlock

**At login:**

```
/admin/login → password + optional Master Creator access code
```

**After login:**

```
/admin → Master Creator panel → enter access code → Unlock fleet admin
```

**End session:**

```
End edit access (Master Creator logout) — admin login remains until full logout
```

---

## Security notes

- Treat the Master Creator code like a **root operations password** — separate from the admin password.
- Rotate if compromised: update `master_creator_code_hash` in `secrets.conf` or set a new `MASTER_CREATOR_CODE` before first hash is written.
- Master Creator does not bypass mesh partner token requirements for external `assets/blurt/` publish APIs.

---

## Quick reference

| Question | Answer |
|----------|--------|
| Blockchain key? | **No** |
| Needed to view admin? | **No** — admin password only |
| Needed to change stratum/faucet? | **Yes** |
| Needed to edit fleet devices? | **Yes** |
| Same as mesh publish token? | **No** |

---

*Document version: 1.0 · July 2026 · Downloads only (not chain-mesh anchored)*