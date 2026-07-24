# Phase H1 — node / miner inventory snapshot

**Snapshot time:** 2026-07-23 ~22:25 UTC  
**Chain tip:** **15042**  
**H:** **17000** (**1958** blocks left)  
**ETA *H*:** **~2026-07-29 08:00–16:00 UTC** (see `h1-boundary-status.json` for live)

This is an **ops inventory**, not a complete census of every wallet user. Re-run `getpeerinfo` + pool dashboard before any final go/no-go.

---

## 1. Countdown

| Metric | Value |
|--------|-------|
| Freeze tip (docs) | ~13869 (2026-07-20) |
| Tip now | **15042** |
| Blocks since freeze | ~1173 |
| Blocks to *H* | **1958** |
| Observed rate | ~341–360 blocks/day (~240–253 s/block) |
| Wall-clock left | **~5.4–5.7 days** |
| ETA band | **2026-07-29 UTC** (morning–afternoon) |

---

## 2. Full nodes (P2P peers seen from primary `64.188.22.190`)

**20 peers** at snapshot; subversion histogram:

| Subversion | Count | H1-ready? |
|------------|------:|-----------|
| `/Bloodstone:0.7.6/` | **11** | Yes (has H1 gate in 0.7.6-h1 line) |
| `/Bloodstone:0.7.4/` | **5** | **No** |
| `/Bloodstone:0.7.2/` | **3** | **No** |
| `/Bloodstone:0.7.0/` | **1** | **No** |

### Notable hosts

| Addr / role | Subver | Notes |
|-------------|--------|-------|
| **Primary VPS** `64.188.22.190` (this host) | `/Bloodstone:0.7.6/` | Running `/root/bloodstone-core/src/bloodstoned`; SHA256 `58d0f35ba9f9e10c34acf9c2e651199b6a7593859dd8762f9e81e89472ef4fe9`; H1 markers present |
| **LRGK worker** `192.119.82.145` | `/Bloodstone:0.7.6/` | **RESOLVED 2026-07-23** — upgraded; binary SHA **matches primary**; strata restarted. Ricardo: **no miners on LRGK yet** (template path theoretical) |
| `185.190.56.235` | `0.7.4` | Soft residual only — full-relay peer; **no public STONE stratum**; possible offline solo-GBT (low impact @ ~250 s/block) |
| `107.205.210.9` | `0.7.0` | **Pool-client** — mines to **our** stratum (primary templates); own version irrelevant to validity |
| `97.149.216.154` | `0.7.6` | Also mining to pool (stratum ESTAB) |
| `185.32.162.191` | `0.7.6` | |
| `207.177.142.232` | mix **0.7.6 + 0.7.4** | **Pool-client** — hashrate to our pool; residual 0.7.4 process not a public template host |

**Federation roster (coordinators):**

| ID | Base | P2P | Roles |
|----|------|-----|-------|
| coord-a-primary | bloodstonewallet.mytunnel.org | 64.188.22.190:17333 | witness, status, downloads, catalog, pool, electrumx |
| coord-b-lrgk-01 | LRGK.mytunnel.org | 192.119.82.145:17333 | witness, status (**bloodstoned 0.7.6** — upgraded) |
| coord-lab-witness-01 | (lab) | — | witness |

---

## 3. Three mining lanes (pool stratum on primary)

| Lane | Algo | Port | Connected (TCP ESTAB @ snap) | Template host risk |
|------|------|-----:|-----------------------------:|--------------------|
| **SHA256d** (Bitaxe / aux) | sha256d | **3429** | 3 | Primary + LRGK both **0.7.6**; live finds on **primary** path |
| **Neoscrypt** | neoscrypt-xaya | **3437** | 3 | same |
| **Yespower R16** | yespower | **3438** | 5 | same |

**Recent block finds (pool dashboard):** essentially **all recent tips are sha256d pool finds** from:

- `SeaYqqAjsyMQDhWumL3GRXR9EiA4hpWJRa` (workers Goodaxe / Goodaxe2 / …)
- `SiL1NKaAtfQ5AVckXohBx9AvMjZaCfCGF2` (worker gamma)

So **current hashrate that lands blocks is almost entirely pool-template path on primary** — good **if** primary stays 0.7.6-h1 and **no** competing old solo/external templates after H.

---

## 4. Pool miners / workers (active or recent)

`miners_with_balance`: **26** addresses (many idle).  
**Active / recent hashrate set (~5):**

| Address | Connected | Lanes seen | Notes |
|---------|-----------|------------|-------|
| `SeaYqqAjsyMQDhWumL3GRXR9EiA4hpWJRa` | yes | neo + sha256d + yespower | Dominant multi-worker (Bitaxe, laptop, android, browser) |
| `SiL1NKaAtfQ5AVckXohBx9AvMjZaCfCGF2` | yes | sha256d | ASIC gamma — frequent finder |
| `SZ1tRscaJGjBwhwWhmqjH23X5pj791Z8ox` | yes | neo + yespower | GPU-class |
| `SPCvEJ1LowL4eBEgUoMPcCmGqketX1pMVK` | partial | yespower | browser + android |
| `Sh9vSHEFEvhGdA7Dd4uRYgh8p23oNbyReq` | partial | yespower | android |

