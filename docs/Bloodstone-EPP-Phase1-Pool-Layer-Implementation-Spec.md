# Bloodstone EPP — Phase 1 Pool-Layer Implementation Specification

**Status:** Implementation Spec (Phase 1 only)  
**Governing architecture:** RFC-001 v0.6 — Edge Presence Proof (Architecture Freeze)  
**Date:** 2026-07-26  
**Scope:** Production-ready design against the live Bloodstone pool codebase  

---

## 0. Governing constraints (do not reopen)

From RFC-001 v0.6 and the Phase 1 brief:

| Constraint | Phase 1 stance |
|------------|----------------|
| Consensus / PoW | **Unchanged** — no hard fork, no validation changes |
| Observer | **Mining pool is the sole trusted observer** |
| OAL / bonds / maturity | **Not enforced** (architecture reserved for later phases) |
| Slashing / custodial stake | **Never** |
| Dishonest-but-valid detection | **Out of scope** (Phase 3 research gate) |
| Monetary policy | **No inflation** — EPP reuses an existing 1% allocation (see §2.2) |
| Binary EPP | Qualify / Do Not Qualify only — no scores, ranks, continuous edge scores |

**Architecture vs Phase 1 fidelity:** Phase 1 **faithfully implements** Layer 2 observation and Layer 3 economics **at the pool**, with the pool trusted as OAL. It does **not** implement multi-observer OAL, non-custodial bonds, or consensus-level proof verification. Those gaps are explicit, not design rework.

---

## 1. Repository impact analysis

### 1.1 Repositories / trees

| Tree | Role | Phase 1 changes |
|------|------|-----------------|
| **VPS root pool stack** (`/root/pool_*.py`, `bloodstone-stratum*.py`, `stratum_utils.py`) | Share accounting, block credit, stratum | **Primary** — EPP observer, challenge, qualification, payout split |
| **`bloodstone-miner-web`** | Browser miner, pool API, dashboard | Challenge client APIs, EPP status UI, metrics |
| **`bloodstone-portal`** | Public landing, nav, API mirror | Optional public EPP status + docs links |
| **`bloodstone-miner-android` / desktop** | Native miners | Optional: EPP challenge HTTP poll (Phase 1b) |
| **`bloodstone-core` / chain** | Consensus daemon | **None** for Phase 1 |
| **`bloodstone-wallet-web`** | Profiles, referrals | **None** required (optional later: show “edge qualified” badge from pool API) |
| **`bloodstone-repo` / docs** | Specs, downloads | Spec + operator notes only |

### 1.2 Modules affected (concrete)

| Module | Path | Change |
|--------|------|--------|
| Schema + credits | `pool_db.py` | New tables; EPP credit path on `distribute_block` |
| Algo distribution plan | `pool_algo_balance.py` | Hook: peel 1% EPP allocation before (or from) existing plan |
| Stratum neoscrypt | `bloodstone-stratum.py` | On authorize / share: register presence session; optional challenge nudge |
| Stratum yespower | `bloodstone-stratum-yespower.py` | Same |
| Stratum sha256d | `bloodstone-stratum-sha256.py` | Same (TCP peer + worker identity) |
| Stratum helpers | `stratum_utils.py` | Worker → address normalization reuse (no protocol change) |
| Browser / mobile | `pool_browser_miner.py`, `pool_mobile_contrib.py`, `pool_device_fleet.py` | Presence signals (IP, transport, device_id) feed observer |
| Miner API | `bloodstone-miner-web/app.py` | `/api/epp/*` routes |
| Payout runner | `pool_payout.py` | No protocol change — continues to pay `pending_stone` |
| New package | **`pool_epp.py`** (new) | Observer service, challenges, qualification, metrics |
| New service | **`bloodstone-epp-observer.service`** (optional) | Scheduled challenge sweeps / expiry |

### 1.3 Complexity estimate

