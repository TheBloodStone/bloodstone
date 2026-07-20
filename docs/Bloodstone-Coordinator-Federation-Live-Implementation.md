# Bloodstone Coordinator Federation — Live Implementation Notes

**Document version:** 1.2 · July 2026  
**Status:** **Interim control plane on COORD-A only** (`64.188.22.190`) — **B/C not yet provisioned** — **not** Federation v1 — **not** multi-operator decentralized — open join **off** until G6.  
**As-of (UTC):** 2026-07-11 (gate snapshot from live API / CLI)  

**Public copy:**  
https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Coordinator-Federation-Live-Implementation.md

### Companion document set (version alignment)

| Document | File | Doc version | Role |
|----------|------|-------------|------|
| Ops topology | [Bloodstone-Decentralized-Coordinator-Federation-Ops-Topology.md](Bloodstone-Decentralized-Coordinator-Federation-Ops-Topology.md) | **v1.1** | Design: topology, gates G0–G6, phases, §8.4 claims |
| Remediation + fee plan | [Bloodstone-Coordinator-Federation-Remediation-And-Membership-Fee.md](Bloodstone-Coordinator-Federation-Remediation-And-Membership-Fee.md) | **v1.3** | Design: audit response, fee amounts, slash, payment procedure |
| **This file** | Bloodstone-Coordinator-Federation-Live-Implementation.md | **v1.2** | **Live-state audit record** (what is actually running) |

**Lineage (fee plan):** internal draft 1.0 (method) → 1.1 (numbers) → 1.2 (§11 top-ups + slash/burn clarity) → **1.3** (status line: design + live code pointers).  
Ops topology remains **v1.1** (no v1.2/v1.3 topology doc).  
Do not confuse **fee plan v1.x** with **ops topology v1.x** or **this live notes v1.x**.

**Public companions:**

- https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Decentralized-Coordinator-Federation-Ops-Topology.md  
- https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Coordinator-Federation-Remediation-And-Membership-Fee.md  

---

## 0. Audit claim guardrail (read first)

| Claim | Allowed now? | Why |
|-------|--------------|-----|
| “Control plane live on COORD-A” | **Yes** | APIs, signed roster file, fee JSON, unique device id, gates DB |
| “Federation v1” (G1+G2+G4) | **No** | G2 and G4 **open** (§1) |
| “Multi-operator / decentralized coordinator” | **No** | `operator_count=1`; `O_min` bar not met |
| “Open join / pay STONE to join” | **No** | `COORD_FEDERATION_OPEN_JOIN=0`; G6 open |
| “Fee schedule published” | **Yes** | JSON is **schedule only** — does **not** activate join (§5) |
| Fee proves multi-op | **Never** | §8.4: fee ≠ multi-operator |

Per ops topology §8.4: single-org multi-VPS or single live COORD-A is **interim resilience**, not marketing “decentralized v1.”

---

## 1. Explicit gate status (audit requirement)

Live source: `python3 /root/bloodstone_coordinator_federation.py gates`  
API: https://bloodstonewallet.mytunnel.org/api/coordinator/gates  

| Gate | Phase focus | Closed? | closed_at (unix) | Note / evidence |
|------|-------------|---------|------------------|-----------------|
| **G0** | Decisions / inventory | **Yes** | 1783767624 | Inventory + fee schedule live; bootstrap |
| **G1** | Multi-witness unique IDs | **Yes** | 1783767790 | `coord-a-primary` emits; mesh `witness-coord-a-primary-*` |
| **G2** | Multi-homed status | **No** | — | Only COORD-A public status origin |
| **G3** | Catalog / registry-first | **No** | — | Catalog still single-homed on A |
| **G4** | Signed roster + **client pin** → Federation v1 | **No** | — | Roster is **signed & published**; **client binary pin / multi-endpoint failover not shipped** → G4 incomplete |
| **G5** | Pool messaging / LAN clarity | **No** | — | Not started as federation work item |
| **G6** | Open join, drills, `O_min` policy | **No** | — | Open join env off; T8–T14 not closed |

| Composite | Value |
|-----------|--------|
| `federation_v1_ready` | **false** (needs G1✓ G2✗ G4✗) |
| `storage_claim_ready` | **false** (needs G3) |
| `open_join_ready` | **false** (needs G6 + env) |
| Implementation start rule | Phase N requires G(N−1) closed |
| Claims track | **Gates, not calendar** |

