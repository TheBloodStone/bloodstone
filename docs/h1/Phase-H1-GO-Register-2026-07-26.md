# Phase H1 — GO register (checkpoint 2026-07-26)

**Status as of 2026-07-24 (ops update):** ready for **GO on 26th** once **NTP/clock on LRGK** is receipted.  
**H:** 17000 · **path:** flag-day (not re-tag)  
**Crossing band (staffed):** ~**20:42 NZST 29 Jul** through ~**04:00 NZST 30 Jul** (see live `h1-boundary-status.json` for rolling ETA UTC).

---

## Four criteria — accurate register

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | **Primary template host ≥ 0.7.6-h1** | **GREEN** | `/Bloodstone:0.7.6/`; binary SHA `58d0f35ba9f9e10c34acf9c2e651199b6a7593859dd8762f9e81e89472ef4fe9`; H1 markers present |
| 2 | **LRGK bloodstoned ≥ 0.7.6-h1** | **GREEN (resolved)** | Upgraded 2026-07-23; P2P subver `/Bloodstone:0.7.6/`; same binary SHA as primary; strata restarted. Ricardo: **no miners on LRGK yet** — template path theoretical, not live hashrate |
| 3 | **Cexius on same main chain** | **GREEN (closed)** | `getbestblockhash` `5ef86bdd…` → primary `getblock` height **15133**, **confirmations 21** (2026-07-24) |
| 4 | **No live foreign STONE template host &lt; H1** | **GREEN** | Peer triage: sub-0.7.6 IPs are pool-clients or soft residual (185.190); no open foreign 3429/3437/3438 |

**Live blocker count:** **0**  
**Small unquantified residual:** 185.190.56.235 possible offline solo-GBT (0.7.4) — low impact at ~250 s/block (window rule cannot fire; stray block orphans).

---

## NTP / clock (honest failure mode at H)

Post-H `MAX_FUTURE_BLOCK_TIME` = **1800 s**. A template host **&gt; ~30 min fast** stamps blocks peers reject.

| Host | NTP / clock | Status |
|------|-------------|--------|
| **Primary** `64.188.22.190` | `System clock synchronized: yes`; NTP service active (systemd-timesyncd → ntp.ubuntu.com); offset ~**+1.4 ms**; stratum 2 | **CLOSED 2026-07-24** |
| **LRGK** `192.119.82.145` | Needs operator receipt: `timedatectl status` / `chronyc tracking` (or equivalent) showing **NTPSynchronized=yes** and offset ≪ 30 min | **OPEN — close before 26 Jul UTC** |

Do **not** treat LRGK as clock-verified until that receipt is logged here or in inventory §8.

---

## Decision

| When | Action |
|------|--------|
| **By 2026-07-26 00:00 UTC** | Close LRGK NTP receipt → **confirm GO on H=17000** (no re-tag) |
| **Crossing** | Staffed watch ~**20:42 NZST 29 Jul → ~04:00 NZST 30 Jul** (align to live ETA); monitor rejects, tip, pool templates, peer subvers |
| **+24–48 h post-activation** | Check-in: tip healthy, no sustained invalid-template spam, Cexius/ops quiet |
| **§15.1 vault gate** | Remains **signed off ≠ discharged** until H1 rules are **merged and active on the network**; then flip `vault-threat-model.md` §15.1 row to **discharged** |

---

## Explicitly not blockers

- Pool-client peers still on 0.7.0/0.7.4 who mine **to our stratum** (templates from primary 0.7.6).  
- LRGK advertising stratum **with zero miners** (upgrade already done).  
- Cexius (chain hash verified).

---

*Ops correction 2026-07-24: LRGK + lagging-miner language was stale; register above supersedes inventory §6 CONDITIONAL HOLD framing.*
