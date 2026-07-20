# Bloodstone Coordinator Federation — Audit Remediation Note & STONE Membership Fee Plan

**Document version:** 1.2 · July 2026  
**Status:** Planning / design — **numeric fee schedule recommended**; G6 launch may reprice via board rate  
**Companion:** [Bloodstone-Decentralized-Coordinator-Federation-Ops-Topology.md](Bloodstone-Decentralized-Coordinator-Federation-Ops-Topology.md) (ops topology **v1.1**)  
**Public copy:** https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Coordinator-Federation-Remediation-And-Membership-Fee.md  

**References:**

- SWOT/audit of ops topology v1.0  
- Ops topology v1.1: §8.0–§8.7, §10.0, §10A, §10B, §15, §15.1, §18  
- Open design input: STONE coordinator membership fee  
- Early commercial rate context: `MONETIZE_STONE_USDT_RATE = 0.0001` USDT/STONE (fixed early — see USDT monetization model)

**Changelog (1.2):** §11 quick reference now lists all role top-ups (catalog +1M; pool +500k; electrumx +500k) matching §5.2; slash/burn wording clarified vs §8.4 (admission never burned; only proven-offense bond slash).

---

## 1. Executive summary

Ops topology **v1.1** answers the SWOT weaknesses and audit findings raised against **v1.0** via:

- An **§18 audit-response map**
- A hardened **roster bootstrap / rotation** chain (§8.5–§8.6)
- A staged **COORD-A transition playbook** (§10A)
- A **witness lifecycle** policy (§10B)
- An extended **adversarial / partition** test suite (§15.1 T8–T14)
- An explicit **gate registry** (§10.0 G0–G6) with start/declare rules

This document:

1. Records the **remediation status** (what ops v1.1 closed vs what remains verification work).  
2. Specifies the **STONE membership fee** as the concrete **§8.2 open-join Sybil** mechanism.  
3. Anchors fee **start** to **G6** and publishes a **recommended numeric schedule** (§5) with slash %, payment/escrow detail, and claim language (§5.8).

**Federation v1** remains: gates **G1 + G2 + G4**.  
**Storage-independence marketing** still requires **G3**.  
**Multi-operator marketing** still requires **`O_min ≥ 2`**.  
The fee is **necessary-not-sufficient** for decentralization claims.

---

## 2. Audit-response table (§18-style + fee row)

| Audit point (v1.0) | v1.1 / this doc | Status |
|--------------------|-----------------|--------|
| Deferred design / no Phase-exit clarity | Ops §10.0 gate registry + G0–G6 targets | **Resolved (design)** |
| Thin quorum / failure-domain detail | Ops §8.0 parameters + §8.7 operator checklist | **Documented** — verify in deploy |
| Roster bootstrap & key-control SPOF | Ops §8.5 bootstrap + §8.6 rotation | **Documented** — verify in clients |
| Transition fragility (single primary) | Ops §10A COORD-A playbook (`64.188.22.190` → peer) | **Documented** — execute when B/C live |
| Witness storage growth / rate limits | Ops §10B lifecycle + Phase 6 rate limits | **Documented** — verify prune job |
| Partition tests beyond kill-A | Ops §15.1 T8–T14; G6 exit includes T8–T11 | **Resolved (exit criteria)** |
| “Fake decentralization” perception | Ops §8.4 claim table + `O_min ≥ 2` | **Documented** |
| Open-join Sybil (fee mechanism) | Ops §8.2 + **this document §4–§6** | **Schedule recommended (v1.1)** — G6 board may reprice; amounts in §5.1 |

---

## 3. Detailed remediations (v1.1 confirmed)

### 3.1 Phase-gate & implementation control — CONFIRMED

Each phase has entry criteria, work, exit criteria, and rollback; exit criteria must not be skipped.

| Rule | Definition |
|------|------------|
| **Implementation start** | Coding/deploy for Phase *N* requires gate **G(N−1)** closed (checkbox + date in ops log) |
| **Federation v1** | Gates **G1 + G2 + G4** closed |
| **Storage-independence marketing** | Also requires **G3** |
| **Schedule** | Targets are planning defaults; **claims track gates, not calendar** |

