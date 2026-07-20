# Bloodstone Decentralized Coordinator Federation — Ops Topology & Deployment Phases

**Document version:** 1.1 · July 2026  
**Status:** Ops design — **implementation may start only after Phase 0 exit**; v1 federation declared only after **Phase gates G1+G2+G4** (see §10.0)  
**Public copy:** https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Decentralized-Coordinator-Federation-Ops-Topology.md  
**Primary coordinator today:** https://bloodstonewallet.mytunnel.org  
**Primary public IP today:** `64.188.22.190`  
**Related docs:**

- [QUASAR Witness-Aware Confirmation Guide](Bloodstone-QUASAR-Witness-Aware-Confirmation-Guide.md)
- [LAN Pool Coordinator Guide](Bloodstone-LAN-Pool-Coordinator-Guide.md)
- [Infrastructure Independence White Paper](Bloodstone-Infrastructure-Independence-White-Paper.docx)
- [RPC Reference](Bloodstone-RPC-Reference.md)
- [Become a Witness FAQ](Bloodstone-Become-A-Witness-FAQ.md)

**Changelog (1.1):** Addresses external audit/SWOT — explicit Phase gates + target dates, roster bootstrap & key rotation, quorum/failure-domain parameters, COORD-A transition playbook, witness lifecycle policy, partition-test scenarios beyond kill-A.

---

## 1. Purpose

This document turns the *decentralized VPS coordinator* concept into a **concrete operations topology**: host names, roles, ports, identities, trust rules, failure behavior, and **phased deployment**.

**Goal:** A small mesh of equal **coordinator-class** nodes so that tip policy, mesh discovery, and status APIs do not depend on a single VPS. Losing one region degrades capacity; it does not take the system offline.

**Non-goals:**

- Replacing Proof-of-Work consensus with coordinator votes
- Sharing unpaid pool balances across untrusted operators
- Exposing `bloodstoned` RPC on the public internet
- Making Master Creator / treasury keys multi-party via mesh alone
- Marketing multi-VPS under one operator as “final decentralization” (interim only; see §8.4)

---

## 2. Problem today (single coordinator bundle)

The live host is a **role bundle**, not a single protocol peer type:

| Role | Live surface | SPOF? |
|------|--------------|-------|
| Full node P2P | `17333/tcp` | Partially (peers exist; this host is a seed) |
| RPC | `127.0.0.1:18332` only | Local to host (correct) |
| QUASAR witness emitter | mesh assets `witness-vps-coordinator-{height}` | **Yes if all use same `device_id`** |
| Mesh catalog / publish | coordinator HTTP + SQLite | **Yes** |
| Policy / exchange APIs | `/api/quasar/*`, `/api/exchange` | **Yes** (one origin) |
| Public pool stratum | `3429`, `3437`, `3438`, `3440`, … | **Yes** for internet miners |
| ElectrumX | `50001` / `50002` | **Yes** for light clients using this host |
| Portal / downloads / wallet web | nginx `:80`/`:443` + tunnel name | **Yes** for branding/bootstrap |
| DTN / convergence flush | coordinator APIs | Partially |
| Mesh-gateway fallback | coordinator role | Partially (peer gateways exist) |

**Critical witness detail:** quorum counts **distinct `mesh_key` / `device_id`**, not number of JSON files. Ten boxes publishing as `vps-coordinator` still count as **one signer**.

Witness capsules today look like:

| Field | Example |
|-------|---------|
| Display name | `witness-vps-coordinator-10662` |
| Asset key | `assets/witness/2026-07/vps-coordinator-10662.json` |
| Version | `10662` (block height) |
| Size | ~526 B JSON |
| Schema | `bloodstone/witness-capsule/v1` |

These are intentional tip attestations (QUASAR Phase 2 / L4), not junk.

---

## 3. Target topology overview

```
                    ┌──────────────────────────────────────────┐
                    │     Signed coordinator roster (mesh +     │
                    │     downloads mirrors)                    │
                    └──────────────────┬───────────────────────┘
                                       │
          clients / exchanges / phones │ multi-endpoint failover
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        │                              │                              │
        ▼                              ▼                              ▼
 ┌──────────────┐              ┌──────────────┐              ┌──────────────┐
 │  COORD-A     │◄──gossip────►│  COORD-B     │◄──gossip────►│  COORD-C     │
 │  (primary    │              │  (regional)  │              │  (regional)  │
 │   today)     │◄─────────────│              │─────────────►│              │
 │              │              │              │              │              │
 │ full node    │              │ full node    │              │ full node    │
 │ witness      │              │ witness      │              │ witness      │
 │ catalog*     │              │ catalog*     │              │ catalog*     │
 │ APIs         │              │ APIs         │              │ APIs         │
 │ pool**       │              │ pool**       │              │ pool**       │
 └──────┬───────┘              └──────┬───────┘              └──────┬───────┘
        │                             │                             │
        └──────────── P2P :17333 ─────┴──────────── P2P :17333 ─────┘

 * Catalog starts single-homed; federates in Phase 3
 ** Public pool ledgers stay operator-local; LAN pools stay household-local
```

**Topology style:** full mesh among N ≤ 7 coordinators (equals), not a parent→child chain.

---

## 4. Concrete host inventory

### 4.1 Host table (fill IPs as provisioned)