**Phase interpretation of live state:**

- **Phase 0:** exited (G0 closed).  
- **Phase 1 (partial→gate closed):** unique device id + control plane on A; **not** multi-host witnesses yet.  
- **Phases 2–6:** **not** exited.  
- Overall: **pre-G4 control-plane interim** on a single coordinator.

---

## 2. COORD-B / COORD-C status (narrow, not “Phase 1–6”)

| Host | Provisioned? | Phase work started | Phase work completed |
|------|--------------|--------------------|----------------------|
| **COORD-A** | **Yes** — `64.188.22.190` / mytunnel | 0, 1 (control plane) | G0, G1 only |
| **COORD-B** | **No** | **None** | — |
| **COORD-C** | **No** | **None** | — |
| **WORKER-1** `192.119.82.145` | Exists as hash worker | Not a federation quorum peer | N/A |

B/C are **not** “in Phase 1–6.” They are **not started**. Next concrete work for B (when provisioned) is **Phase 1**: full node + unique `device_id` + witness emit + minimal `/api/quasar/status`, then G2 multi-home.

---

## 3. Positive live controls (design match)

| Control | Live value | Design match |
|---------|------------|--------------|
| Device id | `QUASAR_COORDINATOR_DEVICE_ID=coord-a-primary` | Roster member id / rename decision |
| Operator id | `COORD_FEDERATION_OPERATOR_ID=bloodstone-ops` | Founding `operator_id` |
| Open join | `COORD_FEDERATION_OPEN_JOIN=0` | Known-op until Phase 6 / G6 |
| STONE/USDT rate (illustrative) | `MONETIZE_STONE_USDT_RATE=0.0001` | Fee plan early fixed rate |
| Witness retention | `QUASAR_WITNESS_RETENTION_DAYS=90` | Ops §10B / fee plan |
| Witness quorum | `QUASAR_WITNESS_QUORUM=3` | `W_req=3` |
| Autopublish on HTTP status | **Off** — status does not publish | Manual / upkeep publish model |
| Keys | `/root/.bloodstone/federation/` (not env) | Key separation |
| RPC | localhost `18332` only | Topology security zone |
| SHA-256 sidecars | On roster + fee JSON downloads | Verify / recovery |

---

## 4. Live roster snapshot (verifiable contents)

**URL:** https://bloodstonewallet.mytunnel.org/downloads/coordinator-roster-latest.json  
**API:** https://bloodstonewallet.mytunnel.org/api/coordinator/roster  

| Field | Live value (as-of write) |
|-------|---------------------------|
| `roster_version` | **11** (increments on publish; re-check file) |
| `type` | `bloodstone/coordinator-roster/v1` |
| Member count | **1** |
| `operator_count` | **1** |
| `multi_operator_claim_ok` | **false** |
| Signature | Present (`signature_b64`); API verify **ok** when tested |
| `signing_key_id` | `roster-root-2026-07` |
| Pubkey download | https://bloodstonewallet.mytunnel.org/downloads/coordinator-roster-root.pub |

**Sole member:**

| Field | Value |
|-------|--------|
| `id` / device | `coord-a-primary` |
| `operator_id` | `bloodstone-ops` |
| `base_url` | `https://bloodstonewallet.mytunnel.org` |
| `p2p` | `64.188.22.190:17333` |
| `region` | `us-east` |
| `roles` | witness, status, downloads, catalog, pool, electrumx |
| `status` | active (founding grandfather) |

---

## 5. Fee schedule JSON — published ≠ activated

**URL:** https://bloodstonewallet.mytunnel.org/downloads/coordinator-fee-schedule-latest.json  
**API:** https://bloodstonewallet.mytunnel.org/api/coordinator/fee-schedule  

| Field | Live value |
|-------|------------|
| `fee_schedule_version` | **1** |
| `g_start` | **G6** |
| `open_join_enabled` | **false** |
| `phases_0_4` | `known-operator invite-only` |
| Yearly sub | **400,000** STONE |
| Standing bond | **2,000,000** STONE |
| Top-ups | catalog +1M; pool +500k; electrumx +500k |
| `burn_on_join_or_renewal` | **false** |