| Gate | Phase focus | Target window (from Phase 0 start) |
|------|-------------|--------------------------------------|
| G0 | Decisions / inventory | Day 0–2 |
| G1 | Multi-witness unique IDs | Week 1–2 |
| G2 | Multi-homed status | Week 2–3 |
| G3 | Catalog / registry-first | Week 3–6 |
| G4 | Signed roster + client pin → **Federation v1** | Week 4–6 |
| G5 | Pool messaging / LAN clarity | Week 6+ |
| G6 | Open join, drills, rotation, `O_min` policy | Ongoing |

### 3.2 Quorum, failure domains, operator diversity

- Normative parameters: ops topology **§8.0** (`W_req`, lag, `C_min`, `O_min`, `D_min`, skew, silence).  
- Operator checklist: **§8.7**.  
- Multi-operator marketing requires **`O_min ≥ 2`** (**§8.4**).  
- “Anyone can be a coordinator” requires **Sybil resistance** before marketing (**§8.2**).

### 3.3 Roster bootstrap & key rotation

- Bootstrap chain: **§8.5** (binary pin → multi-URL → monotonic version; no unsigned single-IP trust).  
- Key rotation: **§8.6** (dual-sign / grace; G6 requires a rotation drill).  
- Client rule: never replace root pubkey because a webpage said so.

### 3.4 Single-primary transition

- **§10A** stages T0–T6: shadow peers → soft multi-home → roster authority → optional A relegation → A as equal peer.  
- Avoids a hard cut that strands users on brand DNS / pool / ElectrumX.

### 3.5 Witness lifecycle / rate limits

- **§10B:** ~0.5 KB capsules; **90-day** retention; one capsule per height; skip unchanged tip; weekly prune.  
- Phase 6: rate limits on catalog sync and status scrapers; revisit `W_req` / exchange overlay as roster grows.  
- Exchange overlay remains independent of any single coordinator’s summary field.

### 3.6 Extended adversarial / partition tests — CONFIRMED in exit criteria

Beyond T1–T7:

| Test | Scenario |
|------|----------|
| T8 | Operator-cluster network split |
| T9 | Clock skew |
| T10 | Rogue coordinator tip |
| T11 | Roster poison / bad signature |
| T12 | Witness spam / disk budget |
| T13 | Brand DNS / tunnel loss |
| T14 | Dual-region outage → degraded, not false “live” |

G6 exit requires drill reports including **T8–T11** (and chaos drills that include §15.1 scenarios).

### 3.7 Catalog decentralization & topology

- Topology: **full mesh** among **N ≤ 7** equal coordinators — not parent→child.  
- Catalog starts single-homed; federates in **Phase 3** (or registry-first path).  
- Public pool ledgers stay **operator-local**; LAN pools stay **household-local**.

---

## 4. Open design input — STONE membership fee

### 4.1 Purpose

The §8.2 open-join design anticipates **on-chain or Blurt registration with cost / stake / vouching**.  
The **STONE membership fee** is the concrete Sybil mechanism for **paid open admission** to the signed coordinator roster.

| The fee **is** | The fee **is not** |
|----------------|--------------------|
| Skin-in-the-game for open join | Consensus weight or mining subsidy |
| Roster admission + renewal right | Master Creator / treasury key rights |
| Sybil cost + optional ops funding | Shared pool ledger membership |
| Enforceable via roster publish | A substitute for `O_min` / `D_min` |

### 4.2 G-start (document-anchored — FIRM)

| Rule | Value |
|------|--------|
| **Fee-based open admission starts** | **No earlier than G6 / Phase 6** |
| **Phases 0–4 trust set** | **Known-operator, invite-only** |
| **After G4 (Federation v1)** | Roster + multi-home may exist **without** public paid join |
| **Rationale** | Ops topology keeps “known-op until Phase 6”; multi-operator and higher `D_min` are Phase 6 goals; open fee admission before G4 would market decentralization before bootstrap/roster hygiene exists |

```
G0–G3   Known-op only; no public paid join
G4      Federation v1 (roster + clients) — invite roster edits only
G5      Pool / LAN messaging — still no open join required
G6      Open join: STONE bond + yearly subscription → admission / renewal
        + chaos/partition drills + key rotation + O_min policy published
```

### 4.3 What payment buys

On successful payment + identity checks, the operator may be listed on the **signed roster** with declared **roles**, for example:

- `witness`
- `status`
- `downloads` (mirror)
- `catalog` (only if Phase 3 rules and extra policy allow)
- `pool` (optional; **own** ledger only — never federated unpaid balances)