| Host ID | Role class | Region (example) | Public IP / DNS | Witness `device_id` | Notes |
|---------|------------|------------------|-----------------|---------------------|-------|
| **COORD-A** | Full coordinator (primary today) | US / existing | `64.188.22.190` · `bloodstonewallet.mytunnel.org` | `coord-a-primary` (migrate from `vps-coordinator`) | Live production bundle |
| **COORD-B** | Full coordinator (peer) | EU | *TBD* · `coord-b.<your-domain>` | `coord-b-eu-01` | Second region |
| **COORD-C** | Full coordinator (peer) | APAC or second US ASN | *TBD* · `coord-c.<your-domain>` | `coord-c-apac-01` | Third signer / third region |
| **WORKER-1** (existing) | Hash / auxiliary worker | *same or nearby* | `192.119.82.145` | *(not a roster coordinator)* | Mining worker only; not a quorum peer |
| **LAN-*** | Household pool + witness | residential | private LAN | phone / desktop mesh keys | Complements federation; not VPS peers |

**Minimum production federation:** **3** coordinators in **≥2** regions / ASNs, preferably **3 different operators** long-term. Early phases may be single-org multi-region.

### 4.2 Role profiles per host

| Capability | COORD-A | COORD-B | COORD-C | WORKER-1 | LAN phone |
|------------|:-------:|:-------:|:-------:|:--------:|:---------:|
| `bloodstoned` full node | ✓ | ✓ | ✓ | optional | full/pruned |
| Unique witness capsules | ✓ | ✓ | ✓ | — | ✓ when online |
| Public HTTPS policy APIs | ✓ | ✓ | ✓ | — | — |
| Mesh catalog primary | ✓ (today) | mirror (Phase 3+) | mirror (Phase 3+) | — | — |
| Public stratum pool | ✓ (today) | optional own pool | optional own pool | — | LAN coordinator |
| ElectrumX | ✓ | optional | optional | — | — |
| Downloads mirror | ✓ | recommended | recommended | — | — |
| DTN flush target | ✓ | ✓ | ✓ | — | edge only |
| Remote CPU miners | offloaded | — | — | ✓ | — |

### 4.3 Identity rules (non-negotiable)

1. Every federation member has a **unique** `QUASAR_COORDINATOR_DEVICE_ID`.
2. `mesh_key` defaults to that device id (or an explicit stable key).
3. Roster **rejects** duplicate device ids.
4. Renaming `vps-coordinator` → `coord-a-primary` is a **controlled cutover** (see Phase 1): historical capsules remain under the old id; new capsules use the new id (counts as a new signer once cut over).

---

## 5. Network ports & security zones

### 5.1 Internet-facing (coordinator)

| Port | Service | Bind | Federation note |
|------|---------|------|------------------|
| `80` / `443` | nginx (portal, APIs, downloads) | public | Each coord has own cert / hostname |
| `17333` | Bloodstone P2P | public | All coords `addnode` each other |
| `3429` | SHA256d stratum | public if running pool | Operator-local ledger |
| `3437` | Neoscrypt stratum | public if running pool | |
| `3438` | Yespower stratum | public if running pool | |
| `3440` | ROD Neoscrypt legacy label | public if running pool | |
| `3430` | Stratum TLS (stunnel) | public if used | |
| `50001` / `50002` | ElectrumX tcp/ssl | public if offered | Clients pin multi-host list later |

### 5.2 Localhost-only (every coordinator)

| Port | Service | Rule |
|------|---------|------|
| `18332` | `bloodstoned` RPC | **Loopback only** — never public |
| Internal app ports (wallet, explorer backends, etc.) | various | Prefer localhost + nginx reverse proxy |

### 5.3 LAN-only (phones / household)

| Port | Service |
|------|---------|
| `18341` | Mesh chunk / peer serve (typical) |
| `18342` | LAN pool snapshot / verification HTTP |
| `3429`+ | Local stratum when LAN pool coordinator active |

### 5.4 Coordinator-to-coordinator control plane

Until dedicated gossip endpoints exist, Phase 1–2 use **HTTPS pull** only:

| Path (proposed) | Direction | Auth |
|-----------------|-----------|------|
| `GET /api/quasar/status` | any → peer | public read |
| `GET /api/quasar/witness/*` (or capsule list) | any → peer | public read |
| `GET /api/exchange` | any → peer | public read |
| Health: tip height, best hash, version | any → peer | public read |

Phase 3+ may add:

| Path (proposed) | Purpose | Auth |
|-----------------|---------|------|
| `GET /api/coordinator/roster` | signed peer list | public + signature verify |
| `GET /api/coordinator/catalog-head` | merkle head of asset index | public |
| `POST /api/coordinator/catalog-sync` | authenticated peer pull | mTLS or HMAC shared secret **or** signed challenges |

**Never** open RPC between VPS hosts. Sync chain via **P2P :17333** only.

---

## 6. Software stack per coordinator

### 6.1 Minimum stack (all COORD-*)

```
bloodstoned.service          # full node, txindex recommended for exchange-class hosts
nginx                        # TLS termination, reverse proxy
bloodstone-upkeep.timer      # 5 min unified upkeep (adapt per host role)
witness emit (cron/timer)    # emit-quasar-witness-capsule.py or upkeep hook
portal / API app             # at least quasar + exchange status routes
```

### 6.2 Full stack (COORD-A today; optional on B/C)

In addition to minimum:

- Stratum suite (`bloodstone-stratum-*`)
- Pool payout / dash warmers
- ElectrumX
- Explorer, faucet, wallet-web, miner-web, dex, support
- Mesh anchor index timer
- DTN / convergence services as deployed

**COORD-B/C can start lean** (node + witness + status APIs + downloads mirror) and opt into pool later.

### 6.3 Environment variables (witness / QUASAR)