**Explicit statement for auditors:** Publishing the fee schedule JSON is **informational and pre-commitment** to the recommended amounts. It does **not** enable public admission, does **not** close G6, and does **not** authorize “anyone can pay STONE to be a coordinator” marketing. Activation requires the **G6 fee gate checklist** (fee plan §10) including open-join env, runbook (§6), and gate close.

### 5.1 Live payment addresses

| Name | Address |
|------|---------|
| `COORD_FEE_SUB_v1` | `SVmWqYMadChSQMmKiKWtGQ2Lc5SG2sT2Eh` |
| `COORD_BOND_ESCROW_v1` | `SkUB1JZcJHWMBp78zVwZiMftGP6jN1SY2t` |
| `COORD_BOND_BURN_v1` | `SZVzFPHZGrGvLuBW8kd5pxJ65ZS9CBMMxJ` |

Memo format: `BSCF1|<operator_id>|<device_id>|<fee_schedule_version>`

---

## 6. Publish runbook (roster inclusion / exclusion)

Autopublish on status API is **off**. Roster mutations become public only when this runbook is executed (upkeep tick or CLI).

### 6.1 When to publish

| Trigger | Action |
|---------|--------|
| Founding / seat status change | Run publish after DB update |
| Payment recorded → active | Publish so clients see new member |
| Subscription lapsed past grace | Mark seat omitted/suspended → publish |
| Slash S3+ | Update seat status → publish |
| Gate close / fee schedule reprice | Publish roster + fee JSON |
| Scheduled upkeep | `federation-tick.py` (via `bloodstone-upkeep`) |

### 6.2 Commands

```bash
# Preferred: full tick (founding ensure, addresses, prune, publish)
python3 /root/federation-tick.py

# Or publish only
python3 /root/bloodstone_coordinator_federation.py publish

# Inspect before/after
python3 /root/bloodstone_coordinator_federation.py status
curl -sS https://bloodstonewallet.mytunnel.org/downloads/coordinator-roster-latest.json | jq '.roster_version,.operator_count,.members'
```

### 6.3 Paid → include

1. `POST /api/coordinator/apply` (or CLI/DB) creates seat `pending`.  
2. Applicant pays **sub** to `COORD_FEE_SUB_v1` and **bond** to `COORD_BOND_ESCROW_v1` with memo.  
3. `POST /api/coordinator/payment` with `sub_txid` + `bond_txid` → seat `active` (or `pending_invite_review` if open join off and non-founding).  
4. **Ops:** confirm invite policy; set `status=active` if invite approved.  
5. **Publish** (§6.2).  
6. Verify member appears in roster JSON with expected `device_id` / `operator_id`.  
7. Verify signature:  
   `python3 -c "import bloodstone_coordinator_federation as b,json; r=json.load(open('/var/www/bloodstone/downloads/coordinator-roster-latest.json')); print(b.verify_roster(r))"`

### 6.4 Lapsed → omit

1. Seat `paid_through` expired; after **21-day grace** seat must not remain `active` in published roster.  
2. Upkeep/build_roster already skips seats past grace; ensure payment tracker marks `suspended_nonpay` if needed.  
3. **Publish** so clients drop the member on next refresh.  
4. Verify member absent from `members[]` or `status` not trusted.

### 6.5 Slash → omit / suspend

1. `apply_slash(seat_id, code=S3|…)` (CLI can be added; function exists in module).  
2. **Publish** immediately.  
3. Log incident id for audit.

### 6.6 G6 fee-gate dependency

Fee plan §10 requires “Roster runbook: paid → include; lapsed → omit.”  
**This section is that runbook.** Gate G6 remains unclosed until open join is intentionally enabled and drills pass; the runbook is **satisfiable** before G6 so the gate is not blocked on missing procedure.

---

## 7. What shipped (code paths)

| Path | Role |
|------|------|
| `/root/bloodstone_coordinator_federation.py` | Core: fees, gates, roster, seats, payments, slash, prune, CLI |
| `/root/federation-tick.py` | Upkeep tick |
| `/root/emit-quasar-witness-capsule.py` | Witness emit → `coord-a-primary` |
| `/root/bloodstone-upkeep.sh` | Witness emit + federation tick |
| `/root/bloodstone-portal/app.py` | `/api/coordinator/*`, `/federation/` |
| `/root/bloodstone-portal/templates/federation.html` | UI |
| `/etc/nginx/snippets/bloodstone-proxy.conf` | `/federation/`, `/coordinator/` |
| `/root/.bloodstone/federation/` | Keys, addresses, local copies |