Payment does **not** automatically grant catalog-primary, brand DNS, or ElectrumX listing without separate ops approval in early G6.

### 4.4 Enforcement consistency (ties to roster)

| Event | Action |
|-------|--------|
| Admission paid + approved | Include member in next signed roster publish |
| Subscription lapsed (after grace) | **Omit / suspend** on next signed roster |
| Bond slashed (policy offense) | Suspend or remove; publish reason code in ops log |
| Client behavior | After roster refresh (§8.5), stop treating removed ids as healthy coordinators |
| Refund (clean exit) | Return unslashed bond per policy; subscription non-refundable pro-rata optional |

---

## 5. Fee mechanics — recommended published schedule (v1.1)

> **G-start** remains **G6 only** (§4.2).  
> Numbers below are the **recommended launch schedule** for auditor verification.  
> At G6 go-live the federation board may reprice using the same **infra-cost method** if STONE/USDT moves materially; any change ships as a new `fee_schedule_version` on the roster and downloads.

### 5.0 Pricing method (how the numbers were chosen)

| Input | Value used |
|-------|------------|
| Lean coordinator VPS (node + witness + status HTTPS) | **≈ $20 USD / month** (planning anchor) |
| Fuller coordinator (pool/Electrum extras) | **≈ $40–60 USD / month** (not required for base seat) |
| Early fixed commercial rate | **0.0001 USDT per STONE** → **10,000 STONE ≈ $1 USDT** |
| Yearly subscription target | **≈ 2 months** lean infra ≈ **$40** |
| Bond target | **≈ 10 months** lean infra ≈ **$200** (≫ cheap sybil profit) |

**Conversion at early fixed rate:**

| USD (approx) | STONE |
|--------------|------:|
| $1 | 10,000 |
| $40 | **400,000** |
| $50 | 500,000 |
| $200 | **2,000,000** |
| $250 | 2,500,000 |

If `MONETIZE_STONE_USDT_RATE` or a market float changes, recompute:

```
sub_stone  = round_up( months_sub * vps_usd_month / usdt_per_stone )
bond_stone = round_up( months_bond * vps_usd_month / usdt_per_stone )
```

Keep **round STONE figures** for UX (prefer multiples of 100,000).

### 5.1 Published amounts (base open-join seat)

| Line item | Amount | Cadence | Destination | Refundable? |
|-----------|-------:|---------|-------------|-------------|
| **Yearly subscription** | **400,000 STONE** | Per seat-year | Federation **ops treasury** (transparent, not Master Creator chain treasury) | **No** (no pro-rata refund at baseline) |
| **Admission / standing bond** | **2,000,000 STONE** | Once per seat; top-up if slash or role upgrade | **Bond escrow** (2-of-3 ops multisig or equivalent) | **Yes** on clean exit if unslashed |
| **Total first-year cash out** | **2,400,000 STONE** | — | split as above | Bond portion refundable |
| **Renewal (year 2+)** | **400,000 STONE** | Yearly | Ops treasury | No |
| **Decimals** | 8 (chain standard) | — | Pay exact integer STONE; dust OK under 1 STONE | — |

**Approx USD at early fixed rate (illustrative only):** sub ≈ **$40/yr**, bond ≈ **$200**, first year ≈ **$240**.

**Identity binding (normative):**

| Rule | Value |
|------|--------|
| Paid seat | **1 subscription + 1 bond package** |
| Maps to | **exactly one** `operator_id` + **exactly one** primary `device_id` / `mesh_key` |
| Extra VPS same operator | Allowed for capacity; **same** `operator_id`; **does not** raise `O_min` |
| Whale spinning N seats | Must pay **N × package** and pass entity checks; still one legal entity ⇒ **`O_min` +1 max** |

### 5.2 Role top-ups (optional, additive bond only)

Base seat roles included: `witness`, `status`, `downloads` (covered by the **2,000,000 STONE** standing bond in §5.1 — no extra bond).

| Extra role | Additional bond (locked) | ≈ USD @ 0.0001 | Notes |
|------------|-------------------------:|---------------:|-------|
| `catalog` peer | **+1,000,000 STONE** | ~$100 | Only after Phase 3 / G3 rules exist |
| `pool` directory listing | **+500,000 STONE** | ~$50 | Own ledger only; no shared balances |
| `electrumx` public listing | **+500,000 STONE** | ~$50 | Optional; ops may refuse |