| Variable | Default today | Federation value |
|----------|---------------|------------------|
| `QUASAR_COORDINATOR_DEVICE_ID` | `vps-coordinator` | **Unique per host** e.g. `coord-a-primary` |
| `QUASAR_WITNESS_PUBLISH_MESH` | `1` | `1` on all federation members |
| `QUASAR_WITNESS_MESH_PREFIX` | `assets/witness` | keep shared prefix |
| `QUASAR_WITNESS_QUORUM` | `3` | keep `3` until roster > 5; then revisit |
| `QUASAR_WITNESS_WINDOW_SEC` | `7200` | keep; ensures recent signers only |
| `BLOODSTONE_CONF` | `/root/.bloodstone/bloodstone.conf` | per host |
| `UPKEEP_ROLE` | `main` on A | `coord-peer` on B/C (lighter critical list) |

### 6.4 `bloodstone.conf` skeleton (each COORD)

```ini
server=1
daemon=1
chain=main
rpcbind=127.0.0.1
rpcallowip=127.0.0.1
rpcallowip=::1
port=17333
rpcport=18332
txindex=1
listen=1
bind=0.0.0.0
maxconnections=96
dnsseed=1
discover=1

# Federation P2P seeds (all peers list all peers)
addnode=64.188.22.190:17333
addnode=<COORD-B-IP>:17333
addnode=<COORD-C-IP>:17333
```

RPC user/password: **unique per host**, never shared across the public internet.

---

## 7. Data flows

### 7.1 Witness path (Phase 1+)

```
bloodstoned (local RPC)
    → emit-quasar-witness-capsule / emit_coordinator_witness()
    → capsule { tip_hash, height, algo_work, peer_count, device_id, mesh_key }
    → local quasar_witness_capsules table
    → mesh publish assets/witness/YYYY-MM/{device_id}-{height}.json
    → other nodes / exchanges consume for quorum_depth
```

Emit cadence today: tied to upkeep / periodic jobs (~minutes). Target: **at least once per ~1–2 blocks** when online, without spamming (one capsule per height is enough).

### 7.2 Client / exchange failover (Phase 2+)

```
exchange backend
  → GET https://coord-a.../api/quasar/status
  → GET https://coord-b.../api/quasar/status
  → GET https://coord-c.../api/quasar/status
  → if tips agree and quorum live → normal deposit confirms
  → if lag / 5xx → drop bad peer
  → if tips disagree → conservative policy / halt large deposits
```

**Best practice:** recompute witness quorum from capsule sets (mesh or API), not from a single host’s summary field alone.

### 7.3 Catalog path (Phase 3)

**Near-term (3A):** peer pull of asset metadata + provider hints; content still content-addressed.  
**Strategic (3B):** Blurt / on-chain registry authoritative; coordinators interchangeable caches.

### 7.4 Pool path (explicitly not federated early)

```
Internet miners → operator's own stratum → that operator's share ledger
Household miners → LAN pool coordinator (APK 1.3.84+) after peer verify
```

Do **not** merge unpaid `pending_stone` across VPS operators.

---

## 8. Trust model, quorum parameters & roster

### 8.0 Quorum & failure-domain parameters (normative)

These numbers make the success test operational. Clients and exchanges SHOULD implement the **exchange overlay** even if the coordinator API only exposes a single-host summary.

| Parameter | Symbol | Default | Notes |
|-----------|--------|---------|-------|
| Witness quorum (tip “live”) | `W_req` | **3** | Distinct `mesh_key` / `device_id` on same `tip_hash` within window |
| Witness window | `W_win` | **7200 s** (2 h) | Env `QUASAR_WITNESS_WINDOW_SEC` |
| Coordinator status majority | `C_maj` | **ceil(N/2)** of healthy roster members | For tip-hash agreement across HTTPS status peers |
| Min healthy status peers | `C_min` | **2** | Below this → treat policy as degraded / raise confirms |
| Max tip lag vs median | `L_max` | **6 blocks** | Peer lagging more is **unhealthy** (not counted in majority) |
| Min independent operators (v1 claim) | `O_min` | **1** interim / **2** for “multi-op beta” / **3** for “decentralized v1 marketing” | Single-org 3 VPS = **interim resilience only** |
| Min failure domains (region or ASN) | `D_min` | **2** for Phase 1 exit; **3** preferred for Phase 6 | Prefer distinct cloud/provider ASNs |
| Rogue coordinator threshold | — | 1 peer alone on tip T' while ≥2 agree on T | Mark peer **split/rogue**; do not follow minority tip for deposits |
| Clock skew tolerance | `S_max` | **120 s** | Capsule `issued_at` vs receiver clock; outside → ignore for quorum |
| Emit silence alert | `E_silence` | **30 min** | No new capsule from a roster member while node is up |

**Policy mapping (exchange / large deposit):**

| Condition | Action |
|-----------|--------|
| `quorum_depth ≥ W_req` AND status peers agree on tip | Standard braid/deposit policy |
| `0 < quorum_depth < W_req` | `witness_pending` — add bonus confirms (existing QUASAR formula) |
| Status peers disagree on tip (split) OR rogue minority tip | **Halt large deposits** until majority stable ≥ 15 min |
| Healthy status peers &lt; `C_min` | Degraded: raise confirms; optional halt withdrawals &gt; threshold |
| Capsule clock skew &gt; `S_max` | Drop that capsule from quorum count |

### 8.1 Early mode (Phases 0–4): known-operator federation

- Roster signed by a **foundation / ops multi-sig or single ed25519 ops key** held offline + deploy key online.
- Members: only hosts you (or named partners) control.
- Document operator legal entity / contact for each host.
- Public language: call this **“known-operator federation”**, not full decentralization, until `O_min ≥ 2` (preferably 3).

### 8.2 Later mode (Phase 6): open join

- On-chain or Blurt registration with cost / stake / vouching.
- Sybil resistance required before marketing “anyone can be a coordinator.”