**Pool-only workers do not need their own 0.7.6 node** as long as they never solo-mine with an old daemon.

---

## 5. Cexius

| Item | Status |
|------|--------|
| Gate / H in `v0.7.6-h1` | Confirmed **H=17000** |
| Public “good to go” note | Published (2026-07-20) |
| **Main-chain tip hash verified?** | **YES** — closed 2026-07-24 (see below) |
| On-chain deposit tracking | Addresses + user flows only (exchange deposits) |

### 5.1 Main-chain verification (2026-07-24)

Cexius reported:

```text
getbestblockhash = 5ef86bdde748942ba1b93e544425766d35818896fa18578f18c2f73d2a08dbe8
```

Primary (`64.188.22.190`) check:

```bash
bloodstone-cli getblock 5ef86bdde748942ba1b93e544425766d35818896fa18578f18c2f73d2a08dbe8 1
```

| Field | Primary result |
|-------|----------------|
| **Found** | yes |
| **height** | **15133** |
| **confirmations** | **21** (≥ 1 → **same main chain**) |
| previousblockhash | `2e345cf968f8eb7964fe1d454d5733bece3836d0fc97d4df668d721627707df8` |
| nextblockhash | `b92f7a5282b77ebff2b59b73dcd0c80cba67aaf7da66da57f454b2cce73989a3` |
| pow | sha256d merge-mined (auxpow present) |
| Primary tip at verify | height **15153** (hash moved past 15133 as expected) |

**Decision:** confirmations **21** ≫ 1 → **same main chain as primary**.  
**Cexius chain alignment: FULLY VERIFIED — item closed.**  
No fork / no “block not found”. Height they held will keep moving; lookup is by **hash**, not a fixed tip height.

Published package binary SHA (x86_64 tarball `bin/bloodstoned`) for operators still comparing binaries:  
`269c5d2de4432865ab224394d6d35efb306456d4e887471af73563f21c953978`  
Tarball SHA256: `48c1c394d9c4bc239a535079a40bbde8fdfea98fadb9d72511be421c334e746f`

---

## 6. Go / no-go on H=17000 (updated 2026-07-24)

**Canonical register:** [Phase-H1-GO-Register-2026-07-26.md](Phase-H1-GO-Register-2026-07-26.md)

| Signal | Observation | Status |
|--------|-------------|--------|
| Block production | Almost all via **primary pool** on **0.7.6** | GREEN |
| LRGK `192.119.82.145` | **0.7.6**, SHA matches primary, strata restarted; **no miners yet** | **RESOLVED** (not a live blocker) |
| Sub-0.7.6 peers | Of remaining lag IPs: **two mine to our pool** (templates = primary 0.7.6); **185.190** soft residual only | **Not a re-tag trigger** |
| Cexius | Tip hash on main chain (conf=21 @ h=15133) | **CLOSED** |
| NTP / clock | Primary **verified synchronized** (offset ~ms); LRGK NTP **receipt still required** | **Only open ops item before 26th** |

### Four criteria for the 26th

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Primary template host 0.7.6-h1 | **GREEN** |
| 2 | LRGK bloodstoned 0.7.6-h1 | **GREEN** |
| 3 | Cexius same main chain | **GREEN** |
| 4 | No live foreign STONE templates &lt; H1 | **GREEN** |

**Live blockers: none.** One small unquantified residual (185.190 offline solo-GBT) — low impact (window rule cannot fire at ~250 s/block; stray block orphans).

### Recommendation (ops correction)

**Intend GO on H=17000 at the 26 Jul checkpoint** after **LRGK NTP/clock receipt** is logged (primary NTP already closed 2026-07-24).  
Do **not** re-open LRGK or “lagging miners” as no-go items — that framing is **stale**.

**Crossing (staffed):** ~**20:42 NZST 29 Jul** through ~**04:00 NZST 30 Jul** (use live ETA from `h1-boundary-status.json`).  
**+24–48 h post-activation:** health check-in.  
**§15.1 vault gate:** discharge **only after** H1 is active on the network (not at GO-decision; see GO register).

---

## 7. NTP / clock (honest failure mode)

Post-H future bound **1800 s** — a **&gt;30 min fast** clock on a template host is the most plausible honest failure at the boundary.

| Host | Check (2026-07-24) | Result |
|------|--------------------|--------|
| **Primary** | `timedatectl`: NTP=yes, **NTPSynchronized=yes**; timesyncd → ntp.ubuntu.com; offset **~+1.4 ms** | **CLOSED** |
| **LRGK** | Needs Ricardo/ops: `timedatectl status` / `chronyc tracking` showing synchronized | **OPEN — close before 26 Jul** |

---

## 8. Watcher + crossing watch

- Service: `bloodstone-h1-boundary-watch.timer` (every 2 min)  
- Log: `/var/log/bloodstone/h1-boundary-watch.log`  
- State: `/var/lib/bloodstone/h1-watch/status.json` + `ALERT` when ≤500 blocks  
- Public: https://bloodstonewallet.mytunnel.org/downloads/h1-boundary-status.json  
- **Staffed window:** NZ evening 29 Jul → early 30 Jul (align to rolling UTC ETA)