| Area | Effort | Risk |
|------|--------|------|
| DB schema + migrations | S | Low — additive tables |
| Challenge generation / collection API | M | Medium — timing, DoS |
| Qualification binary logic | S–M | Low if pool-trusted |
| Integration into `distribute_block` | M | Medium — must not double-credit or break PPLNS |
| Dashboard / metrics | S | Low |
| Full multi-algo stratum + browser coverage | M | Medium — test matrix |
| Android native challenge client | L | Defer to Phase 1b |

**Overall Phase 1 (pool-trusted):** **~1–2 engineer-weeks** to MVP + metrics; **+1 week** hardening and multi-stratum coverage.

---

## 2. Mining pool architecture (Phase 1)

### 2.1 Trust model

```
┌─────────────┐     shares / jobs      ┌──────────────────┐
│   Miners    │◄──────────────────────►│ Stratum servers  │
│ (any kind)  │                        │ neo / yes / sha  │
└──────┬──────┘                        └────────┬─────────┘
       │                                        │
       │ HTTP challenge / proof                 │ record_share
       ▼                                        ▼
┌─────────────────────────────────────────────────────────┐
│                    pool_db (SQLite)                      │
│  shares · rounds · balances · epp_* tables               │
└───────────────────────────┬─────────────────────────────┘
                            │
       ┌────────────────────┼────────────────────┐
       ▼                    ▼                    ▼
┌─────────────┐    ┌────────────────┐    ┌──────────────┐
│ pool_epp.py │    │ distribute_    │    │ pool_payout  │
│ Observer    │    │ block (+ EPP)  │    │ on-chain     │
│ (trusted)   │    │                │    │              │
└─────────────┘    └────────────────┘    └──────────────┘
```

- **Observer = pool operator process** (`pool_epp` + stratum visibility).  
- Consensus daemon is only used for block templates / submitblock as today.  
- Miners do **not** need a consensus change to “prove geography.”

### 2.2 Fixed 1% allocation (no inflation)

**Implementation rule (pool layer):**

When `distribute_block(...)` runs for a closed round:

1. Resolve block subsidy (existing `pool_block_subsidy` / caller).  
2. Apply existing off-top items **unchanged** (finder bonus, staking fund, pool fee) as today.  
3. From the **remaining distributable** pot **or** from a dedicated **1% of gross subsidy** (pick one and freeze in code; recommend **1% of gross block subsidy before pool fee** for monetary clarity), set:

```
EPP_POOL = 0.01 * GROSS_BLOCK_REWARD_STONE   # Phase 1 default source
REMAINING = GROSS - EPP_POOL - other_off_tops  # then fee as today on remaining
```

**Calibration placeholders (not architecture):**

| Sub-bucket of EPP_POOL | Default Phase 1 | Notes |
|------------------------|-----------------|--------|
| Miner Edge Reward | **70%** of EPP_POOL | Qualified edge miners only |
| Observer Service Reward | **30%** of EPP_POOL | Phase 1: paid to **pool observer ops account** (single trusted observer) |

RFC §13: exact split is Phase 1 calibration. Env:

```
BLOODSTONE_EPP_ALLOCATION_BPS=100          # 1% of gross
BLOODSTONE_EPP_MINER_SHARE_BPS=7000      # of EPP allocation
BLOODSTONE_EPP_OBSERVER_SHARE_BPS=3000
BLOODSTONE_EPP_OBSERVER_ADDRESS=S…         # ops treasury / observer service sink
BLOODSTONE_EPP_ENABLED=0|1
```

**Cannot faithfully realize (Phase 1):** multi-observer competition for observer rewards. Phase 1 pays observer share to a **configured operator address** representing the trusted pool observer service — document as Phase 1 proxy for “service rewards.”

### 2.3 Observer service (`pool_epp.py`)

Responsibilities:

| Function | Behavior |
|----------|----------|
| Session registry | Track authorized workers: address, worker, algo, peer_ip, miner_kind, first/last seen |
| Challenge generation | Issue short-lived challenges to workers (or to stratum peer metadata path) |
| Challenge scheduling | Periodic sweep of active workers (not every share) |
| Measurement collection | Record RTT / reachability / multi-path observations **signed by pool** |
| Qualification | Binary: qualifies until expiry or failure |
| Metrics export | Prometheus-friendly counters + JSON for dashboard |