### 8.3 Roster document (conceptual)

```json
{
  "type": "bloodstone/coordinator-roster/v1",
  "roster_version": 3,
  "issued_at": "2026-07-11T00:00:00Z",
  "not_before": "2026-07-11T00:00:00Z",
  "not_after": "2026-10-11T00:00:00Z",
  "quorum_hint": 3,
  "prev_roster_hash": "…",
  "members": [
    {
      "id": "coord-a-primary",
      "base_url": "https://bloodstonewallet.mytunnel.org",
      "p2p": "64.188.22.190:17333",
      "roles": ["witness", "catalog", "pool", "electrumx", "downloads"],
      "region": "us-east",
      "asn_hint": "ASXXXX",
      "operator_id": "bloodstone-ops"
    },
    {
      "id": "coord-b-eu-01",
      "base_url": "https://coord-b.example",
      "p2p": "B.B.B.B:17333",
      "roles": ["witness", "status", "downloads"],
      "region": "eu-west",
      "operator_id": "bloodstone-ops"
    },
    {
      "id": "coord-c-apac-01",
      "base_url": "https://coord-c.example",
      "p2p": "C.C.C.C:17333",
      "roles": ["witness", "status", "downloads"],
      "region": "apac",
      "operator_id": "partner-or-ops"
    }
  ],
  "signing_key_id": "roster-root-2026-07",
  "signature": "…"
}
```

Publish under e.g. `assets/coordinator/roster/latest.json` **and** mirror on every downloads host as:

`/downloads/coordinator-roster-latest.json`  
`/downloads/coordinator-roster-latest.json.sha256`  
`/downloads/coordinator-roster-v{N}.json` (immutable history)

### 8.4 “Fake decentralization” guardrail

| Claim you may make | Requires |
|--------------------|----------|
| “Resilient multi-node tip attestation” | Unique device ids + T1/T2 pass (can be one org) |
| “Works if primary VPS dies (status/witness)” | Phase 1+2 exit + kill-A drill |
| “Multi-operator federation” | `O_min ≥ 2` distinct legal/ops entities in roster |
| “Decentralized coordinator (marketing v1)” | Phases 1+2+4 + `O_min ≥ 2` + `D_min ≥ 2` + T2/T5/T8–T11 |
| “Storage discovery without portal” | Phase 3 exit (T7) |

### 8.5 Roster bootstrap (clients without trusting a single live host)

**Problem:** If the only way to get the roster is `https://bloodstonewallet.mytunnel.org/...`, federation inherits DNS/tunnel centralization.

**Bootstrap chain (ordered):**

1. **Genesis pin (client binary / APK / desktop install)**  
   - Embed: `roster_root_pubkey` (or key id + pubkey), `roster_version` floor, and a **bootstrap member list** (A+B+C base URLs + p2p) frozen at release.  
   - Embed SHA-256 of last known good roster JSON optional.

2. **First run**  
   - Try bootstrap URLs in random order.  
   - Accept roster only if: signature verifies under pin; `roster_version` ≥ embedded floor; `not_before`/`not_after` valid; member set non-empty.

3. **Refresh**  
   - Any healthy member may serve `latest.json`.  
   - Accept update only if: signature OK; `roster_version` **strictly greater**; `prev_roster_hash` matches previous accepted roster hash (or explicit key-rotation attestation — §8.6).  
   - Reject version rollback.

4. **Out-of-band recovery**  
   - Downloads mirrors, partner paste, Discord/ops signed announcement with new key id (human process for disaster).  
   - Optional: mesh asset `assets/coordinator/roster/latest.json` if mesh reachable without HTTPS portal.

5. **What clients must never do**  
   - Blindly trust unsigned JSON from a single IP.  
   - Replace root pubkey because a webpage said so (requires app update or dual-signed rotation message).

### 8.6 Roster key rotation procedure

| Step | Action |
|------|--------|
| 1 | Generate new ed25519 key pair offline (`roster-root-YYYY-MM`). |
| 2 | Produce **rotation roster**: signed by **both** old and new keys (dual signature fields) OR old-signed payload that includes `next_signing_key` + grace period. |
| 3 | Publish immutable `coordinator-roster-v{N}.json` on **all** mirrors + mesh. |
| 4 | Bump client embed on next app release with new pin; old key remains valid until `not_after`. |
| 5 | After grace (≥ 14 days or one full client release cycle): stop accepting old-only signatures. |
| 6 | Store old key offline destroyed/HSM policy; document in ops log. |
| 7 | **Drill:** annual forced rotation on staging roster. |

**Compromise response:** publish dual-signed empty/freeze roster if needed; push emergency app pin; announce via all operator channels.

### 8.7 Operator independence checklist (failure domains)

For each roster member record:

- [ ] Distinct public IP /32  
- [ ] Distinct region label  
- [ ] Distinct ASN **or** documented same-ASN exception  
- [ ] Distinct `device_id` / `mesh_key`  
- [ ] Distinct TLS cert / hostname  
- [ ] Operator contact + `operator_id`  
- [ ] Who can reboot the box (not all the same person if claiming multi-op)

---

## 9. Failure modes & expected behavior

| Failure | Expected behavior |
|---------|-------------------|
| COORD-A down | B/C still emit witnesses; clients use roster failover; pool on A offline until recovery or miners use LAN/other pools |
| COORD-B lagging tip | Peers mark unhealthy; do not count stale witness for tip quorum window |
| Two coords on tip X, one on tip Y | Status `split` / conservative exchange policy |
| Mesh publish fails on one host | Local capsule DB still has data; other hosts still publish; investigate disk/mesh DB |
| Catalog only on A, A dies (pre-Phase 3) | Discovery degraded; chunks may still exist on devices; **this is why Phase 3 matters** |
| Tunnel DNS (mytunnel) dies | Direct IP / alternate hostnames in roster still work if clients updated |
| Entire single-org multi-region outage | Still a trust-domain failure — multi-operator is the real fix |