**Stacking:** top-ups are **additive** to the base bond (e.g. base + catalog + pool = **3,500,000 STONE** locked).  
**Both pool and electrumx:** **+500,000 each** if both roles approved (**+1,000,000** combined).  
Subscription stays **400,000 STONE/yr** for base seat; board may later add role-sub add-ons (not in baseline).

### 5.3 Monthly tier (optional, not required at G6 launch)

| Item | Amount |
|------|-------:|
| Monthly subscription | **50,000 STONE / month** (≈ $5 at early rate; ≈ 1.5× yearly if paid all year — premium for flexibility) |
| Bond | **Same 2,000,000 STONE** |

Ship monthly tier **only if** ops can handle 12× renewal events; default marketing is **yearly**.

### 5.4 Parameter summary

| Parameter | Published pick |
|-----------|----------------|
| Cadence | **Yearly** (monthly optional later) |
| Accounting | **Stake-lock bond** + **ops treasury subscription** |
| Burn on admission / renewal | **Never** — joining is not a burn fee (§5.5.1 / §8.4 narrative) |
| Burn on slash only | **50% of slashed bond** (offense-linked); other **50%** → ops treasury (§5.5) |
| Denomination | **STONE** on Bloodstone mainnet |
| Reprice | At least **yearly** at seat anniversary or global `fee_schedule_version` bump |
| Max roster size soft cap | **N ≤ 7** coordinators (ops topology); waitlist if full |
| Role top-ups | §5.2: catalog **+1M**; pool **+500k**; electrumx **+500k** |

### 5.5 Slash catalog (percentages)

Bond balance = currently locked bond for that seat (base **2,000,000** + any §5.2 top-ups − prior slashes).

| Code | Offense | Detection | Bond slash | Roster action | Rejoin |
|------|---------|-----------|------------|---------------|--------|
| **S0** | Subscription lapse after grace | Payment tracker | **0%** | Omit / `suspended_nonpay` | Pay sub + any top-up; bond intact |
| **S1** | Silence / unreachable **> 7 days** while listed | Health monitor | **0%** first event | `suspended_silence` | Auto or request after healthy 48h |
| **S2** | Silence **repeat** within 90 days | Health monitor | **10%** | Suspend until review | Top-up bond to full + review |
| **S3** | T10 rogue tip/status **≥ 2h** against majority (≥2 peers) | Partition/quorum monitors | **25%** | Remove 30 days | New review + top-up |
| **S4** | T10 rogue **repeat** within 180 days | Same | **100%** | **Permanent ban** `operator_id` | No |
| **S5** | Sybil / undisclosed multi-`operator_id` to game `O_min` | Ops investigation | **100%** all related seats | Permanent ban | No |
| **S6** | Proven roster/key attack, intentional client poison | Ops + evidence | **100%** | Permanent ban | No |
| **S7** | Contested slash | Member appeals within **14 days** | Hold | Stay suspended | Multisig vote; reverse if wrongful |

#### 5.5.1 Slash vs burn vs admission (normative — §8.4 alignment)

This separates **honest membership cost** from **penalty for proven bad behavior**, so slash/burn is not read as “pay STONE to be extracted.”

| Flow | What happens to STONE | §8.4 / narrative note |
|------|----------------------|------------------------|
| **Yearly subscription** | 100% → **ops treasury** (transparent federation ops) | Not a burn; funds roster ops, not Master Creator ceremony |
| **Bond lock (admission / top-up)** | 100% stays in **escrow**; refundable on clean exit | **Not burned** on join; Sybil skin-in-the-game only |
| **Slash (S2–S6 only)** | Of the **slashed portion only**: **50% ops treasury + 50% burn** | Penalty after due process; **not** an admission fee |
| **Unslashed bond on clean exit** | **100% returned** to member (minus network fees) | Proves bond was collateral, not a hidden burn |
| **Subscription on exit** | Not refunded (baseline) | Prepaid seat-year; still not a burn |

**Rules of construction:**

1. **Never** label the 400,000 sub or 2,000,000 bond as a “burn to join.”  
2. **Burn path exists only** after a published offense code (S2+) and adjudicator process.  
3. Marketing must use §5.8 language: fee ≠ consensus power; fee ≠ multi-op proof.  
4. Slash **does not** increase `O_min` or mint decentralization claims for remaining operators.