### 7.1 Public surfaces

| Surface | URL |
|---------|-----|
| UI | https://bloodstonewallet.mytunnel.org/federation/ |
| Status | https://bloodstonewallet.mytunnel.org/api/coordinator/status |
| Fee schedule API | https://bloodstonewallet.mytunnel.org/api/coordinator/fee-schedule |
| Roster API | https://bloodstonewallet.mytunnel.org/api/coordinator/roster |
| Gates API | https://bloodstonewallet.mytunnel.org/api/coordinator/gates |
| Apply | `POST /api/coordinator/apply` |
| Payment | `POST /api/coordinator/payment` |

---

## 8. Environment (COORD-A)

| Variable | Live / default | Notes |
|----------|----------------|-------|
| `QUASAR_COORDINATOR_DEVICE_ID` | `coord-a-primary` | Unique signer |
| `COORD_FEDERATION_OPERATOR_ID` | `bloodstone-ops` | Single operator today |
| `COORD_FEDERATION_OPEN_JOIN` | `0` | Invite-only |
| Status autopublish | Off | Publish = upkeep/CLI only |
| `COORD_FEDERATION_DIR` | `/root/.bloodstone/federation` | Secrets on disk |
| `BLOODSTONE_DOWNLOADS_DIR` | `/var/www/bloodstone/downloads` | Public artifacts |
| `MONETIZE_STONE_USDT_RATE` | `0.0001` | Illustrative USD only |
| `QUASAR_WITNESS_RETENTION_DAYS` | `90` | Prune |
| `QUASAR_WITNESS_QUORUM` | `3` | W_req |

---

## 9. Verification checklist

| Check | Result at v1.2 write |
|-------|----------------------|
| G0 closed | **Yes** |
| G1 closed | **Yes** |
| G2–G6 closed | **No** |
| Federation v1 ready | **No** |
| Open join enabled | **No** |
| operator_count ≥ 2 | **No** (1) |
| Roster signature verifies | **Yes** |
| Fee JSON open_join_enabled false | **Yes** |
| Fee amounts 400k / 2M / top-ups | **Yes** |
| Device id coord-a-primary | **Yes** |
| Publish runbook documented | **Yes** (§6) |
| B/C provisioned | **No** |

---

## 10. Remaining work (honest roadmap)

| Priority | Item | Unblocks |
|----------|------|----------|
| 1 | Provision COORD-B (unique device id + status HTTPS) | G2 path |
| 2 | Provision COORD-C or phone witnesses for W_req diversity | Quorum without single device |
| 3 | Client roster pin + multi-URL failover | **G4** / Federation v1 |
| 4 | Catalog federation or registry-first | G3 |
| 5 | Partition drills T8–T11 | G6 exit |
| 6 | Multisig bond escrow ceremony | Production fee safety |
| 7 | `COORD_FEDERATION_OPEN_JOIN=1` only after G6 checklist | Paid open join |

---

## 11. Quick reference

```
State:    COORD-A control plane only · B/C not yet provisioned · interim
          NOT federation v1 · NOT multi-op · NOT open join
Gates:    G0✓ G1✓ · G2–G6 open · federation_v1_ready=false
Join:     OPEN_JOIN=0 · fee JSON published but inactive (g_start=G6)
Roster:   1 member · bloodstone-ops / coord-a-primary · signed
Publish:  upkeep/CLI only · runbook §6 (paid→include, lapsed→omit)
UI:       https://bloodstonewallet.mytunnel.org/federation/
Companions: ops topology v1.1 · fee plan v1.3 · this live notes v1.2
```

---

## 12. Document history

| Version | Date | Notes |
|---------|------|-------|
| 1.0 | 2026-07-11 | Initial live implementation capture |
| 1.1 | 2026-07-11 | Audit remediation: explicit gates; companion version matrix; claim guardrail; roster/fee JSON contents; publish runbook §6; B/C “not started”; fee JSON ≠ activation |
| 1.2 | 2026-07-11 | Residual: header status explicitly “B/C not yet provisioned” (aligned with §2 / §11; removed any Phase 1–6 peer implication); companion self-ref row + §11 = v1.2 |

---

*Bloodstone LLC · Live implementation notes (audit-oriented) · Not a substitute for ops topology or fee plan design specs*