---

## 10. Deployment phases

Each phase has **entry criteria**, **work**, **exit criteria**, and **rollback**. Do not skip exit criteria.

### 10.0 Phase-gate registry (implementation may not claim phase complete without these)

| Gate | Phase | Exit condition (must all pass) | Target window (from Phase 0 start) | Blocks implementation of |
|------|-------|--------------------------------|------------------------------------|---------------------------|
| **G0** | 0 | Host table filled; trust mode frozen; device id scheme approved; RPC-localhost policy signed off | **Day 0–2** | All later phases |
| **G1** | 1 | ≥2 unique coordinator device ids publishing; tips within 2 blocks; no public RPC; T1 path demonstrated (3rd signer may be phone) | **Week 1–2** | Partner multi-URL marketing |
| **G2** | 2 | ≥2 public status URLs; written exchange procedure; kill-A **status** drill 30 min pass | **Week 2–3** | “Primary can die” public claim |
| **G3** | 3 | T7 catalog survival **or** documented registry-first path live | **Week 3–6** | “Storage without portal” claim |
| **G4** | 4 | Signed roster live+mirrored; bootstrap pin in ≥1 client family; T5 + T2 client path | **Week 4–6** | **Federation v1** declaration |
| **G5** | 5 | Pool messaging clear; no cross-ledger balances; LAN guide mirrored | **Week 6+** | Multi-pool directory |
| **G6** | 6 | Quarterly chaos drill log; one key rotation drill; `O_min` policy published | **Ongoing** | Open roster join |

**Implementation start rule:** Coding/deploy for Phase *N* requires gate **G(N−1)** closed (checkbox + date in ops log).  
**Federation v1 rule:** Gates **G1 + G2 + G4** closed. Phase 3 (G3) required before storage-independence marketing.  
**Schedule uncertainty:** Targets above are planning defaults; slip is allowed, but **claims must track gates**, not calendar.

---

### Phase 0 — Inventory & decision freeze

**Duration:** 1–2 days  
**Owner:** ops lead  
**Gate:** G0  

**Work:**

1. Confirm budget for COORD-B and COORD-C (compute, disk, bandwidth, TLS).
2. Freeze trust mode: **known-operator** for Phases 1–5.
3. Choose regions / ASNs (prefer diverse providers).
4. Decide cutover name for A’s device id (`coord-a-primary` recommended).
5. Fill host table §4.1 with real IPs/DNS.
6. Document who holds roster signing key.

**Exit criteria:**

- [ ] 3 host slots identified (or 2 if temporary, knowing quorum needs a third signer from LAN/phones)
- [ ] Identity naming scheme approved
- [ ] Security rule reaffirmed: RPC localhost-only

**Rollback:** N/A (docs only).

---

### Phase 1 — Multi-witness coordinators (fast win)

**Duration:** 2–5 days  
**Depends on:** Phase 0 / **G0**  
**Gate:** G1  

**Work:**

1. Provision COORD-B (and COORD-C if ready) with:
   - `bloodstoned` full node
   - synced chain (bootstrap from known-good, then P2P)
   - `addnode` to A/B/C
2. Set unique env:
   - A: `QUASAR_COORDINATOR_DEVICE_ID=coord-a-primary` (cutover window)
   - B: `coord-b-eu-01`
   - C: `coord-c-apac-01`
3. Enable `QUASAR_WITNESS_PUBLISH_MESH=1` on all.
4. Run witness emit on a timer (5 min acceptable; tighten later).
5. Deploy **minimal HTTPS** on B/C: at least `/api/quasar/status` (and witness list if available).
6. **Do not** yet move public pool or primary DNS off A.

**Verification:**

```bash
# On each host
curl -sS http://127.0.0.1:18332/ -u user:pass \
  --data-binary '{"jsonrpc":"1.0","id":"1","method":"getblockchaininfo","params":[]}'

# Public status (after TLS)
curl -sS https://<coord-host>/api/quasar/status | jq '.witness'

# Mesh listing should show distinct display names:
#   witness-coord-a-primary-{H}
#   witness-coord-b-eu-01-{H}
#   witness-coord-c-apac-01-{H}
```

**Exit criteria:**

- [ ] ≥2 (ideally 3) distinct coordinator device ids publishing capsules
- [ ] Tips match within 1–2 blocks across coords under normal conditions
- [ ] `quorum_depth` can reach required 3 **without** relying on a single device id (phones can supply third during 2-host stage)
- [ ] No RPC port open on public interfaces (`ss -tlnp | grep 18332` → 127.0.0.1 only)

**Rollback:**

- Stop emit on B/C; revert A device id if cutover caused client confusion; A remains sole public coordinator.

---

### Phase 2 — Multi-homed status for exchanges & partners

**Duration:** 3–7 days  
**Depends on:** Phase 1 exit / **G1**  
**Gate:** G2  

**Work:**

1. Publish partner one-pager addendum: poll **≥2** coordinator base URLs.
2. Provide example client logic:
   - majority tip hash
   - max lag threshold (e.g. reject peer &gt; 6 blocks behind median)
   - on disagreement → raise confirms / halt large deposits
3. Optional: secondary DNS names (not required if raw hostnames in roster).
4. Mirror critical docs + SHA-256 sidecars on B/C `/downloads/`.
5. Keep ElectrumX primary on A; list B as optional when ready.

**Exit criteria:**