### 2.4 Challenge generation

**Challenge object (pool-signed, not miner-signed in Phase 1):**

```json
{
  "challenge_id": "epp_c_<uuid>",
  "address": "S…",
  "worker": "S….rig1",
  "algo": "yespower",
  "issued_at": 1785000000,
  "expires_at": 1785000060,
  "nonce": "<16 bytes hex>",
  "methods": ["tcp_echo", "http_pong"],
  "pool_sig": "hmac-sha256(pool_secret, canonical_payload)"
}
```

**Phase 1 measurement methods (pool-centric):**

1. **Stratum liveness** — worker submitted ≥1 valid share in window W (already known).  
2. **TCP peer diversity** — peer_ip not in “hosting concentration” set for that address’s recent sessions (heuristic).  
3. **HTTP pong** (browser/Android) — `POST /api/epp/challenge/response` with challenge_id + client nonce within TTL.  
4. **Optional multi-observer stub** — reserved columns; unused until Phase 2+.

**Pool signature** uses HMAC with `BLOODSTONE_EPP_HMAC_SECRET` (not blockchain crypto).

### 2.5 Challenge scheduling

| Parameter | Default | Env |
|-----------|---------|-----|
| Active worker definition | share or authorize within 15 min | `EPP_ACTIVE_WINDOW_SEC` |
| Challenge interval per worker | 5 min | `EPP_CHALLENGE_INTERVAL_SEC` |
| Challenge TTL | 60 s | `EPP_CHALLENGE_TTL_SEC` |
| Max concurrent open challenges / worker | 1 | — |
| Sweep period | 30 s | `EPP_SWEEP_SEC` |

**Do not challenge every share** — would amplify DoS and load.

### 2.6 Measurement collection

Store raw observations; qualification consumes them.

| Observation type | Source | Fields |
|------------------|--------|--------|
| `share_accept` | stratum `record_share` | t, algo, worker, peer_ip |
| `challenge_issue` | pool_epp | challenge_id, methods |
| `challenge_response` | HTTP API | rtt_ms, client_meta, ok |
| `tcp_probe` | pool observer | rtt_ms, success (optional outbound probe) |
| `qualify` / `disqualify` | pool_epp | reason codes |

### 2.7 EPP qualification logic (binary)

**Phase 1 qualify if ALL hold:**

1. **PoW activity:** ≥ N accepted shares (or mobile contribution ticks) in window Wq (default N=1, Wq=900s).  
2. **Fresh challenge:** at least one successful challenge response **or** continuous stratum presence with stable peer_ip for Tstable (default 300s) when HTTP client unavailable (ASIC path).  
3. **Not pool-operator / not blocked** (`pool_db` blocked addresses).  
4. **Not expired:** last successful proof younger than `EPP_QUALIFY_TTL_SEC` (default 1800s).  
5. **Topology independence heuristic (weak, Phase 1):**  
   - peer_ip /24 not shared by > K other **distinct** payout addresses that are also qualified (default K=50 — anti-farm soft cap), **or**  
   - browser/android with distinct `device_id` from fleet table.  

**Output:** `qualified ∈ {true, false}` + `reason` enum. No score.

**ASIC honesty:** Phase 1 cannot cryptographically prove independent topology for silent ASICs beyond share+IP heuristics. Spec marks this as **implementation limitation** (not RFC redesign): ASICs qualify via share liveness + IP diversity only; browser/phone can complete HTTP challenge for stronger Phase 1 evidence.

### 2.8 Pool payout integration

**Hook site:** `pool_db.distribute_block` after subsidy resolution, before proportional weight credits.