**Slash proceeds split (when slash &gt; 0% of bond):**

| Destination | Share of *slashed amount only* |
|-------------|------:|
| Federation ops treasury | **50%** |
| Burn (`COORD_BOND_BURN_v1` — provably unspendable / documented sink) | **50%** |

**Adjudicator (early G6):** 2-of-3 **federation ops multisig** (not Master Creator key).  
**Evidence window:** publish incident id, tips observed, timestamps; member may respond **72 hours** before S3+ executes (except ongoing attack).

### 5.6 Grace, renewal, reprice (finalized defaults)

| Item | Value |
|------|--------|
| Renewal reminders | **T−30** and **T−7** days |
| Grace after sub lapse | **21 days** (`grace` flag on roster) |
| After grace | Omit from signed roster within **next publish** (≤ 24h target) |
| Clean exit bond return | Request + **14-day** cool-off; return **unslashed** bond minus network fees |
| Global reprice | Board notice **≥ 30 days**; applies to **new** admits and **next** renewal only |
| Seat anniversary reprice | May use new schedule if `fee_schedule_version` increased |

### 5.7 Payment & escrow procedure (“contract” on UTXO chain)

Bloodstone is **UTXO / Bitcoin-family**, not EVM. “Contract” here means **published addresses + payment memo + multisig escrow + ops runbook** — not a Solidity contract.

#### Addresses (publish at G6; placeholders until generated)

| Name | Purpose | Control |
|------|---------|---------|
| `COORD_FEE_SUB_v1` | Yearly (or monthly) **subscription** receives | Federation ops treasury wallet (2-of-3 spend) |
| `COORD_BOND_ESCROW_v1` | **Bond lock** | 2-of-3 multisig; spends only for refund or slash split |
| `COORD_BOND_BURN_v1` | Slash burn leg | Provably unspendable or documented burn process |

*Until addresses exist, G6 fee gate checklist remains unchecked for “payment address published.”*

#### Admission payment steps

1. Applicant registers intent: `operator_id`, region, ASN, roles, contact, primary `device_id`.  
2. Ops uniqueness check (`operator_id` / entity).  
3. Applicant sends **two** on-chain payments (or one tx with two outputs):

   | Output | Amount | Destination |
   |--------|-------:|-------------|
   | Subscription | **400,000 STONE** | `COORD_FEE_SUB_v1` |
   | Bond | **2,000,000 STONE** | `COORD_BOND_ESCROW_v1` |

4. **Payment reference** (required in one of):  
   - `OP_RETURN` / tx message: `BSCF1|<operator_id>|<device_id>|<fee_schedule_version>`  
   - or mesh receipt asset: `assets/coordinator/payments/<txid>.json`  
5. Ops verifies ≥ **1 confirmation** (prefer **6** before roster include).  
6. Bond credited on seat ledger; subscription sets `paid_through = now + 365d`.  
7. Next signed roster includes member with roles + `paid_through`.  
8. Applicant runs coordinator stack; must emit unique-id witness capsules.

#### Renewal

- Send **400,000 STONE** to `COORD_FEE_SUB_v1` with same reference form before `paid_through + grace`.  
- Bond stays locked; no re-bond unless slashed or schedule top-up.

#### Clean exit

1. Member requests exit; removed from next roster.  
2. After **14-day** cool-off and no pending S3–S6 case: multisig refunds remaining bond to member’s specified address.  
3. Public ops log: exit + refund txid.

#### Slash execution

1. Incident record + 72h response (S3+).  
2. Multisig spends slash amount from escrow: 50% → treasury, 50% → burn.  
3. Seat ledger updated; member must top-up to full bond before rejoin (if allowed).

#### Optional later automation

- Payment watcher daemon matches `BSCF1|…` memos → draft roster PR.  
- Blurt `custom_json` mirror of payment proof (optional, not required for v1.1).

### 5.8 Claim language (§8.4 alignment — copy/paste for marketing)

**Allowed after G6 fee system live:**