- [ ] Written exchange procedure with ≥2 endpoints
- [ ] Simulated A outage: partner can still read policy from B/C
- [ ] Downloads at least partially multi-homed

**Rollback:**

- Partners fall back to A-only URL (document grace period).

---

### Phase 3 — Catalog federation (or Blurt-primary acceleration)

**Duration:** 1–3 weeks  
**Depends on:** Phase 2 / **G2**  
**Gate:** G3  

**Choose path:**

| Path | Description | When to prefer |
|------|-------------|----------------|
| **3A Gossip/pull catalog** | Peers sync asset index heads + metadata | Need multi-VPS discovery soon |
| **3B Registry-first** | Blurt/on-chain manifest authoritative; coords are caches | Strategic fit with mesh v2-lite |

**Work (3A sketch):**

1. Define `catalog-head` (merkle over current asset keys + hashes).
2. Peer pull every N minutes; verify chunk hashes on demand.
3. Publish still allowed on any member; fan-out headers to peers.
4. Conflict rule: content-hash wins; same key different hash → quarantine + alert.

**Work (3B sketch):**

1. Ensure new publishes anchor to registry.
2. Coordinator catalog becomes cache + search UX only.
3. Clients resolve registry → providers without A.

**Exit criteria:**

- [ ] Publish on B is findable if A is offline (within documented lag)
- [ ] No silent overwrite of differing content under same key
- [ ] Runbook for catalog quarantine

**Rollback:**

- Disable peer sync; A remains sole catalog writer; document degraded mode.

---

### Phase 4 — Signed roster + client failover

**Duration:** 1–2 weeks  
**Depends on:** Phase 2 / **G2** (Phase 3 can parallelize)  
**Gate:** G4  

**Work:**

1. Generate ops signing key; store offline backup (§8.6).
2. Publish `bloodstone/coordinator-roster/v1` to mesh + all downloads mirrors.
3. Implement client bootstrap per §8.5 (pin + multi-URL + version monotonicity).
4. Client health score: tip freshness, TLS OK, latency, agreement with peers (§8.0).
5. Failover order: prefer regional low-latency, then any healthy, never single hardcode forever.

**Exit criteria:**

- [ ] Signed roster live and mirrored
- [ ] At least one client family uses multi-endpoint bootstrap
- [ ] Kill-A drill: client continues mesh/status via B/C

**Rollback:**

- Clients keep hardcoded A URL as ultimate fallback for one release cycle.

---

### Phase 5 — Pool story (optional, careful)

**Duration:** ongoing  
**Depends on:** Phase 1+ / **G1** (does not require Phase 3)  
**Gate:** G5  

**Work:**

1. **Do not** federate share ledgers across operators.
2. Document independent public pools (A’s pool, partner pool B, etc.) as separate brands.
3. Push LAN pool coordinator adoption (household independence).
4. Optional: pool directory in roster (`roles: ["pool"]`) for discovery only.

**Exit criteria:**

- [ ] Clear user messaging: which pool, which payout host
- [ ] LAN guide linked from downloads on all mirrors
- [ ] No cross-host unpaid balance claims

**Rollback:**

- Internet miners stay on A pool only.

---

### Phase 6 — Hardening & open ops

**Duration:** ongoing after Phase 4 / **G4**  
**Gate:** G6  

**Work:**

1. Sybil policy for roster (invite, stake, or on-chain register).
2. Rate limits on catalog sync and status scrapers.
3. Alerting: tip split, peer down, witness silence &gt; `E_silence`, disk &gt; 85%, clock skew.
4. Execute key rotation drill (§8.6) and TLS renewal drill.
5. Chaos drills quarterly: kill each COORD; plus partition scenarios (§15.1).
6. Revisit `W_req` / exchange overlay as roster size grows (§8.0).

**Exit criteria:**

- [ ] Drill reports stored (including partition tests T8–T11)
- [ ] Rotation tested once
- [ ] Public status page lists federation health (optional)
- [ ] `O_min` / marketing claims table (§8.4) published

---

## 10A. Transition playbook — COORD-A (`64.188.22.190`) from sole primary → peer

This is the path from **today’s single coordinator** to federation without a hard cut that strands users.

### Stage T0 — Sole primary (today)

- A owns: brand DNS, pool, ElectrumX, catalog, downloads, witness as `vps-coordinator` (or pre-cutover id).
- B/C: not required.

### Stage T1 — Shadow peers (after G1)

| Item | Action |
|------|--------|
| B/C | Full node + witness + minimal status HTTPS |
| A | Still sole public UX; optional rename device id to `coord-a-primary` |
| DNS | Unchanged (`bloodstonewallet.mytunnel.org` → A) |
| Pool / ElectrumX | Remain on A |
| Partners | Quietly notified of B/C status URLs as **experimental** |
| Success | Unique witnesses visible; A still does 100% user traffic |

### Stage T2 — Soft multi-home (after G2)

| Item | Action |
|------|--------|
| Docs / exchange one-pager | Document ≥2 status URLs |
| Downloads | Mirror SHA-256 artifacts on B/C |
| DNS | Optional: `status-b.` / `status-c.` CNAMEs; brand name still A |
| Monitoring | Synthetic checks poll A+B+C |
| Success | Kill-A 30 min: status+witness OK; pool may be down (expected) |

### Stage T3 — Roster authority (after G4)

| Item | Action |
|------|--------|
| Clients | Bootstrap pin + roster; A is one member, not the only root of trust |
| Brand DNS | May still point at A for portal UX |
| A role | **Peer with extra optional roles** (pool, catalog primary until G3) |
| Language | “Primary” retired in eng docs → “COORD-A (legacy brand host)” |