```
gross = reward_stone
epp_pool = gross * (EPP_ALLOCATION_BPS / 10000)
if not EPP_ENABLED: epp_pool = 0

# existing: finder bonus, staking, fee on (gross - epp - finder - stake) OR fee first — freeze order in code
plan = existing_distribution_plan(...)

qualified = set of addresses with active EPP qualify at block time
qualified_weight = sum(weight[a] for a in open_round if a in qualified)
if qualified_weight > 0 and epp_pool > 0:
    for a in qualified:
        credit(a, epp_pool * weight[a] / qualified_weight)  # Miner Edge Reward share of epp_pool * miner_bps
observer_cut = epp_pool * OBSERVER_SHARE_BPS / 10000
credit(OBSERVER_ADDRESS, observer_cut)

# remainder of epp_pool if no qualified miners → roll to next block or observer (document: roll-forward)
```

**Must not break:**

- `block_find_exists` idempotency  
- weight decay / multi-round open sets  
- blocked / frozen addresses  
- rental share path  

**Accounting:** EPP credits go to same `miner_balances.pending_stone` so `pool_payout.py` needs **no protocol change**.

---

## 3. Miner protocol (Phase 1)

### 3.1 Stratum (unchanged)

| Message | Change |
|---------|--------|
| `mining.subscribe` / `authorize` / `submit` | **No method change** |
| Side effect | On successful authorize + submit, pool updates `epp_sessions` |

Miners that only speak stratum (Bitaxe, cpuminer) need **no binary update** for Phase 1 baseline qualification.

### 3.2 HTTP APIs (miner-web / pool API)

Base: existing mining API host (`/mining/api/…` or portal mirror).

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/epp/status` | none | Global Phase 1 flags + allocation |
| GET | `/api/epp/session?address=&worker=` | none / rate-limit | Session + qualified bool |
| GET | `/api/epp/challenge?address=&worker=` | HMAC optional | Issue or fetch open challenge |
| POST | `/api/epp/challenge/response` | body | Complete challenge |
| GET | `/api/epp/metrics` | admin or localhost | Operational metrics |

#### 3.2.1 Challenge response body

```json
{
  "challenge_id": "epp_c_…",
  "address": "S…",
  "worker": "S….web",
  "client_nonce": "hex",
  "device_id": "optional fleet id",
  "client_ts": 1785000001
}
```

**Validation:**

- challenge exists, not expired, matches address/worker  
- single use  
- `client_ts` within ±120s of server (skew)  
- rate limit per IP and per address  

**Replay protection:** challenge_id unique; mark `consumed_at` on success.

**Timeouts:** issue TTL 60s; late response → fail, no qualify extension.

### 3.3 Browser miner integration

File: `bloodstone-miner-web/static/js/web-miner.js` (or small `epp-client.js`):

1. After authorized mining running, every `EPP_CHALLENGE_INTERVAL_SEC` poll `GET /api/epp/challenge`.  
2. Immediate `POST .../response`.  
3. Display “Edge: qualified / not” on miner stats (optional UX).

### 3.4 Authentication (Phase 1)

- **No new wallet signatures required** for Phase 1 (keeps friction low).  
- Identity = stratum worker authorization (address ownership assumed as today for pool payouts).  
- Optional Phase 1.1: require one-time message signature with address key for challenge bind (not RFC-required for pool-trusted).

### 3.5 Failure handling

| Failure | Effect |
|---------|--------|
| Challenge timeout | No qualify extension; existing qualify may expire |
| HTTP 429 | Back off; still mine |
| Pool EPP disabled | All EPP endpoints return `enabled: false`; full subsidy path as today |
| DB locked | Retry like `record_share` |

---

## 4. Data model

**Database:** same SQLite as pool — `BLOODSTONE_POOL_DB` → `/var/lib/bloodstone/pool.db`  
**Migration:** additive `CREATE TABLE IF NOT EXISTS` in `pool_db.init_db()` or `pool_epp.init_db()`.

### 4.1 Tables

```sql
-- Active mining presence for EPP
CREATE TABLE IF NOT EXISTS epp_sessions (
  session_id TEXT PRIMARY KEY,
  address TEXT NOT NULL,
  worker TEXT NOT NULL,
  algo TEXT NOT NULL,
  miner_kind TEXT NOT NULL DEFAULT '',
  peer_ip TEXT NOT NULL DEFAULT '',
  device_id TEXT NOT NULL DEFAULT '',
  first_seen INTEGER NOT NULL,
  last_share_at INTEGER NOT NULL,
  last_challenge_at INTEGER NOT NULL DEFAULT 0,
  qualified INTEGER NOT NULL DEFAULT 0,
  qualified_until INTEGER NOT NULL DEFAULT 0,
  qualify_reason TEXT NOT NULL DEFAULT '',
  UNIQUE(address, worker, algo)
);
CREATE INDEX IF NOT EXISTS idx_epp_sessions_qualified
  ON epp_sessions(qualified, qualified_until);
