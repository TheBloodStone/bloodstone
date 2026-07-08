# Bloodstone QUASAR — Witness-Aware Confirmation Guide

**Audience:** CEX integrators, custody engineers, GleecDEX / AtomicDEX operators  
**Phase:** QUASAR 4 (live) — fork signaling rehearsal, braid index, spend enforcement, witness, LAN echo, tripwires
**Updated:** July 2026

---

## 1. Why this exists

Bloodstone uses **three PoW algorithms** (neoscrypt, yespower, SHA256d merge-mining). A rented SHA256 fleet can skew **one epoch** without winning long-term chain work.

QUASAR Phase 1 adds a **software policy layer** so exchanges do not credit deposits on block height alone when the **epoch braid** is unhealthy.

**Do not use pool VPS RPC as your settlement source.** Run your own node or ElectrumX (see `/api/exchange`).

---

## 2. APIs to poll

| Endpoint | Purpose |
|----------|---------|
| `GET /api/exchange` | Listing pack — coin metadata, seeds, ElectrumX, **embedded `quasar` block** |
| `GET /api/quasar/status` | Live braid vector, witness quorum, LAN echo, tripwires, confirmations |
| `POST /api/quasar/witness/submit` | Ingest signed witness capsule (`bloodstone/witness-capsule/v1`) |
| `POST /api/quasar/lan-echo` | Submit LAN echo packet (`bloodstone/lan-echo/v1`) |
| `GET /api/quasar/alerts` | Active anomaly tripwire alerts |
| `GET /api/quasar/braid-index` | Persistent epoch braid index (`?sync=1` to refresh) |
| `POST /api/quasar/enforcement/check` | Spend policy gate — `{"amount_stone": N}` |
| `GET /api/quasar/activation` | Soft-fork deployment descriptor |
| `GET /api/quasar/signaling` | Miner version-bit signaling (bit 3) |
| `GET /api/quasar/fork-rehearsal` | Testnet rehearsal readiness |

Poll status every **60–120 seconds** (or on each deposit detection). Cache TTL on the server is ~45s.

### Example `quasar` block inside `/api/exchange`

```json
{
  "quasar": {
    "version": "3.0",
    "phase": 3,
    "enforcement_mode": "policy",
    "braid_index_synced_height": 12450,
    "braid_status": "healthy",
    "braid_finality_epoch_blocks": 10,
    "confirmation_multiplier": 1.0,
    "confirmations_deposit_recommended": 6,
    "confirmations_withdrawal_recommended": 6,
    "confirmations_policy": "standard",
    "sha256d_epoch_fraction": 0.42,
    "witness_status": "not_live",
    "status_url": "https://bloodstonewallet.mytunnel.org/api/quasar/status",
    "guide_url": "https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-QUASAR-Witness-Aware-Confirmation-Guide.md"
  }
}
```

---

## 3. Braid status values

| Status | Meaning | Deposit action |
|--------|---------|----------------|
| `healthy` | Epoch braid balanced across CPU + SHA256d lanes | Credit at **6** confirmations (default) |
| `skewed` | SHA256d-heavy or low CPU braid presence | Credit at **12–20** confirmations |
| `deferred` | SHA256d ≥85% of epoch with CPU braid &lt;10% | Credit at **20** confirmations; flag large deposits |
| `unknown` | Node RPC unavailable to policy service | **Do not credit** until status recovers |

Explorer shows the same status: `/explorer/` → **QUASAR Epoch Braid** panel.

---

## 4. Confirmation policy (Phase 1)

Base deposit confirmations: **6** (coinbase maturity **100** blocks — separate rule).

| Signal | `confirmations_deposit_recommended` | `confirmations_policy` |
|--------|-------------------------------------|-------------------------|
| Braid healthy | 6 | `standard` |
| Braid skewed | 12–20 (scales with SHA256d fraction) | `skew_bump` |
| Braid deferred | 20 | `deferred_finality` |
| Witness split (Phase 2) | Halt | `halt_deposits` |

**Withdrawals:** keep **6** confirmations unless your risk team dictates otherwise.

Implement in your crediting worker:

```python
listing = GET("/api/exchange")
status = GET("/api/quasar/status")
required = max(
    listing["coin"]["confirmations_deposit"],
    status["confirmations"]["recommended_deposit"],
    listing["quasar"]["confirmations_deposit_recommended"],
)
if status["braid_status"] == "unknown":
    pause_deposits()
```