### Stage T4 — Catalog / storage independence (after G3)

| Item | Action |
|------|--------|
| Publish path | Any roster member or registry-first |
| A | No longer sole catalog writer |
| Kill-A | Mesh find/retrieve still works within documented lag |

### Stage T5 — Optional A relegation (not required)

Only after G3+G4+G5 and operator comfort:

1. Move brand DNS to anycast/LB **or** keep A as UX front with reverse-proxy failover to B (ops choice).
2. Split pool to a dedicated host or keep A as “official public pool” brand (accounting stays operator-local).
3. ElectrumX: add second instance; update `/api/exchange` list.
4. **Do not** shut A until: roster without A still has `C_min` healthy peers, downloads mirrored, partners notified 14 days.

### Stage T6 — A as equal peer (steady state)

- A is not special in protocol terms.
- Brand domain is UX, not trust root (trust root = roster pin + keys).
- Marketing uses §8.4 claim table only.

**Rollback at any stage:** restore DNS/docs to A-only; leave B/C running as dark witnesses (still useful for quorum).

---

## 10B. Witness file lifecycle policy

Witness capsules are small (~0.5 KB) but unbounded if never pruned.

### Retention

| Store | Retention | Rule |
|-------|-----------|------|
| Mesh asset `assets/witness/YYYY-MM/*.json` | **90 days** hot; older months **cold/archive or delete** | Prefer keep last 90d of *tips that still matter for audit*; not every height forever |
| Local `quasar_witness_capsules` SQLite | **90 days** or max **50k** rows per host | FIFO delete by `created_at` |
| Quorum evaluation | Only capsules within `W_win` (default 2h) | Old files never affect live quorum |
| Exchange compliance export | Optional monthly snapshot of tips + signer sets | Off-mesh backup |

### Publish rate limits

| Rule | Value |
|------|-------|
| Max useful capsules per device | **1 per block height** (overwrite/replace same height) |
| Emit interval floor | ≥ **60 s** between publishes per device |
| Skip if tip unchanged | If height+hash identical to last emit, skip mesh publish |
| Mesh display | UI may hide `assets/witness/**` behind “system attestations” filter |

### Replication

- Content-addressed chunks: only peers that **care** pull witness JSON.
- Coordinators SHOULD retain **recent** witness assets for other members’ audit.
- Full history replication across all nodes is **not** required.

### Prune job (ops)

- Weekly cron/timer: delete mesh witness assets with `created_at` older than 90 days (or month prefix &lt; current−3).
- Never prune non-witness user assets with this job.
- Log counts deleted; alert if prune removes &lt; expected (clock issues) or &gt; 10× expected (path bug).

### Growth budget (order of magnitude)

- 1 capsule / 5 min / 3 coords ≈ **~26k capsules/month** ≈ **~13 MB/month** raw JSON before chunk overhead — fine if pruned; monitor if emit rate increases.

---

## 11. Recommended build order (summary Gantt)

```
Week 0     Phase 0 decisions
Week 1     Phase 1 COORD-B up + unique witnesses
Week 1–2   Phase 1 COORD-C + quorum without single id
Week 2–3   Phase 2 exchange multi-endpoint
Week 3–6   Phase 3 catalog or registry-first
Week 4–6   Phase 4 roster + client failover (overlap OK)
Week 6+    Phase 5 pool directory / LAN push
Ongoing    Phase 6 drills & hardening
```

**Highest ROI first:** Phase 1 (unique witnesses) → Phase 2 (API multi-home) → Phase 4 (client roster).  
Phase 3 is the main storage SPOF killer; schedule it before marketing “fully decentralized coordinator.”

---

## 12. Day-2 ops checklists

### 12.1 Daily (automated preferred)

- [ ] All COORD tips within 2 blocks of each other
- [ ] Each COORD emitted a witness capsule in last 30–60 minutes
- [ ] HTTPS 200 on `/api/quasar/status` for all members
- [ ] Disk &lt; 85% on each host
- [ ] P2P connections &gt; 0 on each `bloodstoned`

### 12.2 After each release

- [ ] Roster version bumped if endpoints/roles changed
- [ ] SHA-256 sidecars for new download artifacts on **all** mirrors
- [ ] Witness device ids unchanged (unless intentional migration)

### 12.3 Incident: COORD-A down

1. Confirm B/C healthy and tips agree.
2. Announce degraded mode: primary pool/electrum may be down.
3. Point status communications at B/C URLs.
4. Do **not** hastily renumber device ids.
5. Restore A from runbook; re-sync if needed; rejoin P2P.

### 12.4 Incident: tip split across coordinators

1. Compare `getchaintips` / `getblockchaininfo` on each host.
2. Check peer sets and stuck IBD.
3. Exchange policy: halt large deposits until majority stable.
4. Avoid force-reorg unless Core rules demand it; prefer natural resolution.

---

## 13. What stays intentionally centralized (for now)

Be honest in partner comms:

| Item | Why still central |
|------|-------------------|
| Brand DNS `bloodstonewallet.mytunnel.org` | UX bootstrap; mitigated by roster |
| Primary public pool ledger on A | Accounting trust boundary |
| Master Creator / treasury ops | Separate key ceremony, not mesh |
| Single-org ownership of early B/C | Temporary; multi-operator is Phase 6 goal |

Federation **reduces** SPOFs for tip attestation, status, and (after Phase 3) discovery. It does not magically decentralize money keys or pool debt.

---

## 14. Mapping to existing Bloodstone pieces

