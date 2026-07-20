# Bloodstone Coordinator — Second Operator Onboarding

**Document version:** 1.0 · July 2026  
**Status:** Live path (invite-only) — raises `O_min` when a **distinct** `operator_id` is active  
**Public copy:** https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Coordinator-Second-Operator-Onboarding.md  

---

## 1. Why this exists

Multi-operator marketing requires **`operator_count ≥ O_min` (2)**.  
Today all seats use `bloodstone-ops`. A second host (`coord-b-lrgk-01`) does **not** raise `O_min`.

This document is the **real** second-operator path: ops issues an invite for a **new** `operator_id`; the partner runs a peer and pays the membership package (when payments are required).

---

## 2. Roles

| Party | Does |
|-------|------|
| **Ops (bloodstone-ops)** | `create-invite`, verify entity, approve seat, publish roster |
| **Partner operator** | Provides independent ops control, unique `device_id`, status HTTPS, witness emit |
| **Federation** | Counts distinct `operator_id` for `multi_operator_claim_ok` |

---

## 3. Ops: create invite

```bash
python3 /root/bloodstone_coordinator_federation.py create-invite \
  --operator-id partner-example-ops \
  --display-name "Example Partner LLC" \
  --contact "ops@example.com" \
  --entity-note "Independent legal entity; region eu-west" \
  --expires-days 30 \
  --roles witness,status,downloads
```

Send the returned `invite_code` **out-of-band** (never publish in open downloads).

```bash
python3 /root/bloodstone_coordinator_federation.py list-invites
```

---

## 4. Partner: apply

```http
POST https://bloodstonewallet.mytunnel.org/api/coordinator/apply
Content-Type: application/json

{
  "operator_id": "partner-example-ops",
  "device_id": "coord-eu-partner-01",
  "invite_code": "inv_…",
  "base_url": "https://partner.example",
  "p2p": "P.P.P.P:17333",
  "region": "eu-west",
  "roles": ["witness", "status"],
  "contact": "ops@example.com",
  "display_name": "Example Partner LLC"
}
```

Response includes payment amounts, addresses, and memo:

```text
BSCF1|partner-example-ops|coord-eu-partner-01|1
```

---

## 5. Partner: run a peer

Minimum (same as COORD-B lean peer):

1. Full node synced on mainnet  
2. Unique `QUASAR_COORDINATOR_DEVICE_ID`  
3. Public HTTPS: `/api/quasar/status` and/or `/api/coordinator/status`  
4. Witness emit (local capsule submit to primary or self-mesh)  
5. RPC **localhost only**  

Deploy pack reference on primary: `/root/coord-peer-pack/`

---

## 6. Payment + activation

1. Pay **400,000 STONE** (sub) + bond (2,000,000 base + role top-ups) with memo.  
2. `POST /api/coordinator/payment` with txids **or** ops runs:
   ```bash
   python3 /root/bloodstone_coordinator_federation.py scan-payments
   ```
3. Ops publishes roster:
   ```bash
   python3 /root/bloodstone_coordinator_federation.py publish
   ```
4. Verify:
   ```bash
   curl -sS https://bloodstonewallet.mytunnel.org/downloads/coordinator-roster-latest.json | jq '.operator_count,.multi_operator_claim_ok,.members'
   ```

When `operator_count ≥ 2` and `multi_operator_claim_ok=true`, multi-operator **marketing** language becomes allowed (still not “open join” until G6).

---

## 7. Claim guardrail

| Situation | Claim |
|-----------|--------|
| 2 devices, 1 operator_id | Multi-home only — **not** multi-operator |
| 2 operator_ids active | Multi-operator claim **OK** if regions/ASN independent |
| Invite not redeemed | No second operator |

---

## 8. Document history

| Version | Date | Notes |
|---------|------|-------|
| 1.0 | 2026-07-11 | Invite-based second operator path |

---

*Bloodstone LLC · Second operator onboarding*