CREATE INDEX IF NOT EXISTS idx_epp_sessions_addr
  ON epp_sessions(address, last_share_at);

-- Challenges
CREATE TABLE IF NOT EXISTS epp_challenges (
  challenge_id TEXT PRIMARY KEY,
  address TEXT NOT NULL,
  worker TEXT NOT NULL,
  algo TEXT NOT NULL,
  issued_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  consumed_at INTEGER,
  nonce TEXT NOT NULL,
  methods_json TEXT NOT NULL DEFAULT '[]',
  pool_mac TEXT NOT NULL DEFAULT '',
  result TEXT NOT NULL DEFAULT '',  -- '', ok, fail, expired
  rtt_ms REAL,
  peer_ip TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_epp_chal_worker
  ON epp_challenges(address, worker, issued_at DESC);

-- Append-only audit / observations
CREATE TABLE IF NOT EXISTS epp_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  kind TEXT NOT NULL,
  address TEXT NOT NULL DEFAULT '',
  worker TEXT NOT NULL DEFAULT '',
  algo TEXT NOT NULL DEFAULT '',
  challenge_id TEXT NOT NULL DEFAULT '',
  peer_ip TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  block_height INTEGER
);
CREATE INDEX IF NOT EXISTS idx_epp_obs_ts ON epp_observations(ts DESC);
CREATE INDEX IF NOT EXISTS idx_epp_obs_kind ON epp_observations(kind, ts DESC);

-- Per-block EPP accounting
CREATE TABLE IF NOT EXISTS epp_block_credits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  algo TEXT NOT NULL,
  block_height INTEGER NOT NULL,
  block_hash TEXT NOT NULL,
  gross_reward REAL NOT NULL,
  epp_pool REAL NOT NULL,
  miner_edge_total REAL NOT NULL,
  observer_total REAL NOT NULL,
  qualified_count INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  UNIQUE(algo, block_height, block_hash)
);