- “Operators may **apply** to join the coordinator roster by locking a **STONE bond** and paying a **yearly STONE subscription**.”  
- “The fee is **Sybil resistance and roster membership**, not a mining reward and not consensus power.”  
- “Paid seats still require **unique device identity** and do **not** by themselves prove multi-operator decentralization.”  
- “The bond is **refundable collateral**; it is **not burned on join**. Only **proven policy offenses** can slash a portion of the bond (see public slash table).”  
- “Optional roles (catalog / pool directory / ElectrumX listing) may require **additional locked bond**, not extra subscription in v1 baseline.”

**Forbidden unless `O_min` / `D_min` bars met:**

- “Decentralized because anyone can pay STONE.”  
- “N paid coordinators = N independent operators” (false if one entity).  
- “Fee replaces witness quorum / braid / LAN pool.”  

**Forbidden always (burn/extraction narrative):**

- “Burn STONE to become a coordinator.”  
- “Admission fee is destroyed.”  
- Implying slash burn is automatic on join or renewal.

**Federation v1** (G1+G2+G4) may be claimed **without** the fee system.  
**Open join** marketing requires this document’s **§10 fee gate** checklist.

### 5.9 Logical admission package schema

```
Admission package (fee_schedule_version: 1)
├── operator_id          (stable legal/ops identity)
├── device_id / mesh_key (unique witness identity)
├── bond_stone           (2_000_000 base + role top-ups; escrow)
├── subscription_stone   (400_000 yearly → ops treasury)
├── paid_through         (ISO date)
├── roles[]              (approved subset)
├── region / asn_hint
├── payment_txids[]      (sub + bond)
└── contact / attestations
```

### 5.10 Optional post-G6 extensions

- Monthly tier (§5.3).  
- Blurt-anchored registration mirror.  
- Partner vouch **≤ 25%** subscription discount (bond **never** discounted below 2,000,000 for open join).  
- Waitlist auction if N = 7 hard cap.

---

## 6. Threat model (fee-specific)

| Threat | Mitigation |
|--------|------------|
| Whale funds many “operators” | 1 fee ↔ 1 `operator_id`; bond sized above fake-coord profit; optional vouch/KYC early; `O_min` counts entities |
| Same org, 3 VPS, 3 fees, claims multi-op | §8.4 + `operator_id` / legal entity; fees do **not** mint operator diversity |
| Non-payment mid-term | Grace then roster omit; clients refresh |
| Slash griefing | Clear catalog; human review early; evidence from T8–T10 style signals |
| “Fee = value extraction” narrative | Refundable bond; **no burn on join**; slash burn only after offense (§5.5.1); transparent treasury for sub only |
| STONE price volatility | Method-based sizing + scheduled reprice at renewal |
| Fee replaces decentralization work | Explicit: fee **does not** replace `O_min` / `D_min` / partition drills |

---

## 7. Grandfather & known-op policy (recommended defaults)

| Question | Recommended default | Status |
|----------|---------------------|--------|
| Pre-G6 invite members after G6 opens | **Grandfather: free subscription for 12 months** from G6 open; **bond waived** for founding seats A/B/C only; afterward full schedule or board exception | **Recommended** |
| Emergency invite after G6 | Allowed; unique ids; prefer converting to paid within 90 days | **Recommended** |
| Open paid join prerequisite | **`O_min ≥ 2`** already true under invite before marketing open join | **Recommended** |

---

## 8. Residual / open items

### 8.1 Verification pending (implementation, not design)

1. Confirm client **T11** “continue on last good roster” in code when Phase 4 ships.  
2. Confirm **§10B** prune / rate limits back **T12** disk budget.  
3. Confirm clients/exchanges enforce §8.4 / `O_min` so fee cannot spoof multi-op.  
4. Execute §10A when B/C exist; log gate closures with dates.

### 8.2 Ops publishables at G6 (amounts already recommended)

| Item | Status in this doc | Still needed at go-live |
|------|--------------------|-------------------------|
| STONE amounts | **§5.1 recommended** | Board confirm or reprice |
| Slash % table | **§5.5** | Multisig sign-off on first incident process |
| Grace = 21 days | **§5.6** | Config in payment tracker |
| Payment procedure | **§5.7** | **Generate real addresses** `COORD_FEE_SUB_v1`, `COORD_BOND_ESCROW_v1` |
| Claim language | **§5.8** | Comms review |
| Grandfather | **§7 recommended** | Founder list A/B/C |
| Monthly tier | **§5.3 optional** | Defer unless requested |
| Blurt mirror | Optional | Defer |