---

## 5. Epoch braid mechanics (integrator mental model)

- **Epoch size:** 10 blocks (~15 minutes at 90s target inter-block time)
- **Braid vector:** `(sha256d_blocks, neoscrypt_blocks, yespower_blocks)` in the current epoch
- **Skew tripwire:** SHA256d fraction ≥ **85%** AND CPU (neoscrypt + yespower) fraction &lt; **10%** → `deferred`
- **Continuity:** prior epoch tip must appear in ≥2 algo streams in the current epoch (reorg / split-brain detector)

This is **policy**, not consensus — your node still follows most-work chain rules.

---

## 6. Witness-aware confirmations (Phase 2 — live)

Mesh **Witness Capsules** (`bloodstone/witness-capsule/v1`) publish signed tip attestations via Chain Mesh under `assets/witness/YYYY-MM/`. Android full/pruned nodes and the VPS coordinator emit capsules automatically.

```
confirmations_effective = base_confirmations + witness_bonus
witness_bonus = max(0, 3 - witness_quorum_depth)   # when quorum < 3
```

| Witness signal | Policy |
|----------------|--------|
| `live` — quorum ≥ 3 on tip | Standard braid policy applies |
| `pending` / `awaiting` — quorum &lt; 3 | `witness_pending` — add bonus confirms (cap 20) |
| `split` — disagreeing tip hashes | **Halt deposits** (`halt_deposits`) |

### LAN Echo Quorum (LEQ)

Phones on the same public IP echo their observed tip via `POST /api/quasar/lan-echo`. Status appears in `/api/quasar/status` → `lan_echo`:

| `lan_echo.status` | Meaning |
|-------------------|---------|
| `quorum` | Majority of LAN echoes agree with pool tip |
| `disagree` | LAN fleet disagrees with pool — delay deposits |
| `split_brain` | Multiple tip hashes on same LAN — manual review |

### Anomaly tripwires (AT)

`GET /api/quasar/alerts` evaluates pool share velocity and orphan shadow rules. When `tripwire.active` is true, `/api/exchange` bumps `confirmations_deposit_recommended` via `tripwire_bump` policy. Alerts also publish to `assets/alerts/quasar/YYYY-MM/latest.json` on mesh.

---

## 7. Braid index + spend enforcement (Phase 3 — live)

Phase 3 persists epoch braid summaries under `{datadir}/indexes/braid/` and exposes them via `/api/quasar/braid-index`. The status payload includes `braid_index`, `enforcement_mode`, and `activation`.

Before processing **large withdrawals**, call:

```bash
curl -s -X POST https://YOUR_HOST/api/quasar/enforcement/check \
  -H 'Content-Type: application/json' \
  -d '{"amount_stone": 5000}'
```

| `action` | Integrator response |
|----------|---------------------|
| `allow` | Proceed with standard confirmations |
| `defer` | Queue withdrawal; retry after `retry_after_sec` |
| `halt` | Manual review — do not auto-release |

Node RPC (after braid index sync): `getquasarbraid`, `getquasaractivation`.

Full proposal: `Bloodstone-QUASAR-Phase3-Braid-Finality-Proposal.md`  
Attack budgets: `Bloodstone-QUASAR-Attack-Budget-Appendix.md`

---

## 8. Operational checklist

1. Deploy **exchange node package** (`bloodstone-exchange-node-*-linux-x86_64.tar.gz`) with `txindex=1` and local hot wallet.
2. Subscribe to ElectrumX (`ssl://…:50002`) as a sanity check against your node's tip.
3. Poll `/api/quasar/status` — never credit when `braid_status` is `unknown`.
4. Log `confirmations_policy` changes for compliance audits.
5. On `skewed` or `deferred`, post a maintenance notice — deposits are delayed, not rejected.
6. Read the full defense model: `Bloodstone-QUASAR-51-Percent-Defense-White-Paper.md`.

---

## 9. Support links

| Resource | URL |
|----------|-----|
| QUASAR landing | `/quasar/` |
| Exchange pack | `/exchange/` |
| Explorer braid panel | `/explorer/` |
| Mesh anchors (Phase 2 witness path) | `/explorer/mesh-anchors` |

---

*Bloodstone · QUASAR Witness-Aware Confirmation Guide v3.0 · July 2026*