CREATE TABLE IF NOT EXISTS epp_block_credit_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  block_credit_id INTEGER NOT NULL,
  address TEXT NOT NULL,
  role TEXT NOT NULL,  -- edge_miner | observer
  amount REAL NOT NULL,
  weight REAL NOT NULL DEFAULT 0,
  FOREIGN KEY(block_credit_id) REFERENCES epp_block_credits(id)
);
```

### 4.2 Audit trail

- Never UPDATE `epp_observations` rows (append-only).  
- Challenge `result` may transition `'' → ok|fail|expired` once.  
- Retention: prune observations older than `EPP_OBS_RETENTION_DAYS` (default 90) via upkeep job.

### 4.3 Metrics store

Either:

- in-process counters flushed to `epp_metrics_snapshots` every 60s, or  
- scrape `/api/epp/metrics` from existing monitoring.

---

## 5. Security review (Phase 1)

### 5.1 Trust assumptions

1. Pool operator is honest for observation and qualification.  
2. Stratum auth implies payout address control (same as today).  
3. HMAC secret for challenges is not leaked.  
4. Clock on pool host is NTP-synced (already an H1 ops requirement).  

### 5.2 Abuse cases

| Abuse | Mitigation |
|-------|------------|
| Sybil many workers one IP | /24 soft cap; device_id for mobile |
| Challenge spam | Rate limits; 1 open challenge |
| Replay challenge | Single consume; TTL |
| Farm many VPS IPs | Costly; still only 1% allocation — RFC economic ceiling |
| Disable EPP secretly | Feature flag + public `/api/epp/status` |
| Inflate EPP via fake shares | Unchanged share validation |
| Observer reward theft | Fixed OBSERVER_ADDRESS; audit lines |

### 5.3 Operational risks

- SQLite lock contention: use same retry pattern as `record_share`.  
- Challenge storms after pool restart: stagger sweep.  
- Qualifying zero miners: roll EPP pool to next block or to observer (config).  

### 5.4 DoS

- Challenge endpoints behind same nginx limits as mining API.  
- No unbounded body sizes.  
- Sweep limited to active sessions only.

### 5.5 Architecture fidelity gaps (explicit)

| RFC element | Phase 1 |
|-------------|---------|
| Independent multi-observer OAL | **Not implemented** — pool is sole observer |
| Non-custodial observer bond | **Not implemented** |
| Observer maturity 14d | **Not implemented** (optional soft config later) |
| Consensus proof verification | **Not implemented** |
| Dishonest-but-valid detection | **Not implemented** (Phase 3 gate) |

These are **deferred by brief**, not redesigned.

---

## 6. Performance analysis

| Resource | Expectation |
|----------|-------------|
| CPU | Challenge HMAC + occasional TCP probe: negligible vs PoW verify |
| Memory | Session map ~ few KB × active workers (typically &lt; 1k) |
| Network | +1 small HTTP RTT per worker per 5 min for browsers; ASICs 0 extra |
| SQLite | +2–4 writes/min/worker worst case; prune retention |
| Scalability | 10k workers: sweep batches of 500/tick; still fine on current VPS |

**Do not** add EPP work to the hot path of hash verification beyond one cheap session touch on accept.

---

## 7. Operational metrics (Phase 1 → calibration)

Collect at least:

| Metric | Definition |
|--------|------------|
| `epp_enabled` | gauge 0/1 |
| `epp_sessions_active` | sessions with last_share in window |
| `epp_qualified_sessions` | qualified_until &gt; now |
| `epp_qualification_rate` | qualified / active |
| `epp_challenges_issued_total` | counter |
| `epp_challenges_ok_total` | counter |
| `epp_challenges_fail_total` | counter by reason |
| `epp_challenge_success_rate` | ok / (ok+fail+expired) |
| `epp_challenge_rtt_ms` | histogram (p50/p95/p99) |
| `epp_share_liveness_ratio` | sessions with share in 15m / authorized |
| `epp_uptime_observer` | process uptime |
| `epp_sweep_duration_ms` | histogram |
| `epp_block_credits_total` | STONE credited to edge miners |
| `epp_observer_credits_total` | STONE to observer sink |
| `epp_false_qualification_proxy` | ops-labeled: % qualified later banned / same-/24 farm cluster size |
| `epp_ops_cost_proxy` | optional: challenge HTTP volume, DB size |
| `epp_per_algo_qualified` | breakdown neo/yes/sha |
| `epp_miner_kind_qualified` | browser/android/asic |

Export JSON snapshot every 60s to `/var/lib/bloodstone/epp-metrics.json` and dashboard panel on miner-web admin.

---

## 8. Open implementation questions (codebase-only)

1. **Exact peel order in `distribute_block`:** Is EPP 1% of gross before finder/staking/fee, or of post-fee distributable? **Recommend gross 1%** for simple monetary audit; confirm with ops.  
2. **Cross-algo rounds:** Bloodstone credits can span multiple open rounds / algos — does EPP qualify per-algo session or per-address global? **Recommend per-address global qualify, credit proportional to that block’s algo weights.**  
3. **SHA256 Bitaxe:** No HTTP stack — confirm IP+share path is acceptable for Phase 1 qualify (documented limitation).  
4. **Weight reset (6h):** Qualification TTL independent of weight reset; confirm UI copy so miners don’t confuse “weight reset” with “edge expire.”  
5. **`BLOODSTONE_EPP_OBSERVER_ADDRESS`:** Use existing treasury vs new ops address?  
6. **Rod dual pools:** EPP only on STONE pool balances Phase 1 (exclude ROD-only stratum).  
7. **Rentals (`pool_hashrate_rental`):** Exclude rental shares from EPP qualify/credit to avoid double-economic games.  
8. **Multi-instance stratum:** neoscrypt/yespower/sha are separate processes — session registry must be **DB-backed** (not memory-only per process).  

**None of the above reopen RFC architecture**; they are engineering freezes.

---

## 9. Implementation work packages (execution order)

| WP | Deliverable | Depends |
|----|-------------|---------|
| WP0 | Feature flag `BLOODSTONE_EPP_ENABLED=0` default off | — |
| WP1 | `pool_epp.py` + schema in `pool.db` | WP0 |
| WP2 | Session touch from all `record_share` / authorize paths | WP1 |
| WP3 | Challenge issue/response API on miner-web | WP1 |
| WP4 | Browser `epp-client.js` poll | WP3 |
| WP5 | `distribute_block` EPP peel + credits + audit rows | WP1–2 |
| WP6 | Metrics snapshot + admin panel | WP1 |
| WP7 | Enable on staging, soak 7 days, calibrate split | WP5–6 |
| WP8 | Production enable + public status | WP7 |

**Out of WP:** core consensus, bonds, multi-observer, dishonest-but-valid.

---

## 10. Testing plan

| Test | Pass criteria |
|------|----------------|
| Unit: qualify true/false matrix | Table-driven reasons |
| Unit: challenge expiry / replay | Second response fails |
| Integration: share → session → qualify | DB state |
| Integration: `distribute_block` with EPP on/off | Balances match spreadsheet |
| Load: 1k sessions sweep | &lt; 100ms/tick |
| Regression: existing PPLNS with EPP=0 | Bit-identical credits |

---

## 11. Documentation & operator surfaces

| Doc / UI | Action |
|----------|--------|
| This spec | `/downloads/Bloodstone-EPP-Phase1-Pool-Layer-Implementation-Spec.md` |
| RFC-001 v0.6 | Publish alongside when approved |
| Portal Mining commands | Link “EPP Phase 1 (experimental)” when enabled |
| Miner dashboard | Qualified badge + countdown of qualify TTL |
| Feature flag runbook | Enable/disable, observer address, allocation bps |

---

## 12. Conclusion

Phase 1 is a **pool-layer prototype** that:

- preserves PoW sovereignty and non-recourse  
- implements **binary** edge qualification with the **pool as trusted observer**  
- redistributes a **fixed 1%** via existing `pending_stone` rails  
- instruments calibration metrics for miner vs observer split  
- explicitly defers OAL bonds, multi-observer truth, and dishonest-but-valid detection  

**No consensus changes. No hard fork. No new cryptography beyond HMAC. No slashing.**

Architecture (RFC v0.6) remains frozen; this document only specifies how to implement Phase 1 against the live Bloodstone pool stack.

---

## Appendix A — Suggested file layout

```
/root/pool_epp.py                 # observer + qualify + challenge
/root/pool_db.py                  # schema hooks + distribute_block peel
/root/bloodstone-stratum*.py      # session touch on authorize/submit
/root/bloodstone-miner-web/app.py # /api/epp/*
/root/bloodstone-miner-web/static/js/epp-client.js
/etc/systemd/system/bloodstone-epp-observer.service
/var/lib/bloodstone/pool.db       # epp_* tables
/var/lib/bloodstone/epp-metrics.json
```

## Appendix B — Reason codes (qualify / challenge)

```
ok_share_and_challenge
ok_share_and_stable_peer
fail_no_shares
fail_challenge_expired
fail_challenge_replay
fail_rate_limited
fail_blocked_address
fail_rental_worker
fail_epp_disabled
expired_ttl
```

## Appendix C — Alignment with roadmap

1. ~~H1 Consensus Flag Day~~ (ops track)  
2. ~~RFC v0.6 Architecture Freeze~~  
3. **← This document: Phase 1 Pool-Layer Prototype**  
4. Operational data collection (metrics §7)  
5. Economic calibration (miner/observer split)  
6. Phase 3 research (dishonest-but-valid) — blocked until solved  

---

*Bloodstone EPP Phase 1 Pool-Layer Implementation Spec · RFC-001 v0.6 · 2026-07-26*