### 8.3 Accounting (closed for baseline)

| Option | Baseline |
|--------|----------|
| Pure burn as admission fee | **Rejected** (§5.5.1 / §8.4) |
| Bond escrow + yearly treasury sub | **Accepted** |
| Slash split 50% treasury / 50% burn | **Accepted — offense-only**, never on join/renewal |

---

## 9. Mapping to ops topology sections

| Topic | Ops topology v1.1 | This document |
|-------|-------------------|---------------|
| Gates / v1 definition | §10.0, §15 | §3.1 |
| Quorum / claims | §8.0, §8.4 | §3.2, §5.8, §6 |
| Roster trust | §8.5, §8.6 | §3.3, §4.4 |
| A → peer | §10A | §3.4 |
| Witness growth | §10B | §3.5 |
| Partition tests | §15.1 | §3.6 |
| Open join Sybil | §8.2 (principle) | **§4–§5 (amounts + payment)** |
| Audit map | §18 | §2 |

---

## 10. Acceptance criteria for “fee system ready” (G6 fee gate)

Do **not** market “anyone can pay STONE to be a coordinator” until:

- [ ] **G4** closed (roster + bootstrap pin in ≥1 client family)  
- [ ] **G6** chaos/partition minimum (T8–T11 once) scheduled or done  
- [x] Bond + yearly sub **amounts** published — **§5.1** (this doc v1.1)  
- [x] Slash + grace policy published — **§5.5 / §5.6**  
- [x] Claim language published — **§5.8**  
- [ ] **Live** payment addresses generated and published (`COORD_FEE_SUB_v1`, escrow)  
- [ ] Roster runbook: paid → include; lapsed → omit (manual OK at first)  
- [ ] `operator_id` uniqueness process staffed  
- [ ] Founder grandfather list recorded (§7)

---

## 11. Quick reference

**Remediation:** Ops topology v1.1 closed design gaps; claims follow **gates**, not calendar.

**Fee start:** **G6 open join only** (Phases 0–4 invite-only).

### 11.1 Base seat (required)

| Item | Amount | ≈ USD @ 0.0001 |
|------|-------:|---------------:|
| Yearly subscription | **400,000 STONE** | ~$40 |
| Standing bond (refundable escrow) | **2,000,000 STONE** | ~$200 |
| First-year total (base only) | **2,400,000 STONE** | ~$240 |

Base bond covers roles: `witness`, `status`, `downloads`.

### 11.2 Role top-ups (optional; additive bond — matches §5.2)

| Extra role | Additional bond | ≈ USD @ 0.0001 |
|------------|----------------:|---------------:|
| `catalog` peer | **+1,000,000 STONE** | ~$100 |
| `pool` directory listing | **+500,000 STONE** | ~$50 |
| `electrumx` public listing | **+500,000 STONE** | ~$50 |

Example: base + catalog + pool + electrumx locked bond = **4,000,000 STONE** (+ still **400,000 STONE/yr** sub).

### 11.3 Grace & slash (offense-only burn)

| Item | Value |
|------|------:|
| Grace after sub lapse | **21 days** |
| Rogue slash (first, S3) | **25%** of locked bond |
| Sybil / repeat rogue (S4–S6) | **100%** of locked bond |
| Slash proceeds | **50%** ops treasury / **50%** burn |
| Burn on join or renewal | **Never** (§5.5.1) |

**Buys:** Signed **roster seat** + roles — not consensus, not Master Creator, not shared pools.

**Must pair with:** `1 package ↔ 1 operator_id ↔ unique device_id` + **`O_min` / `D_min`** for decentralization marketing (**fee ≠ multi-op**).

**Success (federation):** COORD-A can die and tip policy + status still work; partitions **degrade safely**.

---

## 12. Document history

| Version | Date | Notes |
|---------|------|-------|
| 1.0 | 2026-07-11 | Remediation response note + STONE membership fee plan (method only) |
| 1.1 | 2026-07-11 | Recommended numeric schedule, slash %, payment/escrow procedure, claim language, grace/grandfather defaults |
| 1.2 | 2026-07-11 | §11 lists pool/electrum +500k top-ups; §5.2 stacking note; §5.5.1 slash/burn vs admission clarified for §8.4 |

---

*Bloodstone LLC · Coordinator federation remediation & membership fee plan · Companion to ops topology v1.1*
