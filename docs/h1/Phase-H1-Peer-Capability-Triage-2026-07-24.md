# Phase H1 — peer capability triage (not version count)

**Snapshot:** 2026-07-24 ~00:20 UTC  
**Tip:** **15068**  
**H:** 17000 · **remaining:** ~1932 blocks  
**ETA H (≈250 s/block):** ~2026-07-29 UTC (see `h1-boundary-status.json`)

**Metric:** can the peer **produce Bloodstone templates/blocks**, or only observe/wallet/mine *to* us?

| Class | Definition | Checkpoint treatment |
|-------|------------|----------------------|
| **(a) Block producer** | Solo GBT/creatework, own stratum serving STONE templates, or pool template source | **Hard blocker** if &lt; 0.7.6-h1 |
| **(b) Wallet / observer / pool-client** | Sync + relay only, or hashrate pointed at **our** stratum (templates from primary/LRGK) | Self-healing lag — may ride past H |

---

## Receipts (ops-controlled template hosts)

| Host | Role | Version | Subversion | Binary SHA256 | Tip | Class |
|------|------|---------|------------|---------------|-----|-------|
| **64.188.22.190** primary | bloodstoned + all STONE strata (3429/3437/3438) + tip-watchdog creatework | v0.7.6 | `/Bloodstone:0.7.6/` | `58d0f35ba9f9e10c34acf9c2e651199b6a7593859dd8762f9e81e89472ef4fe9` | 15068 | **(a) CLEAN** |
| **192.119.82.145** LRGK worker | bloodstoned + strata 3437/3438 (+ SHA if enabled) | v0.7.6 | `/Bloodstone:0.7.6/` | `58d0f35ba9f9e10c34acf9c2e651199b6a7593859dd8762f9e81e89472ef4fe9` | 15068 | **(a) CLEAN** (upgraded 2026-07-23) |

H1 markers on both: `nH1TimewarpActivationHeight`, `timewarp-dgw-window`.

**Recent block finds (2d):** 608× sha256d; finders only SeaYqq… / SiL1NK… / SZGS2… — all **pool workers** → templates from **primary 0.7.6** path.

---

## Sub-0.7.6 peers visible at snapshot (4 connections → 3 IPs)

Earlier “9 peers” mixed multi-conn; **now 3 IPs remain &lt; 0.7.6**.

| IP | Subver | Services | Height | Public ports probed | Stratum→primary? | Class | Notes |
|----|--------|----------|--------|---------------------|------------------|-------|-------|
| **107.205.210.9** | **0.7.0** | WITNESS + NETWORK_LIMITED (**no NETWORK**) | stuck start ~12070 | 17333 closed | **Yes** ESTAB 3429×2 + 3437 | **(b)** | Residential AT&T (lightspeed.rcsntx). Pruned/light peer; **mines to our pool** → uses **our** templates. Not a STONE template host. |
| **185.190.56.235** | **0.7.4** | NETWORK + WITNESS + LIMITED | synced ~tip | **17333 open**; 18332 speaks HTTP 400 (not useful JSON-RPC without creds); **7777** timeout; **no** 3429/3437/3438 | No ESTAB as miner in last ss snap | **(b)** primary; **soft (a) residual** | Full-relay node bidirectionally peered. **No public Bloodstone stratum.** Could still solo-GBT if they mine locally — **reach for upgrade receipt** (version + SHA + confirm no local GBT/stratum). |
| **207.177.142.232** | **mixed 0.7.4 + 0.7.6** | NETWORK/LIMITED mix | near tip | 17333 closed | **Yes** ESTAB 3429 | **(b)** | Wireless CPE. Multiple processes; one still 0.7.4. Hashrate to **our** pool. Prefer kill residual 0.7.4; **not** a public template host. |

### 0.7.6 peers (non-ops) — not blockers

| IP | Class | Notes |
|----|-------|-------|
| 97.149.216.154 | (b) pool-client | ESTAB yespower/neo to primary |
| 185.32.162.191 | (b) observer/wallet-ish | inbound 0.7.6 |
| 207.177.142.232 (0.7.6 conns) | (b) | same host as mixed row |

---

## Classification summary

| Class | Count (unique IPs) | Hard blocker for H=17000? |
|-------|--------------------|---------------------------|
| **(a) CLEAN ops templates** | 2 (primary + LRGK) | No — upgraded |
| **(a) unknown external templates** | **0 observed** (no foreign STONE stratum ports) | — |
| **(b) lag / pool-client / mixed residual** | 3 IPs with &lt;0.7.6 | **No** for checkpoint if finds stay on our pool |
| **soft residual (a)** | 185.190.56.235 if they solo-mine offline | Contact + upgrade preferred before H |

**Checkpoint reading:** version lag alone is **not** a re-tag trigger. **(a) external template hosts &lt; H1** would be. None detected on open ports.

---

## Cexius (closed 2026-07-24)

| Item | Status |
|------|--------|
| Main-chain tip hash | **CLOSED** — `getbestblockhash` `5ef86bdd…` → primary height **15133**, **confirmations 21** |
| Risk class | Exchange custody — same chain as primary; not a miner-split criterion |
| Action | No further chase required for H1 chain alignment |

---

## Live status feeds

- https://bloodstonewallet.mytunnel.org/downloads/h1-boundary-status.json  
- https://bloodstonewallet.mytunnel.org/downloads/h1-upgrade-lrgk.json  