| Existing feature | Federation use |
|------------------|----------------|
| Witness capsules + `mesh_key` | Multi-coordinator tip quorum |
| LAN pool coordinator (APK 1.3.84+) | Household independence from VPS pool |
| Mesh content addressing | Bytes survive catalog host loss |
| Blurt mesh v2-lite registry direction | Phase 3B catalog decentralization |
| Upkeep timer (5 min) | Host health + hook point for witness emit |
| Infrastructure Independence paper | Narrative + acceptance tests for “works without portal” |

---

## 15. Acceptance tests (definition of done)

**Federation v1** = gates **G1 + G2 + G4** (Phases 1+2+4).  
**Storage independence claim** also requires **G3** (Phase 3).  
**Multi-operator marketing** also requires `O_min ≥ 2` (§8.4).

### 15.0 Core tests

| # | Test | Pass condition | Gate |
|---|------|----------------|------|
| T1 | Unique signers | 3 distinct mesh keys on same tip (2 coord + 1 phone OK early) | G1 |
| T2 | Kill A 30 min | B/C serve status; witnesses continue; clients using roster still get policy | G2/G4 |
| T3 | Exchange poll | ≥2 URLs; conservative split policy documented | G2 |
| T4 | RPC exposure | No public `18332` on any COORD | G1 |
| T5 | Roster verify | Client rejects tampered / rolled-back roster | G4 |
| T6 | P2P mesh | Each COORD connects to others after restart | G1 |
| T7 | Catalog survival | Asset published on B retrievable while A stopped | G3 |

### 15.1 Partition & adversarial tests (beyond kill-A)

| # | Scenario | Procedure | Pass condition |
|---|----------|-----------|----------------|
| **T8** | Operator-cluster split | Firewall A+B from C (or A \| B+C) for 45 min while all stay “up” | Clients see split or degraded; **no** large-deposit “live” on minority tip; after heal, tips reconverge without manual reorg |
| **T9** | Clock skew | Set one COORD clock +10 minutes; emit capsule | Capsules outside `S_max` ignored; alerts fire; honest quorum still forms |
| **T10** | Rogue coordinator | One COORD advertises wrong tip hash in status + capsule | Majority tip retained; rogue marked unhealthy; deposits not following rogue |
| **T11** | Roster poison | Serve unsigned or wrong-key roster on one mirror | Clients ignore; continue on last good roster; alert/ops notice |
| **T12** | Witness spam | Rapid emit same device | Rate limit / one-per-height; disk growth within lifecycle budget (§10B) |
| **T13** | DNS/tunnel loss | Block `mytunnel.org` only | Bootstrap pin + alternate base_urls still reach B/C |
| **T14** | Dual region outage | Stop A and B | C alone: degraded (`C_min` fail) → raised confirms / halt large deposits — **not** silent false “live” |

Run T8–T11 at least once before G6; re-run quarterly with chaos drills.

---

## 16. Open decisions log

| Decision | Options | Recommendation | Status |
|----------|---------|----------------|--------|
| Trust set | known-op vs open | known-op until Phase 6 | Pending freeze (Phase 0 / G0) |
| Device id cutover on A | keep `vps-coordinator` vs rename | rename to `coord-a-primary` | Pending |
| Catalog path | 3A vs 3B | 3A if need speed; 3B strategic | Pending |
| Quorum at N=5+ | fixed 3 vs majority | **fixed `W_req=3` + status majority overlay** (§8.0) | **Resolved in 1.1** |
| COORD-B/C pool | yes/no | no at first (lean peers) | Recommended |
| Witness retention | 30 / 90 / 365 days | **90 days** (§10B) | **Resolved in 1.1** |
| Marketing bar for “decentralized” | 1-org OK vs multi-op | multi-op `O_min≥2` for that word (§8.4) | **Resolved in 1.1** |

---

## 17. Quick reference — one page

**Idea:** Many equal coordinators, unique IDs, full-mesh gossip/pull, clients use a signed roster.

**Do first:** B + C nodes, unique `QUASAR_COORDINATOR_DEVICE_ID`, witness publish, multi-URL status.

**Don’t do first:** Shared pool ledgers, public RPC, parent→child “chain” only, pretending one operator’s three VPS is final decentralization.

**Witness files in mesh:** expected; ~0.5 KB tip attestations under `assets/witness/YYYY-MM/`; **retain 90 days**, one per height, skip unchanged tip (§10B).

**Quorum defaults:** `W_req=3` distinct keys; status majority of healthy peers; lag &gt; 6 blocks = unhealthy (§8.0).

**Gates:** G0 decisions → G1 witnesses → G2 multi-status → G4 roster = **federation v1**; G3 for storage claim.

**Success:** A can die and tip policy + status still work; partitions degrade safely (T8–T14).

---

## 18. Audit response summary (v1.1)

External SWOT/audit themes and where this document answers them:

| Audit point | Document section |
|-------------|------------------|
| Deferred design / no Phase exit clarity | §10.0 gate registry + target windows |
| Thin quorum / failure-domain detail | §8.0 parameters; §8.7 operator checklist |
| Roster bootstrap & key control SPOF | §8.5 bootstrap chain; §8.6 rotation |
| Transition fragility from single primary | §10A staged T0–T6 playbook |
| Witness storage growth | §10B lifecycle, prune, rate limits |
| Partition tests beyond kill-A | §15.1 tests T8–T14 |
| Fake decentralization perception | §8.4 claim table |

---

## Document history

| Version | Date | Notes |
|---------|------|-------|
| 1.0 | 2026-07-11 | Initial ops topology + phased deployment from federation plan |
| 1.1 | 2026-07-11 | Audit/SWOT response: gates, quorum, roster bootstrap/rotation, A transition, witness lifecycle, partition tests |

---

*Bloodstone LLC · Coordinator federation ops · Companion to QUASAR Phase 2 witness mesh*
